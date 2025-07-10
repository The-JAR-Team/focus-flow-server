import os
import numpy as np
from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any

from db.db_api import get_watch_item, get_model_results_by_video, log_watch_batch_client_tickets
from server.main.utils import get_authenticated_user, check_authenticated_video
from server.main.videos.ticket import ticket_route_authenticator

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


@watch_items_bp.route('/watch/get_results', methods=['GET'])
def watch_get_results():
    """
    Retrieves model results for a specific YouTube video via GET request.
    (This function is from the user-provided watch_items.py)
    """
    response_payload = {"status": "failed"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=1)
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
