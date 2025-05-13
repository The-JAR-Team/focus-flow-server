import bcrypt
import uuid
from datetime import datetime, timedelta

import psycopg2.errors
import psycopg2.extras

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
                return {"status": "failed", "reason": "missing email or password"}, 401, 0

            cur.execute('SELECT user_id, password FROM "User" WHERE email = %s', (email,))
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "no such user is signed in"}, 401, 0
            user_id, stored_password = result

            # Verify password using bcrypt.
            if not bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                return {"status": "failed", "reason": "incorrect password"}, 401, 0

            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(days=1)
            cur.execute(
                'INSERT INTO "Sessions" (session_id, user_id, created_at, expires_at) VALUES (%s, %s, NOW(), %s)',
                (session_id, user_id, expires_at)
            )
            return {"status": "success", "reason": ""}, 200, session_id
    except Exception as e:
        print(e)
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
    After successful registration, automatically logs the user in.
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

            # Check if a user with the given email already exists.
            cur.execute('SELECT user_id FROM "User" WHERE email = %s', (email,))
            if cur.fetchone():
                return {"status": "failed", "reason": "email already connected to an account"}, 401, 0

            # Hash the password using bcrypt.
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            cur.execute(
                'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s) RETURNING user_id',
                (first_name, last_name, email, hashed_password, age)
            )
            user_row = cur.fetchone()
            if user_row is None:
                return {"status": "failed", "reason": "failed to register user"}, 500, 0
        # End of transaction for user registration; commit occurs upon exiting the context.

        # Log in the user immediately after registration.
        login_response, status, session_id = login_user({"email": email, "password": password})
        # Optionally, register as a creator here if needed.
        return login_response, status, session_id
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed registration"}, 401, 0


def _validate_and_extend_session(session_id):
    """
    Common helper: Checks if the session exists and is not expired.
    If valid, extends its expiration and returns (user_id, 200).
    On failure, returns (None, status_code).
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id, expires_at FROM "Sessions" WHERE session_id = %s', (session_id,))
            result = cur.fetchone()
            if result is None:
                return None, 401
            user_id, expires_at = result
            now = datetime.now()
            if now > expires_at:
                return None, 401
            new_expires_at = now + timedelta(days=1)
            cur.execute('UPDATE "Sessions" SET expires_at = %s WHERE session_id = %s', (new_expires_at, session_id))
            return user_id, 200
    except Exception as e:
        print(e)
        return None, 500


def get_user(session_id):
    """
    Retrieves the user_id associated with the given session_id.
    Uses _validate_and_extend_session to do the work.

    Returns:
      (user_id (int), status_code (int))
      If session is invalid, returns (0, error_code).
    """
    user_id, code = _validate_and_extend_session(session_id)
    return (user_id if user_id is not None else 0), code


def validate_session(session_id):
    """
    Validates the provided session id.
    Uses _validate_and_extend_session to check if the session is valid and extends its expiration.

    Returns a 3-tuple:
      (response_dict, http_status_code, session_id (str) or 0)
    """
    user_id, code = _validate_and_extend_session(session_id)
    if user_id is None:
        return {"status": "failed", "reason": "invalid or expired session"}, code, 0
    return {"status": "success", "reason": ""}, code, session_id


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
             "age": <int or null>,
             "permission": <int or null>
          }
        }
      On failure:
        { "status": "failed", "reason": <error message> }
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT user_id, first_name, last_name, email, age, permission FROM "User" WHERE user_id = %s',
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
                "age": row[4],
                "permission": row[5],
            }
            return {"status": "success", "user": user_info}, 200

    except Exception as e:
        print("Error in get_user_info:", e)
        return {"status": "failed", "reason": "Error retrieving user info"}, 500


def get_permission(user_id: int):
    """
    Retrieves the permission level for a given user_id.

    Args:
        user_id (int): The ID of the user.

    Returns:
        int or None: The permission level (integer) if the user is found,
                     otherwise None. Returns None on database error.
    """
    permission_level = None
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT permission FROM "User" WHERE user_id = %s',
                (user_id,)
            )
            row = cur.fetchone()
            if row is not None:
                permission_level = row[0]
                # Handle case where permission might be NULL in DB, though default is 1
                if permission_level is None:
                     print(f"Permission is NULL in DB for user_id: {user_id}. Returning None.")
            else:
                print(f"User not found when retrieving permission for user_id: {user_id}")
                permission_level = None # Explicitly None if user not found

    except psycopg2.Error as db_err:
        print(f"Database error retrieving permission for user_id {user_id}: {db_err}")
        permission_level = None # Return None on DB error
    except Exception as e:
        print(f"Unexpected error retrieving permission for user_id {user_id}: {e}")
        permission_level = None # Return None on unexpected error

    return permission_level


def logout_user(session_id):
    """
    Invalidates the session by removing it from the Sessions table.
    Returns a tuple: (response_dict, http_status_code)
    """
    try:
        with DB.get_cursor() as cur:
            # Delete the session row if it exists.
            cur.execute('DELETE FROM "Sessions" WHERE session_id = %s', (session_id,))
            if cur.rowcount == 0:
                # No row was deleted -> session didn't exist
                return {"status": "failed", "reason": "Session not found"}, 404
            return {"status": "success", "reason": "Logged out successfully"}, 200
    except Exception as e:
        print(f"Error logging out: {e}")
        return {"status": "failed", "reason": "Logout failed"}, 500
