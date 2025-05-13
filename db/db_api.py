"""
db_api.py

This module acts as an aggregator for user, playlist, video, subscription,
watch item, and question operations. All functions delegate to the corresponding
functions in user_management, playlists_management, video_management,
subscription_management, watch_management, or question_management. Below each function,
you'll find its expected input (arguments) and output (return values).
"""

from db import user_management, playlists_management, video_management, subscription_management, watch_management, \
    question_management, lock_management, transcript_manager, summary_management
from db.video_management import get_accessible_videos


def login_user(data):
    """
    Logs in a user by delegating to user_management.login_user.

    Args:
        data (dict): Must include:
            {
                "email": <str>,
                "password": <str>
            }

    Returns:
        tuple: (response_dict, http_status_code, session_id (str or 0), user_id (int or 0))
          - response_dict (dict) has keys: "status" ("success" or "failed"), "reason" (<str>).
          - http_status_code (int) e.g. 200 on success, 401 on failure.
          - session_id (str or 0): The session ID if login succeeded; 0 if failed.
          - user_id (int or 0): The user’s ID if login succeeded; 0 if failed.
    """
    return user_management.login_user(data)


def register_user(data):
    """
    Registers a new user by delegating to user_management.register_user.

    Args:
        data (dict): Must include:
            {
                "email": <str>,
                "password": <str>,
                "first name": <str>,
                "last name": <str>,
                "age": <int>
            }

    Returns:
        tuple: (response_dict, http_status_code, session_id (str or 0))
          - response_dict (dict) has keys: "status" ("success" or "failed"), "reason" (<str>).
          - http_status_code (int) e.g. 200 on success, 401 on failure.
          - session_id (str or 0): The new session ID if registration and auto-login succeeded; 0 otherwise.
    """
    return user_management.register_user(data)


def validate_session(session_id):
    """
    Validates a user's session by delegating to user_management.validate_session.

    Args:
        session_id (str): The session ID to validate.

    Returns:
        tuple: (response_dict, http_status_code, session_id (str or 0))
          - response_dict (dict) with "status" ("success" or "failed"), "reason" (<str>).
          - http_status_code (int) e.g. 200 on success, 401 on failure.
          - session_id (str or 0): The session ID if still valid; 0 if invalid or expired.
    """
    return user_management.validate_session(session_id)


def get_user(session_id):
    """
    Retrieves the user ID associated with a valid session by delegating to user_management.get_user.

    Args:
        session_id (str): The session ID to look up.

    Returns:
        tuple: (user_id (int), status_code (int))
          - user_id (int): 0 if not found or session is invalid; otherwise the user’s ID.
          - status_code (int): 200 if valid, otherwise an error code (e.g., 401).
    """
    return user_management.get_user(session_id)


def get_permission(user_id: int):
    """
    Retrieves the permission level for a given user_id.

    Args:
        user_id (int): The ID of the user.

    Returns:
        int or None: The permission level (integer) if the user is found,
                     otherwise None. Returns None on database error.
    """
    return user_management.get_permission(user_id)


def create_playlist(user_id, playlist_name, playlist_permission):
    """
    Creates a new playlist for a user by delegating to playlists_management.create_playlist.

    Args:
        user_id (int): The ID of the user creating the playlist.
        playlist_name (str): The desired playlist name.
        playlist_permission (str): Access setting ("unlisted", "public", or "private").

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict) with "status" ("success" or "failed"), "reason" on failure,
            and possibly "playlist_id" on success.
          - http_status_code (int): 200 on success, other codes on failure.
    """
    return playlists_management.create_playlist(user_id, playlist_name, playlist_permission)


def delete_playlist(user_id, playlist_id):
    """
    Deletes a playlist by delegating to playlists_management.delete_playlist.

    Args:
        user_id (int): The ID of the user requesting deletion.
        playlist_id (int): The ID of the playlist to delete.

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict) has "status" ("success" or "failed") and a "reason" or "Playlist deleted".
          - http_status_code (int): 200 on success, error codes on failure.
    """
    return playlists_management.delete_playlist(user_id, playlist_id)


