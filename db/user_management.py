import uuid
from datetime import datetime, timedelta
from db.DB import DB


def login_user(data):
    """
    Login function:
    Expects:
      {
         "email": <string>,
         "password": <string>
      }
    On successful login, creates a new session entry in the Sessions table.
    Returns a tuple:
      ( { "status": "success" or "failed",
           "session_id": <session_id or 0>,
           "reason": <explanation> },
        http_status_code )
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return {"status": "failed", "reason": "missing email or password"}, 401, 0

        # Check for the user by email.
        cur.execute('SELECT user_id, password FROM "User" WHERE email = %s', (email,))
        result = cur.fetchone()
        if result is None:
            return {"status": "failed", "reason": "no such user is signed in"}, 401, 0
        user_id, stored_password = result
        if stored_password != password:
            return {"status": "failed", "reason": "incorrect password"}, 401, 0

        # Generate a new session id using uuid
        session_id = str(uuid.uuid4())
        # Set an expiration time for the session (e.g., 1 day from now)
        expires_at = datetime.now() + timedelta(days=1)

        # Insert the session into the Sessions table.
        cur.execute(
            'INSERT INTO "Sessions" (session_id, user_id, created_at, expires_at) VALUES (%s, %s, NOW(), %s)',
            (session_id, user_id, expires_at)
        )
        conn.commit()

        return {"status": "success", "reason": ""}, 200, session_id

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed login"}, 401, 0


def register_user(data):
    """
    Registers a new user and then logs them in.
    Expects input data:
      {
         "email": <string>,
         "password": <string>,
         "first name": <string>,
         "last name": <string>,
         "age": <int>
      }
    Returns a tuple:
      ( { "status": "success"/"failed",
           "reason": <explanation> },
        http_status_code )
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()
        email = data.get("email")
        password = data.get("password")
        first_name = data.get("first name")
        last_name = data.get("last name")
        age = data.get("age")

        # Validate required fields.
        if not email or not password or first_name is None or last_name is None or age is None:
            return {"status": "failed", "reason": "missing required registration fields"}, 401, 0

        # Check if a user with this email already exists.
        cur.execute('SELECT user_id FROM "User" WHERE email = %s', (email,))
        if cur.fetchone():
            return {"status": "failed", "reason": "email already connected to an account"}, 401, 0

        # Insert the new user into the database.
        cur.execute(
            'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s)',
            (first_name, last_name, email, password, age)
        )
        conn.commit()

        # After successful registration, log in the user.
        return login_user({"email": email, "password": password})
    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed registration"}, 401, 0


def validate_session(session_id):
    """
    Validates the provided session id.
    A session is considered valid if its expires_at is in the future.
    If valid, optionally update the expiration (to extend the session).
    Returns a tuple:
      ( { "status": "success" or "failed",
           "reason": <explanation> },
        http_status_code )
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Look up the session in the Sessions table.
        cur.execute('SELECT user_id, expires_at FROM "Sessions" WHERE session_id = %s', (session_id,))
        result = cur.fetchone()
        if result is None:
            return {"status": "failed", "reason": "invalid session"}, 401, 0

        user_id, expires_at = result
        now = datetime.now()
        if now > expires_at:
            return {"status": "failed", "reason": "session expired"}, 401, 0

        # Optionally, extend the session expiration (here we extend it by 1 day from now).
        new_expires_at = now + timedelta(days=1)
        cur.execute('UPDATE "Sessions" SET expires_at = %s WHERE session_id = %s', (new_expires_at, session_id))
        conn.commit()

        return {"status": "success", "reason": ""}, 200, session_id

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed session validation"}, 401, 0


def get_user(session_id):
    """
    Retrieves the user_id associated with the given session_id.
    If the session is valid (not expired), the expiration is updated (extended by 1 day)
    and the user_id is returned along with a status code of 200.
    If the session is invalid or expired, returns 0 and a status code indicating failure.

    Returns:
      (user_id: int, status_code: int)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Query the session information.
        cur.execute('SELECT user_id, expires_at FROM "Sessions" WHERE session_id = %s', (session_id,))
        result = cur.fetchone()
        if result is None:
            return 0, 401  # Session not found.

        user_id, expires_at = result
        now = datetime.now()
        if now > expires_at:
            return 0, 401  # Session expired.

        # Extend the session expiration date by 1 day.
        new_expires_at = now + timedelta(days=1)
        cur.execute('UPDATE "Sessions" SET expires_at = %s WHERE session_id = %s', (new_expires_at, session_id))
        conn.commit()

        return user_id, 200
    except Exception as e:
        print(e)
        conn.rollback()
        return 0, 500
