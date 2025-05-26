import bcrypt
import uuid
from datetime import datetime, timedelta

import db.email_confirmation_management as ecm
import psycopg2.errors
import psycopg2.extras

from db.DB import DB


def login_user(data):
    """
    Login function.
    Expects: {"email": <string>, "password": <string>}
    Returns a 3-tuple: (response_dict, http_status_code, session_id (str) or None)
    """
    response_dict = {"status": "failed", "reason": "Login failed due to an unexpected server error."}
    http_status_code = 500
    session_id_to_return = None

    try:
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            response_dict = {"status": "failed", "reason": "Missing email or password."}
            http_status_code = 400
        else:
            with DB.get_cursor() as cur:
                # Fetch user_id, hashed password, and active status
                cur.execute('SELECT user_id, password, active FROM "User" WHERE email = %s', (email,))
                result = cur.fetchone()
                if result is None:
                    response_dict = {"status": "failed", "reason": "Email not registered or incorrect."}
                    http_status_code = 401
                else:
                    user_id, stored_password_hash, is_active = result

                    if not bcrypt.checkpw(password.encode('utf-8'), stored_password_hash.encode('utf-8')):
                        response_dict = {"status": "failed", "reason": "Incorrect password."}
                        http_status_code = 401
                    elif not is_active:
                        # User's credentials are correct, but account is not active
                        response_dict, http_status_code = ecm.handle_inactive_user_login_attempt(user_id)
                        # session_id_to_return remains None for inactive users
                    else:
                        # Credentials correct and user is active, proceed to create session
                        generated_session_id = str(uuid.uuid4())
                        expires_at = datetime.now() + timedelta(days=1)
                        cur.execute(
                            'INSERT INTO "Sessions" (session_id, user_id, created_at, expires_at) VALUES (%s, %s, NOW(), %s)',
                            (generated_session_id, user_id, expires_at)
                        )
                        response_dict = {"status": "success", "reason": "Login successful.", "user_id": user_id}
                        http_status_code = 200
                        session_id_to_return = generated_session_id
    except Exception as e:
        print(f"TODO: Login exception: {e}")
        # response_dict and http_status_code are already set to a default server error
        # session_id_to_return remains None

    return response_dict, http_status_code, session_id_to_return


def register_user(data):
    """
    Registers a new user and initiates sending a confirmation email.
    The user account will be created as inactive.
    Expects input data: {"email": <string>, "password": <string>, "first name": <string>, "last name": <string>, "age": <int - optional>}
    Returns a 2-tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Registration failed due to an unexpected server error."}
    http_status_code = 500

    try:
        email = data.get("email")
        password = data.get("password")
        first_name = data.get("first name")
        last_name = data.get("last name")
        age = data.get("age")  # Age is optional, handle if None

        if not email or not password or not first_name or not last_name:
            response_dict = {"status": "failed",
                             "reason": "Missing required registration fields (email, password, first_name, last_name)."}
            http_status_code = 400
        else:
            with DB.get_cursor() as cur:
                cur.execute('SELECT user_id FROM "User" WHERE email = %s', (email,))
                if cur.fetchone():
                    response_dict = {"status": "failed", "reason": "This email address is already registered."}
                    http_status_code = 409  # Conflict
                else:
                    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    # User is inserted with active=FALSE by default (as per DB schema from previous steps)
                    if age is not None:
                        cur.execute(
                            'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s) RETURNING user_id',
                            (first_name, last_name, email, hashed_password, age)
                        )
                    else:
                        cur.execute(
                            'INSERT INTO "User" (first_name, last_name, email, password) VALUES (%s, %s, %s, %s) RETURNING user_id',
                            (first_name, last_name, email, hashed_password)
                        )
                    user_row = cur.fetchone()

            if user_row is None:
                response_dict = {"status": "failed", "reason": "Failed to create user account in the database."}
                # http_status_code remains 500
            else:
                user_id_registered = user_row[0]

                passcode_sent, email_error_msg = ecm.send_registration_confirmation_email(
                    user_id=user_id_registered,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )

                if email_error_msg:
                    print(
                        f"TODO: Registration for {email} succeeded, but sending confirmation email failed: {email_error_msg}")
                    response_dict = {
                        "status": "success_with_warning",
                        "user_id": user_id_registered,
                        "message": "Registration successful, but confirmation email could not be sent. Please contact support or try resending confirmation.",
                        "email_error_details": email_error_msg
                    }
                    http_status_code = 201  # Created, but with a follow-up needed
                elif passcode_sent:
                    response_dict = {
                        "status": "success",
                        "user_id": user_id_registered,
                        "message": "Registration successful! Please check your email to activate your account."
                    }
                    http_status_code = 201  # Created
                else:
                    # This case implies email sending was skipped due to config but no direct error raised by mailer
                    response_dict = {
                        "status": "success_with_warning",
                        "user_id": user_id_registered,
                        "message": "Registration successful. Email server not configured; confirmation email not sent. Account is inactive."
                    }
                    http_status_code = 201

    except psycopg2.errors.UniqueViolation:
        response_dict = {"status": "failed",
                         "reason": "This email address is already registered (encountered during insert)."}
        http_status_code = 409
    except Exception as e:
        print(f"TODO: Registration exception: {e}")
        # response_dict and http_status_code are already set to a default server error

    return response_dict, http_status_code


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


def change_password(user_id: int, data: dict):
    """
    Changes the password for a given user_id.
    Expects data: {"old_password": "<string>", "new_password": "<string>"}
    Returns (response_dict, http_status_code).
    """
    response_dict = {"status": "failed", "reason": "Password change failed due to an unexpected server error."}
    http_status_code = 500

    try:
        old_password = data.get("old_password")
        new_password = data.get("new_password")

        if not old_password or not new_password:
            response_dict = {"status": "failed", "reason": "Missing old_password or new_password."}
            http_status_code = 400
        elif not isinstance(user_id, int) or user_id <= 0:
            response_dict = {"status": "failed", "reason": "Invalid user_id."}
            http_status_code = 400
        else:
            with DB.get_cursor() as cur:
                cur.execute('SELECT password FROM "User" WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
                if result is None:
                    response_dict = {"status": "failed", "reason": "User not found."}
                    http_status_code = 404
                else:
                    stored_password_hash = result[0]
                    if not bcrypt.checkpw(old_password.encode('utf-8'), stored_password_hash.encode('utf-8')):
                        response_dict = {"status": "failed", "reason": "Incorrect old password."}
                        http_status_code = 401 # Unauthorized or 403 Forbidden could also be used
                    else:
                        new_hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        cur.execute(
                            'UPDATE "User" SET password = %s WHERE user_id = %s',
                            (new_hashed_password, user_id)
                        )
                        if cur.rowcount == 1:
                            response_dict = {"status": "success", "message": "Password changed successfully."}
                            http_status_code = 200
                        else:
                            # This case should ideally not be reached if user was found and old password matched,
                            # but it's a safeguard.
                            response_dict = {"status": "failed", "reason": "Failed to update password in database."}
                            # http_status_code remains 500
    except Exception as e:
        print(f"TODO: Change password exception for user_id {user_id}: {e}")
        # response_dict and http_status_code are already set to a default server error

    return response_dict, http_status_code