def get_all_user_playlists(user_id):
    """
    Retrieves all playlists for a user by delegating to playlists_management.get_all_user_playlists.

    Args:
        user_id (int): The user's ID.

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict):
              {
                "status": "success" or "failed",
                "playlists": [
                  { "playlist_id": <int>, "playlist_name": <str>, "permission": <str> }, ...
                ]
              }
          - http_status_code (int)
    """
    return playlists_management.get_all_user_playlists(user_id)


def update_playlist_permission(user_id, playlist_id, new_permission):
    """
    Updates the permission setting for a playlist by delegating to playlists_management.update_playlist_permission.

    Args:
        user_id (int): The ID of the user who owns the playlist.
        playlist_id (int): The ID of the playlist to update.
        new_permission (str): The new permission ("public", "unlisted", or "private").

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict): { "status": <"success" or "failed">, "reason": <str> }
          - http_status_code (int)
    """
    return playlists_management.update_playlist_permission(user_id, playlist_id, new_permission)


def update_playlist_name(user_id, data):
    """
    Updates the name of a playlist by delegating to playlists_management.update_playlist_name.

    Args:
        user_id (int): The ID of the user who owns the playlist.
        data (dict): Must include:
            {
              "old_name": <str>,
              "new_name": <str>
            }

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict):
              {
                "status": "success" or "failed",
                "reason": <str>,
                "playlist_id": <int> (on success)
              }
          - http_status_code (int)
    """
    return playlists_management.update_playlist_name(user_id, data)


def remove_from_playlist(user_id, data):
    """
    Removes a playlist item by delegating to playlists_management.remove_from_playlist.

    Args:
        user_id (int): The ID of the user requesting removal.
        data (dict): Must include:
            {
              "playlist_item_id": <int>
            }

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict):
              { "status": "success" or "failed", "reason": <str>, "removed_playlist_item_id": <int> } on success
          - http_status_code (int)
    """
    return playlists_management.remove_from_playlist(user_id, data)


def upload_video(data, user_id):
    """
    Uploads a video and associates it with one or more user playlists by delegating to video_management.upload_video.

    Args:
        data (dict): Must include:
            {
              "video_id": <str> (YouTube video ID),
              "video_name": <str>,
              "subject": <str>,
              "playlists": [<str>], // array of playlist names
              "description": <str>,
              "length": <str> (cast to INTERVAL, e.g. "00:12:34"),
              "uploadby": <str> (e.g. "Prof. Jane AI")
            }
        user_id (int): The ID of the user for whom the playlists are managed.

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict):
              {
                "status": "success" or "failed",
                "reason": <str if failed>,
                "video_id": <int if success>
              }
          - http_status_code (int)
    """
    return video_management.upload_video(data, user_id)


def update_video_details(data, user_id):
    """
    Updates an existing video record by delegating to video_management.update_video_details.

    This version uses a playlist_item_id to locate the video record, verifies that the
    authenticated user owns the playlist associated with that item, and then updates the video.

    Args:
        data (dict): Must include:
            {
              "playlist_item_id": <int>,   // The playlist_item_id that references the video.
              "video_id": <str>,           // YouTube video ID
              "video_name": <str>,
              "subject": <str>,
              "description": <str>,
              "length": <str>,             // To be cast to INTERVAL (e.g. "00:12:34")
              "uploadby": <str>
            }
        user_id (int): The ID of the user for whom the update is being made.

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict):
              {
                "status": "success" or "failed",
                "reason": <str>,
                "video_id": <int if success>
              }
          - http_status_code (int)
    """
    return video_management.update_video_details(data, user_id)


def subscribe_playlist(owner_id, data):
    """
    Subscribes a user to a playlist by delegating to subscription_management.subscribe_playlist.

    Args:
        owner_id (int): The ID of the owner (authenticated user) of the playlist.
        data (dict): Must include:
            {
              "email": <str>,        // Email of the subscriber
              "playlist_id": <int>     // The target playlist's ID
            }

    Returns:
        tuple: (response_dict, http_status_code)
    """
    return subscription_management.subscribe_playlist(owner_id, data)


def unsubscribe_playlist(owner_id, data):
    """
    Unsubscribes a user from a playlist by delegating to subscription_management.unsubscribe_playlist.

    Args:
        owner_id (int): The ID of the owner (authenticated user) of the playlist.
        data (dict): Must include:
            {
              "email": <str>,        // Email of the subscriber
              "playlist_id": <int>     // The target playlist's ID
            }

    Returns:
        tuple: (response_dict, http_status_code)
    """
    return subscription_management.unsubscribe_playlist(owner_id, data)


