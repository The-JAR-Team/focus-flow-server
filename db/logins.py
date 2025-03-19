from db.DB import DB
from datetime import datetime, timedelta


def login_user(data):
    """
    Login function:
    Expects:
      {
         "email": <string>,
         "password": <string>
      }
    On successful login, updates auth_token and auth_last_used.
    Returns a tuple: (response_dict, http_status_code)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return ({"status": "failed", "reason": "missing email or password", "auth_token": 0}, 401)

        # Check for the user by email.
        cur.execute('SELECT user_id, password FROM "User" WHERE email = %s', (email,))
        result = cur.fetchone()
        if result is None:
            return ({"status": "failed", "reason": "no such user is signed in", "auth_token": 0}, 401)
        user_id, stored_password = result
        if stored_password != password:
            return ({"status": "failed", "reason": "incorrect password", "auth_token": 0}, 401)

        # Login successful.
        # Generate a new auth token by forcing an update to use nextval from auth_token_seq.
        cur.execute(
            'UPDATE "User" SET auth_token = nextval(\'auth_token_seq\'), auth_last_used = NOW() WHERE user_id = %s RETURNING auth_token, auth_last_used',
            (user_id,)
        )
        new_token, last_used = cur.fetchone()
        conn.commit()

        return ({"status": "success", "reason": "", "auth_token": new_token}, 200)

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed login", "auth_token": 0}, 401


def register_user(data):
    """
    Registers a new user and then logs them in.

    Expected input data:
      {
         "email": <string>,
         "password": <string>,
         "first name": <string>,
         "last name": <string>,
         "age": <int>
      }
    Returns a tuple: (response_dict, http_status_code)
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
            return ({"status": "failed", "reason": "missing required registration fields", "auth_token": 0}, 401)

        # Check if a user with this email already exists.
        cur.execute('SELECT user_id FROM "User" WHERE email = %s', (email,))
        if cur.fetchone():
            return ({"status": "failed", "reason": "user already exists", "auth_token": 0}, 401)

        # Insert the new user into the database.
        cur.execute(
            'INSERT INTO "User" (first_name, last_name, email, password, age) VALUES (%s, %s, %s, %s, %s)',
            (first_name, last_name, email, password, age)
        )
        conn.commit()

        # After successful registration, use the login method to generate an auth token.
        return login_user({"email": email, "password": password})
    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed registration", "auth_token": 0}, 401


def validate_auth_token(token):
    """
    Validates the provided auth token.
    - The token is valid if its auth_last_used is within the last 3 days.
    - If valid, auth_last_used is updated to now.
    - If not, a "loggedout" status is returned.

    Returns a tuple: (response_dict, http_status_code)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Look up the token in the User table.
        cur.execute('SELECT user_id, auth_last_used FROM "User" WHERE auth_token = %s', (token,))
        result = cur.fetchone()
        if result is None:
            # No such token found.
            return ({"status": "failed", "reason": "invalid token", "auth_token": 0}, 401)

        user_id, last_used = result
        now = datetime.utcnow()
        # Check if token was used within the last 3 days.
        if last_used is None or now - last_used > timedelta(days=3):
            return ({"status": "failed", "reason": "loggedout", "auth_token": 0}, 401)

        # If token is valid, update auth_last_used to extend the session.
        cur.execute('UPDATE "User" SET auth_last_used = NOW() WHERE user_id = %s', (user_id,))
        conn.commit()

        return ({"status": "success", "reason": "", "auth_token": token}, 200)

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed token validation", "auth_token": 0}, 401
