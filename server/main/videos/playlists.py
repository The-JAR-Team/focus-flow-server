from flask import Blueprint, request, jsonify
from db.db_api import *
from server.main.utils import get_authenticated_user

playlist_bp = Blueprint('playlist', __name__)


@playlist_bp.route('/playlists', methods=['POST'])
def create():
    resp, user_id, status = get_authenticated_user(min_permission=1)
    if resp is not None:
        return resp, status

    data = request.get_json()
    playlist_name = data.get("playlist_name", "general")
    playlist_permission = data.get("playlist_permission", "unlisted")

    if not playlist_name:
        return jsonify({"status": "failed", "reason": "missing playlist_name"}), 400

    response, status = create_playlist(user_id, playlist_name, playlist_permission)
    return jsonify(response), status


@playlist_bp.route('/playlists/<int:playlist_id>', methods=['DELETE'])
def delete(playlist_id):
    resp, user_id, status = get_authenticated_user(min_permission=1)
    if resp is not None:
        return resp, status

    response, status = delete_playlist(user_id, playlist_id)
    return jsonify(response), status


@playlist_bp.route('/playlists', methods=['GET'])
def get_all():
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    response, status = get_all_user_playlists(user_id)
    return jsonify(response), status


@playlist_bp.route('/playlists/<int:playlist_id>/permission', methods=['PUT'])
def update_permission(playlist_id):
    resp, user_id, status = get_authenticated_user(min_permission=1)
    if resp is not None:
        return resp, status

    data = request.get_json()
    new_permission = data.get("new_permission")
    if not new_permission:
        return jsonify({"status": "failed", "reason": "missing new_permission"}), 400

    response, status = update_playlist_permission(user_id, playlist_id, new_permission)
    return jsonify(response), status


@playlist_bp.route('/playlists/update_name', methods=['PUT'])
def update_name():
    resp, user_id, status = get_authenticated_user(min_permission=1)
    if resp is not None:
        return resp, status

    data = request.get_json()
    response, code = update_playlist_name(user_id, data)
    return jsonify(response), code


@playlist_bp.route('/playlists/<int:playlist_id>/subscribers', methods=['GET'])
def get_subscribers(playlist_id):
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    response_data, code = get_playlist_subscribers(user_id, playlist_id)
    return jsonify(response_data), code


@playlist_bp.route('/playlists/<int:playlist_id>/subscriber_count', methods=['GET'])
def get_subscriber_count(playlist_id):
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    response_data, code = get_playlist_subscriber_count(user_id, playlist_id)
    return jsonify(response_data), code


@playlist_bp.route('/playlists/item/<int:playlist_item_id>/order', methods=['PUT'])
def update_order(playlist_item_id):
    """
    Updates the order of a specific playlist item.
    Expects a JSON payload: {"new_order": <integer>}
    """
    resp, user_id, status = get_authenticated_user(min_permission=1)
    if resp is not None:
        return resp, status

    data = request.get_json()
    new_order = data.get("new_order")

    if new_order is None:
        return jsonify({"status": "failed", "reason": "missing new_order"}), 400

    response, status = update_playlist_item_order(user_id, playlist_item_id, new_order)
    return jsonify(response), status