def log_watch_item(user_id, data):
    """
    Logs (or updates) a watch record for a given user and video by delegating to watch_management.log_watch.

    Args:
        user_id (int): The ID of the authenticated user.
        data (dict): Must include:
            {
              "video_id": <int>,
              "current_watch_time": <int>,
              "time_before_jump": <int>
            }

    Returns:
        tuple: (response_dict, http_status_code)
    """
    return watch_management.log_watch(user_id, data)


def get_watch_item(user_id, data):
    """
    Retrieves the watch record for a given user and video by delegating to watch_management.get_watch.

    Args:
        user_id (int): The ID of the authenticated user.
        data (dict): Must include:
            {
              "video_id": <int>
            }

    Returns:
        tuple: (response_dict, http_status_code)
    """
    return watch_management.get_watch_item(user_id, data)


def get_all_videos_user_can_access(user_id):
    """
    Retrieves all videos accessible by a user by delegating to video_management.get_accessible_videos.

    Args:
        user_id (int): The ID of the authenticated user.
    """
    return get_accessible_videos(user_id)


def get_questions_for_video(youtube_id, language):
    """
    Retrieves questions for a given YouTube video and language by delegating to question_management.get_questions_for_video.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language (e.g. "Hebrew" or "English").

    Returns:
        dict: A dictionary of questions, e.g. { "questions": [ ... ] }
    """
    return question_management.get_questions_for_video(youtube_id, language)


def store_questions_in_db(youtube_id, language, questions):
    """
    Stores generated questions into the database by delegating to question_management.store_questions_in_db.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language of the questions.
        questions (list): A list of question dictionaries.

    Returns:
        int: The newly created question_group_id, or 0 on failure.
    """
    return question_management.store_questions_in_db(youtube_id, language, questions)


def questions_ready(youtube_id, language="Hebrew"):
    """
    Checks if there are existing questions for the given YouTube video and language by delegating to question_management.questions_ready.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language (default "Hebrew").

    Returns:
        int: The count of questions found (or 0 if none).
    """
    return question_management.questions_ready(youtube_id, language)


def get_user_info(user_id):
    """
    Retrieves user information for the given user_id by delegating to user_management.get_user_info.

    Args:
        user_id (int): The user's ID.

    Returns:
        tuple: (response_dict, http_status_code)
          - response_dict (dict) containing all fields from the User table.
    """
    return user_management.get_user_info(user_id)


def logout_user(session_id):
    """
    Invalidates the session by removing it from the Sessions table, by delegating to user_management.logout_user.

    Args:
        session_id (str): The session ID to invalidate.

    Returns:
        tuple: (response_dict, http_status_code)
    """
    return user_management.logout_user(session_id)


from db import subscription_management


def get_playlist_subscribers(owner_id, playlist_id):
    """
    Retrieves subscriber emails for a playlist by delegating to
    subscription_management.get_playlist_subscribers.

    Args:
        owner_id (int): The user who owns the playlist.
        playlist_id (int): The ID of the target playlist.

    Returns:
        tuple: (response_dict, http_status_code)
          - On success:
              {
                "status": "success",
                "subscribers": ["email1@example.com", "email2@example.com", ...]
              }
          - On failure:
              { "status": "failed", "reason": <error message> }
    """
    return playlists_management.get_playlist_subscribers(owner_id, playlist_id)


def get_playlist_subscriber_count(owner_id, playlist_id):
    """
    Returns the number of subscribers for a playlist by delegating to
    subscription_management.get_playlist_subscriber_count.

    Args:
        owner_id (int): The user who owns the playlist.
        playlist_id (int): The ID of the target playlist.

    Returns:
        tuple: (response_dict, http_status_code)
          - On success:
              {
                "status": "success",
                "count": <number_of_subscribers>
              }
          - On failure:
              { "status": "failed", "reason": <error message> }
    """
    return playlists_management.get_playlist_subscriber_count(owner_id, playlist_id)


