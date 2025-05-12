import threading
import traceback

from flask import Blueprint, request, jsonify
from db.db_api import (upload_video, update_video_details, remove_from_playlist,
                       get_all_videos_user_can_access)
from logic.generation.question_maker import get_or_generate_questions
from logic.generation.summary_maker import get_or_generate_summary
from server.main.utils import get_authenticated_user, check_authenticated_video

videos_bp = Blueprint('videos', __name__)


@videos_bp.route('/videos/upload', methods=['POST'])
def upload():
    """
    Handles video upload metadata and triggers background question generation.
    Ensures a single return point.
    """
    response_payload = {"status": "failed", "message": "Upload failed"}  # Default response
    status_code = 500  # Default status

    auth_resp, user_id, auth_status = get_authenticated_user()
    if auth_resp is not None:
        return auth_resp, auth_status  # Return authentication error directly

    data = request.get_json()
    if not data:
        response_payload = {"status": "failed", "message": "Invalid JSON payload."}
        status_code = 400
    else:
        try:
            # Store video metadata
            response_payload, status_code = upload_video(data, user_id)

            # After a successful upload, trigger background generation
            if status_code in [200, 201]:
                video_id = data.get("video_id")
                if video_id:
                    print(f"Upload successful for {video_id}. Triggering background generation...")

                    def trigger_generation(vid_id, lang):
                        """Target function for background thread."""
                        try:
                            result = get_or_generate_questions(youtube_id=vid_id, lang=lang)
                            print(
                                f"Background generation trigger completed for {vid_id} ({lang}). Status: {result.get('status')}")
                        except Exception as e:
                            print(f"Error in background generation thread for {vid_id} ({lang}): {e}")
                            traceback.print_exc()

                    threading.Thread(target=trigger_generation, args=(video_id, "English",), daemon=True).start()
                    threading.Thread(target=trigger_generation, args=(video_id, "Hebrew",), daemon=True).start()
                else:
                    print("Warning: Video upload successful but no video_id found in request data.")

        except Exception as e:
            print(f"Error during video upload processing: {e}")
            traceback.print_exc()
            response_payload = {"status": "failed", "message": "Internal server error during upload."}
            status_code = 500

    # Single return point
    return jsonify(response_payload), status_code


@videos_bp.route('/videos/update', methods=['POST'])
def update():
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    # update_video_details expects the video JSON payload (including "playlist_item_id")
    # and the user_id for ownership verification.
    response, code = update_video_details(data, user_id)
    return jsonify(response), code


@videos_bp.route('/videos/remove_from_playlist', methods=['POST'])
def remove_from_pl():
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    data = request.get_json()
    # remove_from_playlist expects the user_id and a JSON payload containing the playlist_item_id.
    response, code = remove_from_playlist(user_id, data)
    return jsonify(response), code


@videos_bp.route('/videos/accessible', methods=['GET'])
def get_accessible_videos_api():
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    response_data = get_all_videos_user_can_access(user_id)
    return jsonify(response_data), 200 if response_data.get("status") == "success" else 400


@videos_bp.route('/videos/<string:youtube_id>/questions', methods=['GET'])
def get_video_questions(youtube_id):
    """
    Retrieves questions for the video, generating them if necessary via locking mechanism.
    """
    response_payload = {"status": "failed", "reason": "Internal Server Error"}
    status_code = 500

    auth_resp, user_id, auth_status = get_authenticated_user()
    if auth_resp is not None:
        return auth_resp, auth_status

    vid_access_message, vid_access_status = check_authenticated_video(youtube_id, user_id)
    if vid_access_status != 200:
        response_payload = vid_access_message
        status_code = vid_access_status
    else:
        lang = request.args.get("lang", "Hebrew")
        try:
            result_data = get_or_generate_questions(youtube_id=youtube_id, lang=lang)
            result_status = result_data.get("status")
            result_questions = result_data.get("questions", [])
            result_reason = result_data.get("reason", "")

            if result_status == "success":
                response_payload = {
                    "status": "success",
                    "video_questions": {
                        "youtube_id": youtube_id,
                        "language": lang,
                        "questions": result_questions
                    }
                }
                status_code = 200
            elif result_status == "blocked":
                response_payload = {
                    "status": "pending",
                    "reason": result_reason,
                    "message": "Question generation is currently in progress. Please try again shortly."
                }
                status_code = 202 # Accepted
            else:
                response_payload = {
                    "status": "failed",
                    "reason": result_reason or "Failed to get or generate questions."
                }
                status_code = 500

        except Exception as e:
            print(f"Unexpected error in get_video_questions endpoint for {youtube_id} ({lang}): {e}")
            traceback.print_exc()
            response_payload = {"status": "failed", "reason": f"An unexpected server error occurred: {str(e)}"}
            status_code = 500

    return jsonify(response_payload), status_code


@videos_bp.route('/videos/<string:youtube_id>/summary', methods=['GET'])
def get_video_summary(youtube_id):
    """
    Retrieves the summary for the video, generating it if necessary via locking mechanism.
    """
    response_payload = {"status": "failed", "reason": "Internal Server Error"}
    status_code = 500

    # 1. Authenticate User
    auth_resp, user_id, auth_status = get_authenticated_user()
    if auth_resp is not None:
        return auth_resp, auth_status

    # 2. Check Video Access
    vid_access_message, vid_access_status = check_authenticated_video(youtube_id, user_id)
    if vid_access_status != 200:
        response_payload = vid_access_message
        status_code = vid_access_status
    else:
        # 3. Get Language (default to Hebrew if not provided)
        lang = request.args.get("lang", "Hebrew")

        try:
            # 4. Call the get_or_generate_summary function
            # Ensure get_or_generate_summary is imported correctly
            result_data = get_or_generate_summary(youtube_id=youtube_id, lang=lang)
            result_status = result_data.get("status")
            result_summary = result_data.get("summary")  # Expecting a dict like {"response": "..."} or None
            result_reason = result_data.get("reason", "")

            # 5. Handle Response Statuses
            if result_status == "success":
                response_payload = {
                    "status": "success",
                    "video_summary": {
                        "youtube_id": youtube_id,
                        "language": lang,
                        # Assuming result_summary is the dict {"response": "..."}
                        "summary": result_summary
                    }
                }
                status_code = 200
            elif result_status == "blocked":
                response_payload = {
                    "status": "pending",
                    "reason": result_reason,
                    "message": "Summary generation is currently in progress or blocked. Please try again shortly."
                }
                status_code = 202 # Accepted
            else: # Failed status from get_or_generate_summary
                response_payload = {
                    "status": "failed",
                    "reason": result_reason or "Failed to get or generate summary."
                }
                status_code = 500 # Or appropriate error code based on failure reason

        except Exception as e:
            print(f"Unexpected error in get_video_summary endpoint for {youtube_id} ({lang}): {e}")
            traceback.print_exc()
            response_payload = {"status": "failed", "reason": f"An unexpected server error occurred: {str(e)}"}
            status_code = 500

    # 6. Return JSON Response
    return jsonify(response_payload), status_code
