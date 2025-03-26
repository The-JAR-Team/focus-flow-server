# playlist.py
from flask import Blueprint, request, jsonify
from db.db_api import *

playlist_bp = Blueprint('playlist', __name__)


def get_authenticated_user():
    """
    Reads the session_id cookie, validates the session,
    and returns the associated user_id.
    Returns (user_id, status_code) tuple.
    """
    session_id = request.cookies.get('session_id')
    if not session_id:
        return 0, 401  # No session cookie provided.
    user_id, status = get_user(session_id)
    return user_id, status


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