def process_mediapipe_data(watch_item_id, current_time, extraction_payload):
    """
    Processes and stores facial landmark extraction data from mediapipe.

    Args:
        watch_item_id (int): The ID of the watch item
        user_id (int): The ID of the user
        current_time (float): The current time in the video (will be used as stop_time)
        extraction_payload (dict): Contains the extraction data with format:
            {
                "fps": int,                # Frames per second
                "interval": int,           # Time interval in seconds
                "number_of_landmarks": int,  # Number of landmarks per frame
                "landmarks": array         # Array of landmark data
            }

    Returns:
        tuple: (response_dict, status_code)
            Example success:
              {
                "status": "success",
                "watch_data_id": int,
                "log_data_id": int,
                "message": "Extraction data processed successfully"
              }, 200
    """
    return watch_management.process_mediapipe_data(watch_item_id, current_time, extraction_payload)

def get_model_results_by_video(youtube_id: str):
    """
    Retrieves all model results for a specific YouTube video, grouped by user.

    Args:
        youtube_id (str): The ID of the YouTube video.

    Returns:
        tuple: (response_dict, status_code)
            Example success:
              {
                "status": "success",
                "youtube_id": "some_video_id",
                "results_by_user": {
                  <user_id_1>: [
                    {"model_result_id": 1, "log_data_id": 10, "model": "v1_onnx", "result": 0.75, "timestamp": ...},
                    {"model_result_id": 5, "log_data_id": 15, "model": "basic", "result": 0.80, "timestamp": ...}
                  ],
                  <user_id_2>: [
                    {"model_result_id": 8, "log_data_id": 22, "model": "v1_onnx", "result": 0.60, "timestamp": ...}
                  ]
                }
              }, 200
            Example not found:
              {"status": "success", "youtube_id": "some_video_id", "results_by_user": {}}, 200
            Example error:
              {"status": "failed", "reason": "Error retrieving model results"}, 500
    """
    return watch_management.get_model_results_by_video(youtube_id)


def acquire_lock(lock_key: str) -> bool:
    """
    Attempts to acquire a distributed lock by inserting a unique key into the Generation_Locks table.

    Args:
        lock_key (str): The unique identifier for the resource to lock (e.g., "youtubeId_language").

    Returns:
        bool: True if the lock was successfully acquired, False otherwise (lock already held or DB error).
    """
    return lock_management.acquire_lock(lock_key)


def release_lock(lock_key: str) -> bool:
    """
    Releases a distributed lock by deleting the corresponding key from the Generation_Locks table.

    Args:
        lock_key (str): The unique identifier for the resource lock to release.

    Returns:
        bool: True if the lock was successfully deleted (or didn't exist), False if a DB error occurred.
    """
    return lock_management.release_lock(lock_key)


def insert_transcript(youtube_id: str, language: str, transcript_text: str):
    """
    Inserts a new transcript into the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language of the transcript (e.g., 'en', 'es').
        transcript_text (str): The actual transcript content.

    Returns:
        dict: A dictionary containing:
            - "status" (str): "success" or "failed".
            - "message" (str): A descriptive message about the operation.
            - "transcript_id" (tuple or None): A tuple (youtube_id, language) if successful, else None.
    """
    return transcript_manager.insert_transcript(youtube_id, language, transcript_text)


def get_transcript(youtube_id: str, language: str):
    """
    Retrieves a transcript from the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language of the transcript.

    Returns:
        str or None: The transcript text if found, otherwise None.
                     Returns None and logs an error if a database or unexpected error occurs.
    """
    return transcript_manager.get_transcript(youtube_id, language)


def get_summary(youtube_id: str, language: str):
    """
    Retrieves the summary JSON object from the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the transcript/summary.

    Returns:
        dict or None: The summary JSON object (as a Python dict) if found,
                      otherwise None. Returns None and logs an error if a
                      database or unexpected error occurs.
    """
    return summary_management.get_summary(youtube_id, language)


def upsert_summary(youtube_id: str, language: str, summary_json: dict):
    """
    Inserts a new summary entry or updates the existing one for the given
    youtube_id and language combination in the "Summary" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the summary.
        summary_json (dict): The Python dictionary to be stored as JSONB in the 'summary' column.

    Returns:
        dict: A dictionary containing:
            - "status" (str): "success" or "failed".
            - "message" (str): A descriptive message about the operation.
            - "operation" (str): "insert" or "update" indicating what the DB did (best guess based on rowcount).
                                 Note: ON CONFLICT doesn't directly return this, so it's inferred.
    """
    return summary_management.upsert_summary(youtube_id, language, summary_json)
