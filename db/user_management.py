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
      ( response_dict, http_status_code, session_id (str) or 0, user_id (int) or 0 )
    """
    try:
        with DB.get_cursor() as cur:
            email = data.get("email")
            password = data.get("password")
            if not email or not password:
                return {"status": "failed", "reason": "missing email or password"}, 401, 0, 0

            cur.execute('SELECT user_id, password FROM "User" WHERE email = %s', (email,))
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "no such user is signed in"}, 401, 0, 0
            user_id, stored_password = result
            if stored_password != password:
                return {"status": "failed", "reason": "incorrect password"}, 401, 0, 0

            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(days=1)
            cur.execute(
                'INSERT INTO "Sessions" (session_id, user_id, created_at, expires_at) VALUES (%s, %s, NOW(), %s)',
                (session_id, user_id, expires_at)
            )
            return {"status": "success", "reason": ""}, 200, session_id
    except Exception as e:
        print(e)
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
      ( response_dict, http_status_code, session_id (str) or 0 )
    """
    try:
        with DB.get_cursor() as cur:
            email = data.get("email")
            password = data.get("password")
            first_name = data.get("first name")
            last_name = data.get("last name")
            age = data.get("age")
            if not email or not password or first_name is None or last_name is None or age is None:
                return {"status": "failed", "reason": "missing required registration fields"}, 401, 0

            cur.execute('SELECT user_id FROM "User" WHERE email = %s', (email,))
            if cur.fetchone():
                return {"status": "failed", "reason": "email already connected to an account"}, 401, 0

            cur.execute(
                'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s) RETURNING user_id',
                (first_name, last_name, email, password, age)
            )
            user_row = cur.fetchone()
            if user_row is None:
                return {"status": "failed", "reason": "failed to register user"}, 500, 0
        # End context to commit user insertion.

        # Log in the user.
        login_response, status, session_id = login_user({"email": email, "password": password})
        # Optionally, auto-register as creator here if needed (omitted as per your instructions).
        return login_response, status, session_id
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed registration"}, 401, 0


def validate_session(session_id):
    """
    Validates the provided session id.
    A session is considered valid if its expires_at is in the future.
    If valid, updates the expiration to extend the session by 1 day.
    Returns a 3-tuple:
      ( response_dict, http_status_code, session_id (str) or 0 )
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id, expires_at FROM "Sessions" WHERE session_id = %s', (session_id,))
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "invalid session"}, 401, 0

            user_id, expires_at = result
            now = datetime.now()
            if now > expires_at:
                return {"status": "failed", "reason": "session expired"}, 401, 0

            new_expires_at = now + timedelta(days=1)
            cur.execute('UPDATE "Sessions" SET expires_at = %s WHERE session_id = %s', (new_expires_at, session_id))
            return {"status": "success", "reason": ""}, 200, session_id
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed session validation"}, 401, 0


def get_user(session_id):
    """
    Retrieves the user_id associated with the given session_id.
    If the session is valid (not expired), updates its expiration (extended by 1 day)
    and returns the user_id.
    Returns:
      (user_id (int), status_code (int))
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id, expires_at FROM "Sessions" WHERE session_id = %s', (session_id,))
            result = cur.fetchone()
            if result is None:
                return 0, 401
            user_id, expires_at = result
            now = datetime.now()
            if now > expires_at:
                return 0, 401
            new_expires_at = now + timedelta(days=1)
            cur.execute('UPDATE "Sessions" SET expires_at = %s WHERE session_id = %s', (new_expires_at, session_id))
            return user_id, 200
    except Exception as e:
        print(e)
        return 0, 500


def get_user_info(user_id):
    """
    Retrieves all user information for the given user_id from the User table.

    Returns:
      tuple: (response_dict, http_status_code)

      On success:
        {
          "status": "success",
          "user": {
             "user_id": <int>,
             "first_name": <str or null>,
             "last_name": <str or null>,
             "email": <str or null>,
             "password": <str or null>,
             "age": <int or null>,
             "auth_token": <int or null>,
             "auth_last_used": <str in ISO format or null>
          }
        }
      On failure:
        { "status": "failed", "reason": <error message> }
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT user_id, first_name, last_name, email, password, age, auth_token, auth_last_used FROM "User" WHERE user_id = %s',
                (user_id,)
            )
            row = cur.fetchone()
            if row is None:
                return {"status": "failed", "reason": "User not found"}, 404

            user_info = {
                "user_id": row[0],
                "first_name": row[1],
                "last_name": row[2],
                "email": row[3],
                "password": row[4],
                "age": row[5],
                "auth_token": row[6],
                "auth_last_used": row[7].isoformat() if row[7] is not None else None
            }
            return {"status": "success", "user": user_info}, 200

    except Exception as e:
        print("Error in get_user_info:", e)
        return {"status": "failed", "reason": "Error retrieving user info"}, 500
