from flask import Blueprint, request, jsonify
from server.main.utils import get_authenticated_user  # Assuming utils.py is in server.main
import db.db_api as db_api  # Assuming all your db functions are accessible via db_api

groups_bp = Blueprint('groups', __name__)

# Standard minimum permission level for group operations
MIN_PERMISSION_LEVEL = 1


@groups_bp.route('', methods=['POST'])
def create_new_group():
    """
        Endpoint to create a new group.
        Payload: {"group_name": <string>, "description": <string (optional)>}
        """
    response_payload = {"status": "failed", "reason": "Group creation failed"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "reason": "Invalid JSON payload"}
        status_code = 400
    else:
        # Call the assumed db_api function
        response_payload, status_code = db_api.create_group(data, user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('', methods=['PUT'])
def update_existing_group():
    """
        Endpoint to update an existing group.
        Payload: {"old_group_name": <string>, "new_group_name": <string (optional)>, "new_description": <string (optional)>}
        """
    response_payload = {"status": "failed", "reason": "Group update failed"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "reason": "Invalid JSON payload"}
        status_code = 400
    else:
        response_payload, status_code = db_api.update_group(data, user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('/names', methods=['GET'])
def get_user_group_names():
    """
        Endpoint to retrieve all group names and basic details for the authenticated user.
        """
    response_payload = {"status": "failed", "reason": "Failed to retrieve group names"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    response_payload, status_code = db_api.get_group_names(user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('', methods=['GET'])
def get_all_user_groups_with_items():
    """
        Endpoint to retrieve all groups and their items (videos, playlists) for the authenticated user.
        """
    response_payload = {"status": "failed", "reason": "Failed to retrieve groups"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    response_payload, status_code = db_api.get_groups(user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('/<string:group_name>', methods=['GET'])
def get_specific_group_with_items(group_name):
    """
        Endpoint to retrieve a specific group by name, including its items.
        """
    response_payload = {"status": "failed", "reason": "Failed to retrieve group"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    if not group_name:
        response_payload = {"status": "failed", "reason": "group_name parameter is required"}
        status_code = 400
    else:
        response_payload, status_code = db_api.get_group(user_id, group_name)

    return jsonify(response_payload), status_code


@groups_bp.route('/<string:group_name>', methods=['DELETE'])
def delete_specific_group(group_name):
    """
        Endpoint to delete a specific group by name.
        Payload (optional, but good for consistency if other DELETEs use it): {"group_name": <string>}
        Alternatively, group_name is taken from the URL.
        """
    response_payload = {"status": "failed", "reason": "Failed to remove group"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    # The group_management.remove_group function expects a data dictionary
    data = {"group_name": group_name}
    response_payload, status_code = db_api.remove_group(data, user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('/items', methods=['POST'])
def add_item_to_group_endpoint():
    """
        Endpoint to add an item (video or playlist) to a group.
        If the group doesn't exist, it's created.
        Payload: {"group_name": <string>, "item_type": <"video" or "playlist">, "item_id": <int>}
        """
    response_payload = {"status": "failed", "reason": "Failed to add item to group"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "reason": "Invalid JSON payload"}
        status_code = 400
    else:
        response_payload, status_code = db_api.insert_group_item(data, user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('/items', methods=['DELETE'])
def remove_item_from_group_endpoint():
    """
        Endpoint to remove an item (video or playlist) from a group.
        Payload: {"group_name": <string>, "item_type": <"video" or "playlist">, "item_id": <int>}
        """
    response_payload = {"status": "failed", "reason": "Failed to remove item from group"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "reason": "Invalid JSON payload"}
        status_code = 400
    else:
        response_payload, status_code = db_api.remove_group_item(data, user_id)

    return jsonify(response_payload), status_code


@groups_bp.route('/items/switch_order', methods=['PATCH'])  # Using PATCH as it's a partial update
def switch_group_item_order_endpoint():
    """
        Endpoint to switch the order of two items within a group.
        Payload: {
            "group_name": <string>,
            "item_type": <"video" or "playlist">,
            "order1": <int>,
            "order2": <int>
        }
        """
    response_payload = {"status": "failed", "reason": "Failed to switch item order"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=MIN_PERMISSION_LEVEL)
    if auth_resp:
        return auth_resp, auth_status

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "reason": "Invalid JSON payload"}
        status_code = 400
    else:
        response_payload, status_code = db_api.switch_group_item_placement(data, user_id)

    return jsonify(response_payload), status_code