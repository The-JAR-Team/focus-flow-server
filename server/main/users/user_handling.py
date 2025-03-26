from flask import Blueprint, request, jsonify
from db.db_api import *
from server.main.utils import get_authenticated_user
from server.proxies.db_proxy import proxy_logins_api
import os
from dotenv import load_dotenv

auth_bp = Blueprint('auth', __name__)
load_dotenv()
mode = os.environ.get('MODE')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()  # Expects JSON payload with "email" and "password"
    response, status, session_id = proxy_logins_api(login_user, data, mode)

    if status == 200:
        resp = jsonify(response)
        # Set the session_id cookie
        resp.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=True,  # set to True if using HTTPS
            samesite='none'  # adjust as needed
        )
        return resp, status
    return jsonify(response), status


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # Expects JSON payload with registration fields.
    response, status, session_id = proxy_logins_api(register_user, data, mode)

    if status == 200:
        resp = jsonify(response)
        # Set the session_id cookie upon successful registration
        resp.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=True,
            samesite='none'
        )
        return resp, status

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
