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
    Returns an HTML page indicating success or failure, with a redirect timer.
    """
    passcode = request.args.get('passcode')
    site_login_url = os.getenv('SITE_LOGIN_URL', 'http://localhost:3000/')

    # Enhanced HTML and CSS for a more modern look
    html_response_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Confirmation</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 20px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                min-height: 95vh; /* Adjusted for better centering */
                background-color: #eef2f7; /* Lighter, softer background */
                color: #334155; /* Slate text color */
                text-align: center;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }}
            .container {{
                background-color: #ffffff;
                padding: 40px 50px; /* Increased padding */
                border-radius: 12px; /* More rounded corners */
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08), 0 5px 10px rgba(0, 0, 0, 0.04); /* Softer shadow */
                max-width: 550px;
                width: 100%;
                border: 1px solid #e2e8f0; /* Subtle border */
            }}
            h1 {{
                margin-top: 0;
                margin-bottom: 20px; /* Space below h1 */
                font-size: 2.25em; /* Larger title */
                font-weight: 700; /* Bolder title */
                line-height: 1.2;
            }}
            .success h1 {{
                color: #10b981; /* Emerald green for success */
            }}
            .error h1 {{
                color: #ef4444; /* Red for error */
            }}
            p {{
                color: #475569; /* Slightly lighter text for paragraphs */
                font-size: 1.1em;
                line-height: 1.7;
                margin-bottom: 25px; /* More space below paragraphs */
            }}
            .redirect-message {{
                margin-top: 25px;
                font-size: 0.95em;
                color: #64748b; /* Lighter slate for redirect message */
            }}
            #countdown {{
                font-weight: 600;
                color: #334155;
            }}
            .button {{
                display: inline-block;
                padding: 14px 32px; /* Adjusted padding */
                margin-top: 15px; /* Space above button */
                background-color: #3b82f6; /* Tailwind blue-500 */
                color: white !important;
                text-decoration: none;
                border-radius: 8px; /* More rounded button */
                font-weight: 600;
                font-size: 1.05em;
                border: none;
                cursor: pointer;
                transition: background-color 0.2s ease-in-out, transform 0.1s ease-in-out;
                box-shadow: 0 4px 6px rgba(59, 130, 246, 0.2); /* Subtle shadow for button */
            }}
            .button:hover {{
                background-color: #2563eb; /* Tailwind blue-600 */
                transform: translateY(-1px); /* Slight lift on hover */
            }}
            .icon {{
                font-size: 3em;
                margin-bottom: 15px;
            }}
            .success .icon {{ color: #10b981; }}
            .error .icon {{ color: #ef4444; }}

        </style>
    </head>
    <body>
        <div class="container {status_class}">
            <div class="icon">{icon}</div>
            <h1>{title}</h1>
            <p>{message}</p>
            <button id="redirectButton" class="button">Proceed to Login</button>
            <p class="redirect-message">You will be redirected in <span id="countdown">10</span> seconds...</p>
        </div>
        <script>
            let countdown = 10;
            const countdownElement = document.getElementById('countdown');
            const redirectButton = document.getElementById('redirectButton');
            const loginUrl = "{login_url}"; // This will be replaced by Flask

            function redirectToLogin() {{
                window.location.href = loginUrl;
            }}

            redirectButton.onclick = redirectToLogin;

            const interval = setInterval(() => {{
                countdown--;
                if (countdownElement) {{
                    countdownElement.textContent = countdown;
                }}
                if (countdown <= 0) {{
                    clearInterval(interval);
                    redirectToLogin();
                }}
            }}, 1000);
        </script>
    </body>
    </html>
    """

    status_class_val = "error"
    title_val = "Confirmation Failed"
    message_val = "An unexpected error occurred."
    icon_val = "&#10060;"  # Cross mark (X)
    current_status_code = 400

    if not passcode:
        message_val = "Passcode query parameter is missing. Please use the link provided in your email."
        icon_val = "&#⚠️;"  # Warning sign
    else:
        response_data, status_code_from_ecm = ecm.confirm_user_email(passcode)
        current_status_code = status_code_from_ecm

        if status_code_from_ecm == 200 and response_data.get("status") == "success":
            status_class_val = "success"
            title_val = "Email Confirmed!"
            message_val = response_data.get("message", "Your account has been successfully activated.")
            icon_val = "&#10004;"  # Check mark
        else:
            message_val = response_data.get("reason",
                                            "An error occurred during confirmation. Please try again or contact support.")
            # icon_val remains cross mark or could be a specific error icon

    rendered_html = html_response_template.format(
        status_class=status_class_val,
        title=title_val,
        message=message_val,
        icon=icon_val,
        login_url=site_login_url
    )
    response = make_response(rendered_html, current_status_code)
    response.headers['Content-Type'] = 'text/html'
    return response
