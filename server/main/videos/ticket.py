from functools import wraps
from flask import Blueprint, request, jsonify

# Assuming your ticket_management functions are now directly in db_api
# If ticket_management.py is a separate file in 'db' directory, use:
# from db import ticket_management
# and then call ticket_management.set_next_ticket etc.
from db.db_api import set_next_ticket, set_next_sub_ticket, get_tickets
from server.main.utils import get_authenticated_user, check_authenticated_video  # Assuming utils.py location

tickets_bp = Blueprint('tickets', __name__)


# Decorator for common authentication and data validation logic
def ticket_route_authenticator(min_permission_level=1):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response_data = {"status": "failed"}
            # status_code = 500 # Default status code handled by Flask or specific returns
            user_id = None
            session_id_from_cookie = None
            youtube_id_from_request = None

            auth_resp, u_id, auth_status = get_authenticated_user(min_permission=min_permission_level)
            if auth_resp is not None:
                return auth_resp, auth_status  # auth_resp is already a Flask Response

            user_id = u_id
            session_id_from_cookie = request.cookies.get('session_id')
            if not session_id_from_cookie:
                response_data["reason"] = "Session ID cookie not found after authentication."
                return jsonify(response_data), 401

            if request.method == 'POST':
                data = request.get_json()
                if not data:
                    response_data["reason"] = "Invalid JSON payload."
                    return jsonify(response_data), 400
                youtube_id_from_request = data.get("youtube_id")
            elif request.method == 'GET':
                youtube_id_from_request = request.args.get("youtube_id")

            if not youtube_id_from_request:
                response_data["reason"] = "Missing 'youtube_id'."
                return jsonify(response_data), 400

            vid_message, vid_status = check_authenticated_video(youtube_id_from_request, user_id)
            if vid_status != 200:
                return jsonify(vid_message), vid_status  # vid_message is expected to be a dict

            # Pass validated data to the route function
            return f(user_id, session_id_from_cookie, youtube_id_from_request, *args, **kwargs)

        return decorated_function

    return decorator


@tickets_bp.route('/ticket/next', methods=['POST'])
@ticket_route_authenticator(min_permission_level=1)
def set_main_ticket_route(user_id, session_id, youtube_id):  # Parameters from decorator
    """
    Sets the next main ticket for a given youtube_id and the session_id from cookie.
    Resets sub_ticket to 1.
    Requires min_permission=1.
    """
    response_data = {"status": "failed"}
    status_code = 500  # Default to internal server error

    # Call the ticket management function, which now returns a dict or None
    ticket_info = set_next_ticket(user_id, session_id, youtube_id)

    if ticket_info and isinstance(ticket_info, dict):
        response_data = {
            "status": "success",
            "message": "Next main ticket set successfully.",
            "main_ticket": ticket_info.get("main_ticket"),
            "sub_ticket": ticket_info.get("sub_ticket")
        }
        status_code = 200
    else:
        response_data["reason"] = "Failed to set next main ticket."
        # status_code remains 500 or could be more specific if ticket_management indicated why

    return jsonify(response_data), status_code


@tickets_bp.route('/ticket/next_sub', methods=['POST'])
@ticket_route_authenticator(min_permission_level=1)
def set_sub_ticket_route(user_id, session_id, youtube_id):  # Parameters from decorator
    """
    Sets the next sub-ticket for a given youtube_id and the session_id from cookie.
    If no main ticket exists, a new one is created with sub_ticket 1.
    Requires min_permission=1.
    """
    response_data = {"status": "failed"}
    status_code = 500

    # Call the ticket management function, which now returns a dict or None
    ticket_info = set_next_sub_ticket(user_id, session_id, youtube_id)

    if ticket_info and isinstance(ticket_info, dict):
        response_data = {
            "status": "success",
            "message": "Next sub-ticket set successfully.",
            "main_ticket": ticket_info.get("main_ticket"),
            "sub_ticket": ticket_info.get("sub_ticket")
        }
        status_code = 200
    else:
        response_data["reason"] = "Failed to set next sub-ticket."
        status_code = 500

    return jsonify(response_data), status_code


@tickets_bp.route('/ticket/current', methods=['GET'])
@ticket_route_authenticator(min_permission_level=1)
def get_current_tickets_route(user_id, session_id, youtube_id):  # Parameters from decorator
    """
    Gets the current main and sub-tickets for a given youtube_id (from query param)
    and session_id from cookie.
    Requires min_permission=1.
    """
    response_data = {"status": "failed"}
    status_code = 500

    main_ticket, sub_ticket = get_tickets(session_id, youtube_id)

    if main_ticket is not None and sub_ticket is not None:
        response_data = {
            "status": "success",
            "main_ticket": main_ticket,
            "sub_ticket": sub_ticket
        }
        status_code = 200
    else:
        response_data["reason"] = "Tickets not found or error retrieving tickets."
        status_code = 404

    return jsonify(response_data), status_code
