# playlist.py
from flask import Blueprint, request, jsonify
from db.db_api import *
from server.main.utils import get_authenticated_user

playlist_bp = Blueprint('playlist', __name__)


@playlist_bp.route('/playlists', methods=['POST'])
def create():
    # Validate the session and retrieve user_id.
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    playlist_name = data.get("playlist_name", "general")
    playlist_permission = data.get("playlist_permission", "unlisted")

    if not playlist_name:
        return jsonify({"status": "failed", "reason": "missing playlist_name"}), 400

    response, status = create_playlist(user_id, playlist_name, playlist_permission)
    return jsonify(response), status


@playlist_bp.route('/playlists/<int:playlist_id>', methods=['DELETE'])
def delete(playlist_id):
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    response, status = delete_playlist(user_id, playlist_id)
    return jsonify(response), status


@playlist_bp.route('/playlists', methods=['GET'])
def get_all():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    response, status = get_all_user_playlists(user_id)
    return jsonify(response), status


@playlist_bp.route('/playlists/<int:playlist_id>/permission', methods=['PUT'])
def update_permission(playlist_id):
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    new_permission = data.get("new_permission")
    if not new_permission:
        return jsonify({"status": "failed", "reason": "missing new_permission"}), 400

    response, status = update_playlist_permission(user_id, playlist_id, new_permission)
    return jsonify(response), status

@playlist_bp.route('/playlists/update_name', methods=['PUT'])
def update_name():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    # update_playlist_name expects the user_id and a JSON payload containing "old_name" and "new_name".
    response, code = update_playlist_name(user_id, data)
    return jsonify(response), code
