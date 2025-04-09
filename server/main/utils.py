from flask import Flask, request, jsonify

from db.db_api import get_user, get_all_videos_user_can_access

from flask import request, jsonify, make_response, Response
from db.db_api import get_user  # Assuming get_user(session_id) returns (user_id, status)


def get_authenticated_user():
    """
    Reads the session_id cookie, validates the session,
    and returns a tuple: (resp, user_id, status)

    If authentication succeeds:
      - resp is None,
      - user_id is the authenticated user's id,
      - status is 200.

    If authentication fails:
      - resp is a Flask response (that clears the session cookie),
      - user_id is 0,
      - status is an error code (e.g. 401).
    """
    session_id = request.cookies.get('session_id')
    if not session_id:
        resp = make_response(jsonify({"status": "failed", "reason": "No session cookie provided"}), 401)
        resp.set_cookie("session_id", "", expires=0, httponly=True, secure=True, samesite='none')
        return resp, 0, 401

    user_id, status = get_user(session_id)
    if status != 200:
        resp = make_response(jsonify({"status": "failed", "reason": "Session expired or invalid"}), status)
        resp.set_cookie("session_id", "", expires=0, httponly=True, secure=True, samesite='none')
        return resp, 0, status

    return None, user_id, 200


def check_authenticated_video(youtube_id, user_id):
    message = None
    status = 200
    # Retrieve accessible videos for the user.
    accessible_videos = get_all_videos_user_can_access(user_id)
    if accessible_videos.get("status") != "success":
        message = {"status": "failed", "reason": "failed to retrieve accessible videos"}
        status = 403
    else:
        # Extract all accessible YouTube IDs from the user's playlists.
        accessible_ids = set()
        for playlist in accessible_videos.get("playlists", []):
            for item in playlist.get("playlist_items", []):
                ext_id = item.get("external_id")
                if ext_id:
                    accessible_ids.add(ext_id)

        # Check if the requested youtube_id is among the accessible ones.
        if youtube_id not in accessible_ids:
            message = {"status": "failed", "reason": "user not authorized for this video"}
            status = 403

    return message, status
