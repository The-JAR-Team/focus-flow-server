import os
import numpy as np
from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any
# --- Database and Authentication Imports ---
# Assuming these exist and work as before
from db.db_api import log_watch_item, get_watch_item, process_mediapipe_data, get_model_results_by_video
from logic.RuleBasedModel import RuleBasedModel # Keep if 'basic' model is used
from server.main.utils import get_authenticated_user, check_authenticated_video

# --- ONNX Model Imports ---
# Import components from the ONNX inference script (onnx_inference_script.py)
# Ensure this file is accessible in your Python path
from logic.model_test import (
    onnx_session,                   # The globally loaded ONNX session instance
    predict_engagement_onnx,         # The ONNX prediction function
    map_score_to_class_details
)
MODEL_V1_LOADED = onnx_session is not None
if not MODEL_V1_LOADED:
     print("Warning: ONNX Model v1 session was imported but reported as not loaded.")

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
    Logs watch data, processes landmarks, and runs selected model inference (ONNX for v1).

    Expected JSON payload:
    {
        "youtube_id": <string>,
        "current_time": <float>,
        "extraction": <string>,        # e.g., "mediapipe"
        "extraction_payload": <json>,
        "model": <string>              # e.g., "basic", "v1" (optional)
    }

    Returns:
        JSON response indicating success or failure, including model results.
    """
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    if not data:
        return jsonify({"status": "failed", "message": "Invalid JSON payload."}), 400

    youtube_id = data.get("youtube_id")
    current_time = data.get("current_time", 0.0)
    extraction_method = data.get("extraction", "None")
    extraction_payload = data.get("extraction_payload")
    model_choice = data.get("model") # Can be None

    message, status = check_authenticated_video(youtube_id, user_id)
    if status != 200:
        return jsonify(message), status

    # --- Validate Input ---
    if extraction_method == "None":
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
        log_resp, log_status = log_watch_item(user_id, {"youtube_id": youtube_id, "current_time": current_time})
        if log_status != 200:
            return jsonify(log_resp), log_status # Return error from logging

        watch_item_id = log_resp.get("watch_item_id")
        process_resp, process_status = process_mediapipe_data(
            watch_item_id, current_time, extraction_payload
        )
        if process_status != 200:
             return jsonify(process_resp), process_status # Return error from processing

        log_data_id = process_resp.get("log_data_id")
        if log_data_id is None:
             # Should not happen if process_mediapipe_data succeeds, but good to check
             return jsonify({"status": "failed", "message": "Failed to get log_data_id after processing."}), 500

        # --- Model Inference ---
        if model_choice is None:
            # No model specified, just return success after logging/processing
            message = {"status": "success", "message": "Data processed successfully (no model specified)."}
            status = 200
        elif model_choice.lower() == "basic":
            # Run RuleBasedModel if chosen
            attention_score = RuleBasedModel(extraction_payload, log_data_id) # Assumes this function stores its own result
            message = {
                "status": "success",
                "message": "Basic model processing complete.", # Updated message
                "model_name": "Basic",
                "model_result": attention_score # Include the score if available
            }
            status = 200
        elif model_choice.lower() == "v1":
            # Run ONNX Model v1
            print("Running ONNX Model v1...")
            if not MODEL_V1_LOADED:
                message = {"status": "failed", "message": "Model v1 (ONNX) is not available on the server."}
                status = 503  # Service Unavailable
            else:
                # Call the imported ONNX prediction function
                predicted_score = predict_engagement_onnx(
                    extraction_payload=extraction_payload,
                    session=onnx_session,  # Pass the loaded ONNX session
                    log_data_id=log_data_id
                )

                if predicted_score is not None:
                    message = {
                        "status": "success",
                        "message": "ONNX Model v1 prediction successful.",
                        "model_name": "DNN_v1_ONNX",
                        "model_result": predicted_score.get('score', -1),
                        "model_result_class_name": predicted_score.get('name', "Unknown"),
                    }
                    status = 200
                else:
                    # Prediction failed within predict_engagement_onnx
                    message = {"status": "failed", "message": "ONNX Model v1 prediction failed."}
                    status = 500  # Internal Server Error
        else:
            # Unsupported model choice
             message = {"status": "failed", "message": f"Model '{model_choice}' is not supported."}
             status = 400

    # Final return
    return jsonify(message), status


@watch_items_bp.route('/watch/get_results', methods=['GET']) # Changed method to GET
def watch_get_results():
    """
    Retrieves model results for a specific YouTube video via GET request.

    Query Parameters:
        youtube_id (str): Required. The ID of the YouTube video.
        option (str): Optional. "all" or "alone" (default: "alone").

    Returns:
        JSON response containing model results, filtered based on the 'option'.
    """
    response_payload = {"status": "failed"} # Default error response
    status_code = 500 # Default error code

    # --- Authentication ---
    auth_resp, user_id, auth_status = get_authenticated_user()
    if auth_resp is not None:
        response_payload = auth_resp
        status_code = auth_status
    else: # User is authenticated, proceed
        # --- Get and Validate Query Parameters ---
        # Use request.args for GET parameters
        youtube_id = request.args.get("youtube_id")
        option = request.args.get("option", "alone").lower() # Default to 'alone'

        # --- Validate Input Fields ---
        if not youtube_id:
             response_payload = {"status": "failed", "message": "Missing 'youtube_id' query parameter."}
             status_code = 400
        elif option not in ["all", "alone"]:
             response_payload = {"status": "failed", "message": "Invalid 'option' query parameter. Must be 'all' or 'alone'."}
             status_code = 400
        else:
            # --- Check Video Access ---
            vid_message, vid_status = check_authenticated_video(youtube_id, user_id)
            if vid_status != 200:
                response_payload = vid_message
                status_code = vid_status
            else: # User has access, proceed to fetch results
                # --- Fetch Results from DB ---
                results_data, results_status = get_model_results_by_video(youtube_id)

                if results_status != 200:
                    response_payload = results_data # Use error response from DB function
                    status_code = results_status
                else: # Results fetched successfully (might be empty)
                    # --- Filter Results ---
                    final_results = {}
                    all_results = results_data.get("results_by_user", {})

                    if option == "all":
                        final_results = all_results
                    elif option == "alone":
                        final_results = {user_id: all_results[user_id]} if user_id in all_results else {}

                    # --- Construct Success Response ---
                    response_payload = {
                        "status": "success",
                        "youtube_id": youtube_id,
                        "option": option,
                        "results_by_user": final_results
                    }
                    status_code = 200

    # --- Single Return Point ---
    return jsonify(response_payload), status_code
