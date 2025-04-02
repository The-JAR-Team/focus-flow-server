import threading
from flask import Blueprint, request, jsonify
from db.db_api import (upload_video, update_video_details, remove_from_playlist,
                       get_all_videos_user_can_access, get_questions_for_video_api, get_accessible_videos)
from logic.transcript_maker import generate_questions_from_transcript, gen_if_empty
from server.main.utils import get_authenticated_user

videos_bp = Blueprint('videos', __name__)

@videos_bp.route('/videos/upload', methods=['POST'])
def upload():
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

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
    GET /videos/<youtube_id>/questions

    Optional query parameter:
      lang: language code (default is 'Hebrew')

    This endpoint retrieves questions for the given YouTube video and language.
    It first ensures that the authenticated user has access to the video by checking
    against the accessible videos returned by get_accessible_videos. If not accessible,
    it returns a 403 error.
    If no questions exist, it calls generate_questions_from_transcript() to generate and store them.
    """
    # Authenticate user using session cookie.
    resp, user_id, status = get_authenticated_user()
    if resp is not None:
        return resp, status

    # Retrieve accessible videos for the user.
    accessible_videos = get_accessible_videos(user_id)
    if accessible_videos.get("status") != "success":
        return jsonify({"status": "failed", "reason": "failed to retrieve accessible videos"}), 403

    # Extract all accessible YouTube IDs from the user's playlists.
    accessible_ids = set()
    for playlist in accessible_videos.get("playlists", []):
        for item in playlist.get("playlist_items", []):
            ext_id = item.get("external_id")
            if ext_id:
                accessible_ids.add(ext_id)

    # Check if the requested youtube_id is among the accessible ones.
    if youtube_id not in accessible_ids:
        return jsonify({"status": "failed", "reason": "user not authorized for this video"}), 403

    lang = request.args.get("lang", "Hebrew")
    # Retrieve questions from the database.
    result = get_questions_for_video_api(youtube_id, lang)
    # If no questions were found, generate them.
    if not result.get("video_questions", {}).get("questions"):
        generated = generate_questions_from_transcript(youtube_id, lang)
        result["video_questions"] = generated

    return jsonify(result), 200

