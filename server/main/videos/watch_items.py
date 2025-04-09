from flask import Blueprint, request, jsonify
from db.db_api import log_watch_item, get_watch_item, get_all_videos_user_can_access, process_mediapipe_data
from logic.RuleBasedModel import RuleBasedModel
from server.main.utils import get_authenticated_user, check_authenticated_video

watch_items_bp = Blueprint('watch_items', __name__)


@watch_items_bp.route('/watch/get', methods=['POST'])
def get_watch():
    """
    Retrieves the watch item for the current user for a specified video.
    Expects JSON payload:
    {
      "youtube_id": <int>
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
        "extraction_payload": <json>,  # Payload for the extraction method
        "model": <string>           # Model used for extraction optional
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

    if status == 200:
        # Check if extraction method is specified
        extraction_method = data.get("extraction", "None")

        if extraction_method == "None":
            message = {
                "status": "failed",
                "message": "An extraction method must be specified"
            }
            status = 400

        elif extraction_method.lower() == "mediapipe":
            extraction_payload = data.get("extraction_payload")
            if not extraction_payload:
                message = {
                    "status": "failed",
                    "message": "Missing extraction payload"
                }
                status = 400
            else:
                # Get or create watch_item
                message, status = log_watch_item(user_id, {"youtube_id": youtube_id,
                                                                          "current_time": data.get("current_time",
                                                                                                   0.0)})
                if status == 200:
                    watch_item_id = message.get("watch_item_id")
                    # Process the mediapipe data
                    message, status = process_mediapipe_data(
                        watch_item_id,
                        data.get("current_time", 0.0),
                        extraction_payload
                    )

                    log_data_id = message.get("log_data_id")
                    model = data.get("model", None)
                    if model is not None:
                        if model.lower() == "basic":
                            attention_score = RuleBasedModel(extraction_payload, log_data_id)
                            message = {
                                "status": "success",
                                "message": f"Basic model is not ready yet, but this is how the payload would look like.",
                                "model_result": attention_score
                            }
                            status = 200

        else:
            # Unsupported extraction method
            message = {
                "status": "failed",
                "message": f"The extraction method '{extraction_method}' is not supported"
            }
            status = 400

    print(data.get("current_time", 0.0))
    return jsonify(message), status
