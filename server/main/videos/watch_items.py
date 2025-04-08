from flask import Blueprint, request, jsonify
from db.db_api import log_watch_item, get_watch_item, get_all_videos_user_can_access
from server.main.utils import get_authenticated_user, check_authenticated_video

watch_items_bp = Blueprint('watch_items', __name__)


@watch_items_bp.route('/videos/log_watch', methods=['POST'])
def log_watch():
    resp, user_id, status = get_authenticated_user()
    # if resp is not None:
    #     return resp, status
    #
    # data = request.get_json()
    # # log_watch expects the user_id and a JSON payload containing the video_id.
    # response, code = log_watch(user_id, data)
    return resp, status


@watch_items_bp.route('/watch/get', methods=['POST'])
def get_watch():
    """
    Retrieves the watch item for the current user for a specified video.
    Expects JSON payload:
    {
      "video_id": <int>
    }
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    response, code = get_watch_item(user_id, data)
    return jsonify(response), code


@watch_items_bp.route('/watch/log_watch', methods=['POST'])
def watch_log_watch():
    """
    Logs watch data with facial landmark extraction data.

    Expected JSON payload:
    {
        "youtube_id": <string>,          # YouTube video ID
        "current_time": <float>,       # Current playback time in seconds
        "extraction": <string>,        # Extraction method (e.g., "mediapipe")
        "extraction_payload": <dict>,  # Payload for the extraction method
    }

    Returns:
        JSON response indicating success or failure
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    youtube_id = data.get("youtube_id")

    message, status = check_authenticated_video(youtube_id, user_id)
    if status != 200:
        return jsonify(message), status

    # Check if extraction method is specified
    extraction_method = data.get("extraction")
    if not extraction_method:
        return jsonify({
            "status": "no extraction was selected",
            "message": "An extraction method must be specified"
        }), 200

    # Handle based on extraction method
    if extraction_method.lower() == "mediapipe":
        # Process mediapipe data
        # This will be implemented separately
        # process_mediapipe_data(user_id, data)

        # For now, just return success
        return jsonify({
            "status": "success",
            "message": "Mediapipe data received and will be processed"
        }), 200
    else:
        # Unsupported extraction method
        return jsonify({
            "status": "extraction not implemented yet!",
            "message": f"The extraction method '{extraction_method}' is not supported yet"
        }), 200
