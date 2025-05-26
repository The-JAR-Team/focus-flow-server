import os
import numpy as np
from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any

from db.db_api import log_watch_item, get_watch_item, process_mediapipe_data, get_model_results_by_video, log_watch_batch_client_tickets
from logic.RuleBasedModel import RuleBasedModel # Keep if 'basic' model is used
from server.main.utils import get_authenticated_user, check_authenticated_video

from logic.model_test import (
        predict_engagement_onnx,
        # map_score_to_class_details is used within predict_engagement_onnx
        # load_onnx_sessions # If you prefer to load sessions here instead of them being loaded in model_test globally
        onnx_session_v1 as onnx_session_v1_loaded, # Session for V1 model
        onnx_session_v4 as onnx_session_v4_loaded  # Session for V4 model
    )
from server.main.videos.ticket import ticket_route_authenticator

MODEL_V1_LOADED = onnx_session_v1_loaded is not None
MODEL_V4_LOADED = onnx_session_v4_loaded is not None
watch_items_bp = Blueprint('watch_items', __name__)


@watch_items_bp.route('/watch/get', methods=['POST'])
def get_watch():
    """
    Retrieves the watch item for the current user for a specified video.
    (This function is from the user-provided watch_items.py)
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    # Assuming get_watch_item is defined in your db.db_api
    response, code = get_watch_item(user_id, data)
    return jsonify(response), code


@watch_items_bp.route('/watch/log_watch', methods=['POST'])
def watch_log_watch():
    """
    Logs watch data, processes landmarks, and runs selected model inference.
    Supports ONNX models v1 and v4.

    Expected JSON payload:
    {
        "youtube_id": <string>,
        "current_time": <float>,
        "extraction": <string>,        # e.g., "mediapipe"
        "extraction_payload": <json_string_or_dict>, # landmarks data
        "model": <string>              # e.g., "basic", "v1", "v4" (optional)
    }

    Returns:
        JSON response indicating success or failure, including model results.
    """
    resp, user_id, auth_status = get_authenticated_user()
    if resp is not None:
        return jsonify(resp), auth_status

    data = request.get_json()
    if not data:
        return jsonify({"status": "failed", "message": "Invalid JSON payload."}), 400

    youtube_id = data.get("youtube_id")
    current_time = data.get("current_time", 0.0)
    extraction_method = data.get("extraction", "None")
    extraction_payload = data.get("extraction_payload") # This will be dict if payload is JSON
    model_choice = data.get("model")

    message = {}
    status = 500 # Default to internal server error

    # --- Authenticate Video ---
    # Assuming check_authenticated_video is defined in your server.main.utils
    vid_message, vid_status = check_authenticated_video(youtube_id, user_id)
    if vid_status != 200:
        message = vid_message
        status = vid_status
    # --- Validate Input ---
    elif extraction_method == "None":
        message = {"status": "failed", "message": "An extraction method must be specified"}
        status = 400
    elif extraction_method.lower() != "mediapipe":
         message = {"status": "failed", "message": f"The extraction method '{extraction_method}' is not supported"}
         status = 400
    elif not extraction_payload:
        message = {"status": "failed", "message": "Missing extraction payload for mediapipe"}
        status = 400
    else:
        # --- Log Watch Item and Process Data ---
        # Assuming log_watch_item is defined in your db.db_api
        log_resp, log_status = log_watch_item(user_id, {"youtube_id": youtube_id, "current_time": current_time})
        if log_status != 200:
            message = log_resp
            status = log_status
        else:
            watch_item_id = log_resp.get("watch_item_id")
            # Assuming process_mediapipe_data is defined in your db.db_api
            process_resp, process_status = process_mediapipe_data(
                watch_item_id, current_time, extraction_payload
            )
            if process_status != 200:
                message = process_resp
                status = process_status
            else:
                log_data_id = process_resp.get("log_data_id")
                if log_data_id is None:
                    message = {"status": "failed", "message": "Failed to get log_data_id after processing."}
                    status = 500
                else:
                    # --- Model Inference ---
                    if predict_engagement_onnx is None: # Check if import failed
                        message = {"status": "failed", "message": "ONNX prediction function not loaded."}
                        status = 503
                    elif model_choice is None:
                        message = {"status": "success", "message": "Data processed successfully (no model specified)."}
                        status = 200
                    elif model_choice.lower() == "basic":
                        # Assuming RuleBasedModel is correctly imported
                        attention_score = RuleBasedModel(extraction_payload, log_data_id)
                        message = {
                            "status": "success",
                            "message": "Basic model processing complete.",
                            "model_name": "Basic",
                            "model_result": attention_score
                        }
                        status = 200
                    elif model_choice.lower() == "v1":
                        print("Running ONNX Model v1...")
                        if not MODEL_V1_LOADED:
                            message = {"status": "failed", "message": "Model v1 (ONNX) is not available on the server."}
                            status = 503
                        else:
                            prediction_output = predict_engagement_onnx(
                                extraction_payload_str=extraction_payload, # Will be handled as dict by predict_engagement_onnx
                                model_version="v1",
                                log_data_id=log_data_id,
                                session_v1=onnx_session_v1_loaded,
                                session_v4=onnx_session_v4_loaded # Pass both, function will pick
                            )
                            if prediction_output is not None:
                                message = {
                                    "status": "success",
                                    "message": "ONNX Model v1 prediction successful.",
                                    "model_name": "DNN_v1_ONNX",
                                    "model_result": prediction_output.get('score', -1.0),
                                    "model_result_class_name": prediction_output.get('name', "Unknown"),
                                }
                                status = 200
                            else:
                                message = {"status": "failed", "message": "ONNX Model v1 prediction failed."}
                                status = 500
                    elif model_choice.lower() == "v4":
                        print("Running ONNX Model v4...")
                        if not MODEL_V4_LOADED:
                            message = {"status": "failed", "message": "Model v4 (ONNX) is not available on the server."}
                            status = 503
                        else:
                            prediction_output = predict_engagement_onnx(
                                extraction_payload_str=extraction_payload, # Will be handled as dict
                                model_version="v4",
                                log_data_id=log_data_id,
                                session_v1=onnx_session_v1_loaded,
                                session_v4=onnx_session_v4_loaded # Pass both, function will pick
                            )
                            if prediction_output is not None:
                                message = {
                                    "status": "success",
                                    "message": "ONNX Model v4 prediction successful.",
                                    "model_name": "DNN_v4_ONNX",
                                    "model_result": prediction_output.get('score', -1.0),
                                    "model_result_class_name": prediction_output.get('name', "Unknown"),
                                    "classification_head_result": prediction_output.get('classification_head_name', "Unknown"),
                                    "classification_head_index": prediction_output.get('classification_head_index', -1),
                                }
                                status = 200
                            else:
                                message = {"status": "failed", "message": "ONNX Model v4 prediction failed."}
                                status = 500
                    else:
                        message = {"status": "failed", "message": f"Model '{model_choice}' is not supported."}
                        status = 400
    # Final return
    return jsonify(message), status


@watch_items_bp.route('/watch/get_results', methods=['GET'])
def watch_get_results():
    """
    Retrieves model results for a specific YouTube video via GET request.
    (This function is from the user-provided watch_items.py)
    """
    response_payload = {"status": "failed"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user()
    if auth_resp is not None:
        response_payload = auth_resp
        status_code = auth_status
    else:
        youtube_id = request.args.get("youtube_id")
        option = request.args.get("option", "alone").lower()

        if not youtube_id:
             response_payload = {"status": "failed", "message": "Missing 'youtube_id' query parameter."}
             status_code = 400
        elif option not in ["all", "alone"]:
             response_payload = {"status": "failed", "message": "Invalid 'option' query parameter. Must be 'all' or 'alone'."}
             status_code = 400
        else:
            vid_message, vid_status = check_authenticated_video(youtube_id, user_id)
            if vid_status != 200:
                response_payload = vid_message
                status_code = vid_status
            else:
                # Assuming get_model_results_by_video is defined in your db.db_api
                results_data, results_status = get_model_results_by_video(youtube_id)
                if results_status != 200:
                    response_payload = results_data
                    status_code = results_status
                else:
                    final_results = {}
                    all_results = results_data.get("results_by_user", {})
                    if option == "all":
                        final_results = all_results
                    elif option == "alone":
                        final_results = {user_id: all_results[user_id]} if user_id in all_results else {}
                    response_payload = {
                        "status": "success",
                        "youtube_id": youtube_id,
                        "option": option,
                        "results_by_user": final_results
                    }
                    status_code = 200
    return jsonify(response_payload), status_code


@watch_items_bp.route('/watch/log_watch_batch', methods=['POST'])
@ticket_route_authenticator(min_permission_level=1)
def log_watch_batch_route(user_id, session_id,
                          common_youtube_id_from_decorator):  # Names must match what decorator passes
    """
    Logs a batch of watch data items with client-provided tickets.
    The decorator handles user authentication, session_id retrieval,
    and common_youtube_id extraction and validation.
    """
    response_data = {"status": "failed"}
    status_code = 400  # Default to Bad Request for payload issues

    data = request.get_json()
    if not data:
        # This case should ideally be caught by the decorator if it checks for data to get youtube_id,
        # but as a safeguard or if decorator logic changes.
        response_data["reason"] = "Invalid or missing JSON payload."
        return jsonify(response_data), status_code

    # Extract batch-level information from the validated top-level JSON
    batch_current_time_video = data.get("batch_current_time_video")
    common_model_name = data.get("model_name")  # Optional
    items_data_array = data.get("items")

    # Validate required batch-level fields
    if not isinstance(batch_current_time_video, (int, float)):
        response_data["reason"] = "Missing or invalid 'batch_current_time_video'."
        return jsonify(response_data), status_code
    if not isinstance(items_data_array, list):
        response_data["reason"] = "Missing or invalid 'items' array in payload."
        return jsonify(response_data), status_code

    # common_youtube_id_from_decorator is the youtube_id extracted by the decorator
    # from the top level of the JSON payload.

    # Call the DB API function to process the batch
    result_dict, result_status_code = log_watch_batch_client_tickets(
        user_id=user_id,
        session_id=session_id,
        common_youtube_id=common_youtube_id_from_decorator,
        batch_current_time_video=batch_current_time_video,
        common_model_name=common_model_name,
        items_data_array=items_data_array
    )

    return jsonify(result_dict), result_status_code
