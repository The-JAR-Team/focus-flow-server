from flask import Blueprint, request, jsonify

from db.buffer_manager import BufferManager
from db.db_api import log_watch_item, get_watch_item, process_mediapipe_data
from logic.RuleBasedModel import RuleBasedModel
from server.main.utils import get_authenticated_user, check_authenticated_video
try:
    # Adjust this path based on your project structure
    # Assumes model_test.py is inside logic/Models/ relative to where Flask runs
    from logic.model_test import (
        loaded_model,                   # The globally loaded model instance
        predict_engagement_dnn,         # The prediction function
        IDX_TO_NAME_MAP,                # Helper to map index -> class name
        DEVICE                          # The device the model is loaded on
    )
    # Check if the model actually loaded during import
    MODEL_V1_LOADED = loaded_model is not None
    if not MODEL_V1_LOADED:
         print("Warning: DNN Model v1 was imported but reported as not loaded.")

except ImportError as e:
    print(f"ERROR: Could not import components from logic.Models.model_test: {e}")
    print("       DNN model 'v1' will be unavailable.")
    loaded_model = None
    predict_engagement_dnn = None
    map_score_to_class_idx = None
    IDX_TO_NAME_MAP = {}
    MODEL_V1_LOADED = False
except NameError as e: # Catch if torch itself failed to import in model_test
     print(f"ERROR: NameError during import from logic.Models.model_test (likely PyTorch issue): {e}")
     MODEL_V1_LOADED = False # Ensure flag is False

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
                        elif model.lower() == "v1":
                            print("Running DNN Model v1...")
                            if not MODEL_V1_LOADED or predict_engagement_dnn is None:
                                # Check if the model failed to load when the server started
                                message = {"status": "failed",
                                                 "message": "Model v1 is not available on the server."}
                                status = 503  # Service Unavailable
                            else:
                                # Call the imported prediction function with the globally loaded model
                                predicted_score = predict_engagement_dnn(
                                    extraction_payload=extraction_payload,
                                    model=loaded_model,  # Pass the loaded model instance
                                    device=DEVICE,  # Pass the device it's loaded on
                                    log_data_id=log_data_id
                                )

                                if predicted_score is not None:
                                    # --- Prediction successful ---
                                    print(f"Predicted score: {predicted_score}")
                                    message = {
                                        "status": "success",
                                        "message": "DNN Model v1 prediction successful.",
                                        "model_name": "DNN_v1",
                                        "model_result": predicted_score,
                                    }
                                    status = 200
                                else:
                                    # --- Prediction failed ---
                                    message = {"status": "failed", "message": "DNN Model v1 prediction failed."}
                                    status = 500  # Internal Server Error

        else:
            # Unsupported extraction method
            message = {
                "status": "failed",
                "message": f"The extraction method '{extraction_method}' is not supported"
            }
            status = 400

    return jsonify(message), status
