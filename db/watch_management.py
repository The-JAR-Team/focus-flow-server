import json
from collections import defaultdict
from db.DB import DB
from datetime import datetime


def log_watch(user_id, data):
    """
    Logs or updates watch data for the given user and video.

    Expects:
    {
      "youtube_id": <int>,
      "current_time": <float>,   // optional, defaults to 0.0 if missing
    }

    If a Watch_Item row already exists for (user_id, youtube_id), it updates it.
    Otherwise, it creates a new row with the provided data.

    Returns: (response_dict, http_status_code)
    Example success:
      {
        "status": "success",
        "watch_item_id": <int>,
        "reason": "Watch item logged"
      }, 200
    """
    try:
        with DB.get_cursor() as cur:
            youtube_id = data.get("youtube_id")
            if not youtube_id:
                return {"status": "failed", "reason": "Missing youtube_id"}, 400

            current_time = data.get("current_time", 0.0)

            # Check if a watch item already exists for (user_id, youtube_id).
            cur.execute(
                '''SELECT watch_item_id
                   FROM "Watch_Item"
                   WHERE user_id = %s AND youtube_id = %s
                   LIMIT 1''',
                (user_id, youtube_id)
            )
            row = cur.fetchone()

            if row is None:
                # Insert a new watch item
                cur.execute(
                    '''INSERT INTO "Watch_Item"
                       (user_id, youtube_id, "current_time", last_updated)
                       VALUES (%s, %s, %s, NOW())
                       RETURNING watch_item_id''',
                    (user_id, youtube_id, current_time)
                )
                watch_item_id = cur.fetchone()[0]
            else:
                # Update existing watch item
                watch_item_id = row[0]
                cur.execute(
                    '''UPDATE "Watch_Item"
                       SET "current_time" = %s,
                           last_updated = NOW()
                       WHERE watch_item_id = %s''',
                    (current_time, watch_item_id)
                )

            return {
                "status": "success",
                "reason": "Watch item logged",
                "watch_item_id": watch_item_id
            }, 200

    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "Error logging watch item"}, 500


def get_watch_item(user_id, data):
    """
    Retrieves the watch item for the given user and video, if it exists.

    Expects:
    {
      "youtube_id": <int>
    }

    Returns: (response_dict, http_status_code)

    Example success:
      {
        "status": "success",
        "watch_item": {
          "watch_item_id": <int>,
          "youtube_id": <int>,
          "current_time": <int>,
          "last_updated": <string date>
        }
      }, 200

    If no watch item is found, returns a 404 with a "not found" reason.
    """
    try:
        with DB.get_cursor() as cur:
            youtube_id = data.get("youtube_id")
            if not youtube_id:
                return {"status": "failed", "reason": "Missing youtube_id"}, 400

            cur.execute(
                '''SELECT watch_item_id, "current_time", last_updated
                   FROM "Watch_Item"
                   WHERE user_id = %s AND youtube_id = %s''',
                (user_id, youtube_id)
            )
            row = cur.fetchone()

            if row is None:
                return {"status": "failed", "reason": "Watch item not found"}, 404

            watch_item_id, current_time, last_updated = row
            return {
                "status": "success",
                "watch_item": {
                    "watch_item_id": watch_item_id,
                    "youtube_id": youtube_id,
                    "current_time": current_time,
                    "last_updated": str(last_updated) if last_updated else None
                }
            }, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "Error retrieving watch item"}, 500


