from datetime import timedelta

from flask import Blueprint, request, jsonify, make_response
from db.db_api import *
from server.main.utils import get_authenticated_user
import os
from dotenv import load_dotenv

auth_bp = Blueprint('auth', __name__)
load_dotenv()


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Handles user login, creates a session, and sets a session cookie.
    Optionally checks for a minimum permission level.
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "failed", "reason": "Invalid JSON payload"}), 400

    min_permission_str = request.args.get("min_permission", 0)
    try:
        min_permission = int(min_permission_str)
    except ValueError:
        return jsonify({"status": "failed", "reason": "Invalid min_permission value in query parameter"}), 400

    response, status, session_id = login_user(data)

    if status == 200:
        # Login successful, now check permission if required
        user_id = get_user(session_id)[0]
        if min_permission > 0:
            user_permission = get_permission(user_id)
            if user_permission < min_permission:
                print(f"Login denied for user_id {user_id}: insufficient permission (required: {min_permission}, has: {user_permission})")
                return jsonify({"status": "failed", "reason": "Insufficient permissions"}), 403 # Forbidden

        # Permission check passed (or not required)
        resp = jsonify(response)
        # Set the session_id cookie
        resp.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=True,
            samesite='none',
        )
        return resp, status
    else:
        # Login failed (wrong password, user not found, etc.)
        return jsonify(response), status


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # Expects JSON payload with registration fields.
    response, status = register_user(data)

    return jsonify(response), status


@auth_bp.route('/validate_session', methods=['GET'])
def validate_session_endpoint():
    """
    GET /validate_session

    Uses the get_authenticated_user helper to verify the session by reading the session_id cookie.
    If authentication fails, returns an error response (and clears the cookie).
    If successful, returns a success response with the session_id.
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status
    # If authentication succeeded, return a success message
    return jsonify({"status": "success", "reason": ""}), 200


@auth_bp.route('/user_info', methods=['GET'])
def user_info():
    """
    GET /user_info

    Retrieves all available information for the currently authenticated user.
    Returns a JSON structure like:
    {
      "status": "success",
      "user": {
         "user_id": <int>,
         "first_name": <str or null>,
         "last_name": <str or null>,
         "email": <str or null>,
         "age": <int or null>,
         "auth_token": <int or null>,
         "auth_last_used": <ISO formatted timestamp or null>
      }
    }
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    response, code = get_user_info(user_id)
    return jsonify(response), code


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    POST /logout

    Logs out the current session by removing it from the DB
    and clearing the session_id cookie on the client side.
    """
    # Get the session_id from the cookie
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"status": "failed", "reason": "No session cookie provided"}), 401

    # Call the DB function to remove the session
    response_dict, status_code = logout_user(session_id)

    # Build a response
    resp = jsonify(response_dict)
    # To fully clear the cookie from the client, set an empty value and/or expiration in the past
    resp.set_cookie("session_id", "", expires=0, httponly=True, secure=True, samesite='none')
    return resp, status_code


@auth_bp.route('/change_password', methods=['POST'])
def change_password_endpoint():
    """
    Allows an authenticated user (min_permission=1) to change their password.
    Expects JSON: {"old_password": "current_password", "new_password": "new_secure_password"}
    """
    resp_from_auth, user_id, status_from_auth = get_authenticated_user(min_permission=1)
    if resp_from_auth is not None:
        return resp_from_auth  # Authentication or permission failure

    data = request.get_json()
    if not data:
        return jsonify({"status": "failed", "reason": "Invalid JSON payload"}), 400

    # change_password function is expected to be available from 'from db.db_api import *'
    # which should import it from user_management.py
    response_data, status_code = change_password(user_id, data)

    return jsonify(response_data), status_code


@auth_bp.route('/confirm_email', methods=['GET'])
def confirm_email_endpoint():
    """
    Confirms a user's email address using a passcode from a query parameter.
    Example: GET /confirm_email?passcode=YOUR_PASSCODE_HERE
    Returns an HTML page indicating success or failure.
    """
    passcode = request.args.get('passcode')
    html_response_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Confirmation</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; background-color: #f4f7f6; text-align: center; }}
            .container {{ background-color: #fff; padding: 30px 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            h1 {{ margin-top: 0; }}
            .success h1 {{ color: #28a745; }}
            .error h1 {{ color: #dc3545; }}
            p {{ color: #555; font-size: 1.1em; }}
            a {{ color: #007bff; text-decoration: none; font-weight: bold; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container {status_class}">
            <h1>{title}</h1>
            <p>{message}</p>
        </div>
    </body>
    </html>
    """

    if not passcode:
        # Render error HTML for missing passcode
        rendered_html = html_response_template.format(
            status_class="error",
            title="Confirmation Failed",
            message="Passcode query parameter is missing. Please use the link provided in your email."
        )
        response = make_response(rendered_html, 400)
        response.headers['Content-Type'] = 'text/html'
        return response

    # confirm_user_email is from email_confirmation_management.py
    response_data, status_code = ecm.confirm_user_email(passcode)

    if status_code == 200 and response_data.get("status") == "success":
        rendered_html = html_response_template.format(
            status_class="success",
            title="Email Confirmed!",
            message=response_data.get("message", "Your account has been successfully activated.")
        )
    else:
        rendered_html = html_response_template.format(
            status_class="error",
            title="Confirmation Failed",
            message=response_data.get("reason",
                                      "An error occurred during confirmation. Please try again or contact support.")
        )

    response = make_response(rendered_html, status_code)
    response.headers['Content-Type'] = 'text/html'
    return response
