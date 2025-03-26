# videos.py
import threading

from flask import Blueprint, request, jsonify
from db.db_api import *
from logic.transcript_maker import generate_questions_from_transcript, gen_if_empty
from server.main.utils import get_authenticated_user

videos_bp = Blueprint('videos', __name__)


@videos_bp.route('/videos/upload', methods=['POST'])
def upload():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    response, code = upload_video(data, user_id)

    # After a successful upload, start background threads to generate questions
    if code == 200:
        video_id = data.get("video_id")
        if video_id:
            def async_generate(lang):
                try:
                    gen_if_empty(youtube_id=video_id, lang=lang)
                except Exception as e:
                    print(f"Error generating questions for {lang}: {e}")

            thread_en = threading.Thread(target=async_generate, args=("English",))
            thread_he = threading.Thread(target=async_generate, args=("Hebrew",))
            thread_en.start()
            thread_he.start()

    return jsonify(response), code


@videos_bp.route('/videos/update', methods=['POST'])
def update():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    # Now update_video_details expects the video JSON payload (which contains "playlist_item_id")
    # and the user_id for ownership verification.
    response, code = update_video_details(data, user_id)
    return jsonify(response), code


@videos_bp.route('/videos/remove_from_playlist', methods=['POST'])
def remove_from_pl():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    data = request.get_json()
    # remove_from_playlist expects the user_id and a JSON payload containing the playlist_item_id.
    response, code = remove_from_playlist(user_id, data)
    return jsonify(response), code


@videos_bp.route('/videos/accessible', methods=['GET'])
def get_accessible_videos_api():
    user_id, status = get_authenticated_user()
    if status != 200:
        return jsonify({"status": "failed", "reason": "unauthenticated"}), 401

    response_data = get_all_videos_user_can_access(user_id)
    return jsonify(response_data), 200 if response_data["status"] == "success" else 400


@videos_bp.route('/videos/<string:youtube_id>/questions', methods=['GET'])
def get_video_questions(youtube_id):
    """
    GET /videos/<youtube_id>/questions

    Optional query parameter:
      lang: language code (default is 'Hebrew')

    This endpoint retrieves questions for the given YouTube video and language.
    If the "video_questions" list is empty, it calls generate_questions_from_transcript()
    (which returns a JSON object with a "questions" array) and inserts its output under
    "video_questions" in the result.
    """
    lang = request.args.get("lang", "Hebrew")

    # Retrieve questions from the database.
    result = get_questions_for_video_api(youtube_id, lang)  # Aggregator function

    # If no questions were found, call the generate function and insert its output.
    if not result.get("video_questions", {}).get("questions"):
        generated = generate_questions_from_transcript(youtube_id, lang)
        # Assume generated is a dict like: { "questions": [ ... ] }
        result["video_questions"] = generated

    return jsonify(result), 200

