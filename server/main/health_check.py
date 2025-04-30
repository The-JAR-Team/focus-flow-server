import os
from flask import Blueprint, request, jsonify
from server.main.utils import get_authenticated_user # Assuming this returns (response_or_none, user_id, status_code)

# Define the blueprint
health_check_bp = Blueprint('health_check', __name__)


@health_check_bp.route('/health', methods=['GET'])
def health_check():
    """
    Provides a health check endpoint, optionally requiring authentication.
    Returns the server state, version, and build timestamp (read from env vars).
    """
    response_payload = {"status": "failed"} # Default payload for internal errors
    status_code = 500 # Default status code for internal errors

    # --- Authentication ---
    # get_authenticated_user should return (None, user_id, 200) on success
    # and (response_object, None, status_code) on failure.
    auth_resp, user_id, auth_status = get_authenticated_user()

    # --- Check Authentication Result ---
    if auth_resp is not None:
        # If get_authenticated_user returned a response object (auth failed),
        # return that response directly.
        return auth_resp, auth_status
    else:
        # --- Authentication Succeeded ---
        # User is authenticated (user_id is valid), proceed to build success response.
        try:
            # --- Get Server Info from Environment Variables ---
            server_version = os.environ.get('SERVER_VERSION', 'unknown')
            build_timestamp = os.environ.get('BUILD_TIMESTAMP', 'not set')

            # --- Construct Success Response Payload (as a dictionary) ---
            response_payload = {
                "state": "running",
                "version": server_version,
                "build_timestamp": build_timestamp
            }
            status_code = 200

        except Exception as e:
            # Catch potential errors during environment variable access or dict creation
            print(f"Error constructing health check success response: {e}")
            response_payload = {"status": "failed", "message": "Internal server error during health check."}
            status_code = 500

    # --- Single Return Point ---
    # jsonify the dictionary payload constructed above.
    return jsonify(response_payload), status_code
