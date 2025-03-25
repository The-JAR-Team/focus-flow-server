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
    Returns a 4-tuple:
      ( { "status": "success" or "failed",
           "reason": <explanation> },
        http_status_code,
        session_id (str) or 0,
        user_id (int) or 0 )
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return {"status": "failed", "reason": "missing email or password"}, 401, 0, 0

        # Check for the user by email.
        cur.execute('SELECT user_id, password FROM "User" WHERE email = %s', (email,))
        result = cur.fetchone()
        if result is None:
            return {"status": "failed", "reason": "no such user is signed in"}, 401, 0, 0
        user_id, stored_password = result
        if stored_password != password:
            return {"status": "failed", "reason": "incorrect password"}, 401, 0, 0

        # Generate a new session id using uuid.
        session_id = str(uuid.uuid4())
        # Set an expiration time for the session (e.g., 1 day from now).
        expires_at = datetime.now() + timedelta(days=1)

        # Insert the session into the Sessions table.
        cur.execute(
            'INSERT INTO "Sessions" (session_id, user_id, created_at, expires_at) VALUES (%s, %s, NOW(), %s)',
            (session_id, user_id, expires_at)
        )
        conn.commit()

        # Return a tuple without including the session_id in the response dict.
        return {"status": "success", "reason": ""}, 200, session_id, user_id

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed login"}, 401, 0, 0


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
    After successful registration, automatically logs the user as a creator.
    Returns a 3-tuple:
      ( { "status": "success" or "failed",
           "reason": <explanation> },
        http_status_code,
        session_id (str) or 0 )
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

        # Insert the new user into the database, returning the new user_id.
        cur.execute(
            'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s) RETURNING user_id',
            (first_name, last_name, email, password, age)
        )
        user_row = cur.fetchone()
        if user_row is None:
            conn.rollback()
            return {"status": "failed", "reason": "failed to register user"}, 500, 0
        user_id = user_row[0]
        conn.commit()

        # After successful registration, log in the user.
        login_response, status, session_id, returned_user_id = login_user({"email": email, "password": password})
        if status != 200:
            return login_response, status, session_id

        # Optionally, ensure that the user_id from registration matches the one returned by login_user.
        if user_id != returned_user_id:
            # This should not happen; if it does, it's a consistency error.
            return {"status": "failed", "reason": "user ID mismatch during login"}, 500, session_id

        # Automatically log the new user as a creator.
        creator_response, creator_status = log_creator(user_id)
        if creator_status != 200:
            return {"status": "failed", "reason": "user registered but failed to log as creator: " + creator_response.get("reason", "")}, 500, session_id

        return login_response, status, session_id

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed registration"}, 401, 0


def validate_session(session_id):
    """
    Validates the provided session id.
    A session is considered valid if its expires_at is in the future.
    If valid, updates the expiration to extend the session by 1 day.
    Returns a 3-tuple:
      ( { "status": "success" or "failed",
           "reason": <explanation> },
        http_status_code,
        session_id (str) or 0 )
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

        # Extend the session expiration by 1 day.
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
    and the user_id is returned.
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


def log_creator(user_id):
    """
    Logs a user as a creator by adding an entry into the Creator table.
    Parameters:
      user_id (int): The ID of the user to be registered as a creator.
    Returns a tuple:
      ( { "status": "success" or "failed",
           "creator_id": <new_creator_id> (if success) or omitted,
           "reason": <explanation> },
        http_status_code )
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Check if the user is already registered as a creator.
        cur.execute('SELECT creator_id FROM "Creator" WHERE user_id = %s', (user_id,))
        if cur.fetchone() is not None:
            return {"status": "failed", "reason": "User is already registered as a creator"}, 400

        # Insert a new record into the Creator table.
        cur.execute(
            'INSERT INTO "Creator" (user_id) VALUES (%s) RETURNING creator_id',
            (user_id,)
        )
        new_creator_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "success", "creator_id": new_creator_id}, 200

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": str(e)}, 500