def process_mediapipe_data(watch_item_id, current_time, extraction_payload):
    """
    Processes and stores facial landmark extraction data from mediapipe.

    Args:
        watch_item_id (int): The ID of the watch item
        current_time (float): The current time in the video (will be used as stop_time)
        extraction_payload (dict): Contains the extraction data with format:
            {
                "fps": int,                # Frames per second
                "interval": int,           # Time interval in seconds
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
    try:
        with DB.get_cursor() as cur:
            # Extract data from payload
            fps = extraction_payload.get("fps")
            interval = extraction_payload.get("interval")

            if not all([fps, interval]):
                return {
                    "status": "failed",
                    "message": "Missing required fields in extraction payload"
                }, 400

            # First, create a Watch_Data entry
            cur.execute(
                '''INSERT INTO "Watch_Data" 
                   (watch_item_id, log_date, vid_watch_time, "interval") 
                   VALUES (%s, NOW(), %s, %s) 
                   RETURNING watch_data_id''',
                (watch_item_id, current_time, interval)
            )
            watch_data_id = cur.fetchone()[0]

            # Next, create a Log_Data entry with landmarks stored as JSONB
            extraction_type = f"mediapipe"

            # Using JSONB for storing landmarks
            cur.execute(
                '''INSERT INTO "Log_Data"
                   (watch_data_id, fps_num, extraction_type)
                   VALUES (%s, %s, %s)
                   RETURNING log_data_id''',
                (watch_data_id, fps, extraction_type)
            )
            log_data_id = cur.fetchone()[0]

            # Update the Watch_Item last_updated timestamp
            cur.execute(
                '''UPDATE "Watch_Item"
                   SET last_updated = NOW()
                   WHERE watch_item_id = %s''',
                (watch_item_id,)
            )

            return {
                "status": "success",
                "watch_data_id": watch_data_id,
                "log_data_id": log_data_id,
                "message": "Extraction data processed successfully"
            }, 200

    except Exception as e:
        print(f"Error processing mediapipe data: {e}")
        return {
            "status": "failed",
            "message": f"Error processing extraction data: {str(e)}"
        }, 500


def get_log_data(log_data_id):
    """
    Retrieves Log_Data entry by its ID.

    Args:
        log_data_id (int): The ID of the log data entry to retrieve

    Returns:
        dict: The log data entry as a dictionary, or None if not found
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                '''SELECT log_data_id, watch_data_id, fps_num, extraction_type, fps_log
                   FROM "Log_Data"
                   WHERE log_data_id = %s''',
                (log_data_id,)
            )
            row = cur.fetchone()

            if row is None:
                return None

            log_data_id, watch_data_id, fps_num, extraction_type, fps_log = row

            return {
                "log_data_id": log_data_id,
                "watch_data_id": watch_data_id,
                "fps_num": fps_num,
                "extraction_type": extraction_type,
                "fps_log": fps_log  # This will be automatically deserialized from JSONB to a Python dict
            }

    except Exception as e:
        print(f"Error retrieving log data: {e}")
        return None


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
                    {"model_result_id": 1, "log_data_id": 10, "model": "v1_onnx", "result": 0.75, "timestamp": "...", "video_time": 123.45},
                    # ... more results for user 1
                  ],
                  <user_id_2>: [
                    # ... results for user 2
                  ]
                }
              }, 200
            Example not found:
              {"status": "success", "youtube_id": "some_video_id", "results_by_user": {}}, 200
            Example error:
              {"status": "failed", "reason": "Error retrieving model results"}, 500
    """
    # Use defaultdict(list) for automatic list creation per user
    results_by_user = defaultdict(list)
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                '''SELECT
                       wi.user_id,
                       mr.model_result_id,
                       mr.log_data_id,
                       mr.model,
                       mr.result,
                       wd.log_date AS timestamp, -- Use log_date from Watch_Data as timestamp
                       wd.vid_watch_time -- Get the video time associated with the log
                   FROM "Model_Result" mr
                   JOIN "Log_Data" ld ON mr.log_data_id = ld.log_data_id
                   JOIN "Watch_Data" wd ON ld.watch_data_id = wd.watch_data_id
                   JOIN "Watch_Item" wi ON wd.watch_item_id = wi.watch_item_id
                   WHERE wi.youtube_id = %s
                   ORDER BY wi.user_id, wd.log_date''', # Order for potential chronological listing per user
                (youtube_id,)
            )
            rows = cur.fetchall()

            for row in rows:
                user_id, model_result_id, log_data_id, model_name, result, timestamp, video_time = row
                results_by_user[user_id].append({
                    "model_result_id": model_result_id,
                    "log_data_id": log_data_id,
                    "model": model_name,
                    "result": result,
                    "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
                    "video_time": video_time # Include the video time
                })

            return {
                "status": "success",
                "youtube_id": youtube_id,
                "results_by_user": dict(results_by_user)
            }, 200

    except Exception as e:
        print(f"Error in get_model_results_by_video for youtube_id {youtube_id}: {e}")
        return {"status": "failed", "reason": "Error retrieving model results"}, 500
