from flask import Flask, request, jsonify

from db.db_api import get_user, get_all_videos_user_can_access, get_permission

from flask import request, jsonify, make_response, Response
from db.db_api import get_user  # Assuming get_user(session_id) returns (user_id, status)


def get_authenticated_user(min_permission=0):
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
    arg:
        min_permission (int): Minimum permission level required for the user, 0:guest 1:normal user, 2:admin
    returns:
        resp (Response): Flask response object, None if authentication succeeds
        user_id (int): ID of the authenticated user, 0 if authentication fails
        status (int): HTTP status code, 200 if authentication succeeds, error code if fails
    """
    session_id = request.cookies.get('session_id')
    if not session_id:
        resp = make_response(jsonify({"status": "failed", "reason": "No session cookie provided"}), 401)
        resp.set_cookie("session_id", "", expires=0, httponly=True, secure=True, samesite='none')
        return resp, 0, 401

    user_id, status = get_user(session_id)
    if status != 200:
        resp = make_response(jsonify({"status": "failed", "reason": "Session expired or invalid"}), status)
        if status != 500:
            # resp.set_cookie("session_id", "", expires=0, httponly=True, secure=True, samesite='none')
            print(f"!!!!!!!!!!!!!Session expired or invalid for user_id {user_id} {status}!!!!!!!!!!!!")
        return resp, 0, status

    # Check if the user has the required permission level
    if get_permission(user_id) < min_permission:
        resp = make_response(jsonify({"status": "failed", "reason": "Insufficient permissions"}), 403)
        return resp, user_id, 403

    return None, user_id, 200


def check_authenticated_video(youtube_id, user_id):
    """
    Checks if a user is authorized to access a video based on its youtube_id.
    This is the original method and remains unchanged for backward compatibility.
    """
    message = None
    status = 200
    # Retrieve accessible videos for the user.
    # get_all_videos_user_can_access(user_id) needs to exist in db_api
    accessible_videos_data = get_all_videos_user_can_access(user_id)
    if accessible_videos_data.get("status") != "success":
        message = {"status": "failed", "reason": "Failed to retrieve accessible videos for authentication"}
        status = 500 # Internal error if data retrieval fails
    else:
        # Extract all accessible YouTube IDs from the user's playlists.
        accessible_youtube_ids = set()
        for playlist in accessible_videos_data.get("playlists", []):
            for item in playlist.get("playlist_items", []):
                ext_id = item.get("external_id") # external_id is the youtube_id
                if ext_id:
                    accessible_youtube_ids.add(ext_id)

        # Check if the requested youtube_id is among the accessible ones.
        if youtube_id not in accessible_youtube_ids:
            message = {"status": "failed", "reason": "User not authorized for this video"}
            status = 403

    return message, status


def check_authenticated_video_id(video_id_to_check, user_id):
    """
    Checks if a user is authorized to access a video based on its internal video_id.
    """
    message = None
    status = 200

    if not isinstance(video_id_to_check, int):
        try:
            video_id_to_check = int(video_id_to_check)
        except ValueError:
            return {"status": "failed", "reason": "Invalid video_id format"}, 400

    accessible_videos_data = get_all_videos_user_can_access(user_id)
    if accessible_videos_data.get("status") != "success":
        message = {"status": "failed", "reason": "Failed to retrieve accessible videos for authentication"}
        status = 500 # Internal error
    else:
        found_video = False
        for playlist in accessible_videos_data.get("playlists", []):
            for item in playlist.get("playlist_items", []):
                # 'video_id' is the internal DB primary key for the Video table
                if item.get("video_id") == video_id_to_check:
                    found_video = True
                    break
            if found_video:
                break

        if not found_video:
            message = {"status": "failed", "reason": "User not authorized for this video_id"}
            status = 403

    return message, status


def check_authenticated_playlist_id(playlist_id_to_check, user_id):
    """
    Checks if a user is authorized to access a playlist based on its playlist_id.
    A user is authorized if they own the playlist, are subscribed to a non-private playlist,
    or if the playlist is public.
    """
    message = None
    status = 200

    if not isinstance(playlist_id_to_check, int):
        try:
            playlist_id_to_check = int(playlist_id_to_check)
        except ValueError:
            return {"status": "failed", "reason": "Invalid playlist_id format"}, 400


    # get_all_videos_user_can_access already filters playlists based on user access
    # (own, subscribed to public/shared, or public playlists)
    accessible_videos_data = get_all_videos_user_can_access(user_id)

    if accessible_videos_data.get("status") != "success":
        message = {"status": "failed", "reason": "Failed to retrieve accessible playlists for authentication"}
        status = 500 # Internal error
    else:
        found_playlist = False
        for playlist in accessible_videos_data.get("playlists", []):
            # 'playlist_id' is the internal DB primary key for the Playlist table
            if playlist.get("playlist_id") == playlist_id_to_check:
                found_playlist = True
                break

        if not found_playlist:
            message = {"status": "failed", "reason": "User not authorized for this playlist_id or playlist does not exist"}
            status = 403 # Or 404 if we want to distinguish not found from not authorized

    return message, status
