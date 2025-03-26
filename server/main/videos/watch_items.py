# watch_items.py
from flask import Blueprint, request, jsonify
from db.db_api import log_watch_item, get_watch_item
from server.main.utils import get_authenticated_user

watch_items_bp = Blueprint('watch_items', __name__)

@watch_items_bp.route('/watch/log', methods=['POST'])
def log_watch():
    """
    Logs or updates the watch data for the current user.
    Expects JSON payload:
    {
      "video_id": <int>,
      "current_watch_time": <int>,
      "time_before_jump": <int>
    }
    """
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    response, code = log_watch_item(user_id, data)
    return jsonify(response), code

@watch_items_bp.route('/watch/get', methods=['POST'])
def get_watch():
    """
    Retrieves the watch item for the current user for a specified video.
    Expects JSON payload:
    {
      "video_id": <int>
    }
    """
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    response, code = get_watch_item(user_id, data)
    return jsonify(response), code
