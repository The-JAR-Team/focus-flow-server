import json
import logging
from collections import defaultdict
from typing import Optional

import psycopg2

from db.DB import DB
from datetime import datetime

from db.ticket_management import get_tickets, set_next_ticket

logger = logging.getLogger(__name__)


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
                sql_insert_watch_item = """
                                        INSERT INTO "Watch_Item" (user_id, youtube_id, next_ticket, next_sub_ticket, \
                                                                  "current_time", last_updated)
                                        VALUES (%s, %s, 1, 1, 0.0, NOW()) ON CONFLICT (user_id, youtube_id) DO \
                                        UPDATE \
                                            SET next_ticket = GREATEST("Watch_Item".next_ticket, 2), \
                                            next_sub_ticket = GREATEST("Watch_Item".next_sub_ticket, 2) \
                                        RETURNING watch_item_id, "current_time", last_updated \
                                        """
                cur.execute(sql_insert_watch_item, (user_id, youtube_id))
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
                       wd.vid_watch_time, -- Get the video time associated with the log
                       wd.ticket,
                       wd.sub_ticket
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
                user_id, model_result_id, log_data_id, model_name, result, timestamp, video_time, ticket, sub_ticket = row
                results_by_user[user_id].append({
                    "model_result_id": model_result_id,
                    "log_data_id": log_data_id,
                    "model": model_name,
                    "result": result,
                    "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
                    "video_time": video_time,
                    "ticket": ticket,
                    "sub_ticket": sub_ticket
                })

            return {
                "status": "success",
                "youtube_id": youtube_id,
                "results_by_user": dict(results_by_user)
            }, 200

    except Exception as e:
        print(f"Error in get_model_results_by_video for youtube_id {youtube_id}: {e}")
        return {"status": "failed", "reason": "Error retrieving model results"}, 500


def store_model_result(log_data_id, model_name, result):
    """
    Store the model result in the database.

    Args:
        log_data_id (int): ID of the log data entry.
        model_name (str): Name of the model.
        result (float): Attention score.
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                '''INSERT INTO "Model_Result"
                   (log_data_id, model, result)
                   VALUES (%s, %s, %s)
                   RETURNING model_result_id''',
                (log_data_id, model_name, result)
            )
            model_result_id = cur.fetchone()[0]
            print(f"Stored model result with ID: {model_result_id}")
    except Exception as e:
        print(f"Error storing model result: {e}")


def log_watch_batch_client_tickets(user_id: int, session_id: str, common_youtube_id: str,
                                   batch_current_time_video: float, common_model_name: Optional[str],
                                   items_data_array: list):
    """
    Logs a batch of watch data items. A single main_ticket and sub_ticket pair,
    determined by the server for the given session_id and common_youtube_id,
    is used for all items in this batch.
    The server calls ticket_management.get_tickets() or ticket_management.set_next_ticket()
    once at the beginning of the batch processing.

    Args:
        user_id (int): The ID of the authenticated user.
        session_id (str): The current session ID.
        common_youtube_id (str): The YouTube ID common to all items in the batch.
        batch_current_time_video (float): The video timestamp when the batch was sent.
        common_model_name (str, optional): The model name common to all items if results are present.
        items_data_array (list): A list of dictionaries, each representing a watch data item.
            Client no longer sends main_ticket or sub_ticket per item.
            Each item must contain:
                "item_current_time_video": float
                "extraction_type": str
                "interval_seconds": float
                "fps_at_extraction": int
            Optional fields in each item's "payload_details":
                "extracted_time_utc": str (ISO 8601 format, e.g., "2023-10-26T10:30:00Z")
                "client_processing_duration_ms": int
            Optional field in item:
                "model_result": float (if common_model_name is provided)
    Returns:
        tuple: (response_dict, http_status_code)
    """
    if not all([user_id, session_id, common_youtube_id, items_data_array is not None]):
        logger.error("log_watch_batch_client_tickets: Missing required arguments.")
        return {"status": "failed", "reason": "Missing required arguments for batch logging."}, 400

    if not isinstance(items_data_array, list):
        logger.error("log_watch_batch_client_tickets: items_data_array must be a list.")
        return {"status": "failed", "reason": "items_data_array must be a list."}, 400

    processed_count = 0
    watch_item_id = None
    batch_main_ticket = None
    batch_sub_ticket = None

    try:
        with DB.get_cursor() as cur:
            # Step 1: Ensure Watch_Item exists for this user and video.
            cur.execute(
                '''SELECT watch_item_id
                   FROM "Watch_Item"
                   WHERE user_id = %s
                     AND youtube_id = %s''',
                (user_id, common_youtube_id)
            )
            watch_item_row = cur.fetchone()

            if watch_item_row:
                watch_item_id = watch_item_row[0]
            else:
                logger.info(f"Watch_Item not found for user {user_id}, youtube {common_youtube_id}. Creating it.")
                cur.execute(
                    '''INSERT INTO "Watch_Item" (user_id, youtube_id, "current_time", last_updated)
                       VALUES (%s, %s, %s, NOW()) RETURNING watch_item_id''',
                    (user_id, common_youtube_id, batch_current_time_video)
                )
                watch_item_id = cur.fetchone()[0]

            if not watch_item_id:
                logger.error(f"Failed to create or find Watch_Item for user {user_id}, youtube {common_youtube_id}.")
                return {"status": "failed", "reason": "Failed to establish Watch_Item."}, 500

            # Step 2: Determine the single main_ticket and sub_ticket for this entire batch.
            # These tickets are associated with the session_id and common_youtube_id in Watch_Ticket.

            existing_main_ticket, existing_sub_ticket = get_tickets(session_id, common_youtube_id)

            if existing_main_ticket is not None and existing_sub_ticket is not None:
                batch_main_ticket = existing_main_ticket
                batch_sub_ticket = existing_sub_ticket
                logger.info(
                    f"Using existing tickets for batch: Main={batch_main_ticket}, Sub={batch_sub_ticket} for session {session_id}, youtube {common_youtube_id}")
            else:
                # No entry in Watch_Ticket for this session/video, or get_tickets failed.
                # Call set_next_ticket to establish the first main ticket (and sub_ticket 1) in Watch_Ticket.
                # This also interacts with Watch_Item to get the *actual* next main ticket number for the user/video.
                ticket_info = set_next_ticket(user_id, session_id, common_youtube_id)
                if not ticket_info:
                    logger.error(
                        f"Failed to set initial tickets for user {user_id}, session {session_id}, youtube {common_youtube_id}.")
                    return {"status": "failed", "reason": "Failed to initialize batch tickets."}, 500
                batch_main_ticket = ticket_info["main_ticket"]
                batch_sub_ticket = ticket_info["sub_ticket"]  # Should be 1 from set_next_ticket
                logger.info(
                    f"Established new tickets for batch: Main={batch_main_ticket}, Sub={batch_sub_ticket} for session {session_id}, youtube {common_youtube_id}")

            if batch_main_ticket is None or batch_sub_ticket is None:
                logger.error(
                    f"Failed to determine batch tickets for session {session_id}, youtube {common_youtube_id}.")
                return {"status": "failed", "reason": "Ticket determination failed."}, 500

            # Process each item in the batch using the determined batch_main_ticket and batch_sub_ticket
            for item_data in items_data_array:
                item_current_time = item_data.get("item_current_time_video")
                extraction_type = item_data.get("extraction_type")
                interval_seconds = item_data.get("interval_seconds")
                fps_at_extraction = item_data.get("fps_at_extraction")
                model_result = item_data.get("model_result")
                payload_details = item_data.get("payload_details", {})

                if not all([isinstance(item_current_time, (int, float)),
                            extraction_type, isinstance(interval_seconds, (int, float)),
                            isinstance(fps_at_extraction, int)]):
                    logger.warning(f"Skipping item due to missing or invalid required fields: {item_data}")
                    continue

                # Determine log_date for Watch_Data
                log_date_for_item = psycopg2.extensions.AsIs('NOW()')  # Default to server time
                extracted_time_utc_str = payload_details.get("extracted_time_utc")
                if extracted_time_utc_str:
                    try:
                        # Attempt to parse ISO 8601 string.
                        log_date_for_item = extracted_time_utc_str
                    except ValueError:
                        logger.warning(
                            f"Invalid extracted_time_utc format: '{extracted_time_utc_str}'. Falling back to NOW().")

                # Step 3: Insert into Watch_Data using the batch_main_ticket and batch_sub_ticket
                cur.execute(
                    '''INSERT INTO "Watch_Data" (watch_item_id, log_date, vid_watch_time, "interval", ticket,
                                                 sub_ticket)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING watch_data_id''',
                    (watch_item_id, log_date_for_item, item_current_time, interval_seconds, batch_main_ticket,
                     batch_sub_ticket)
                )
                watch_data_id = cur.fetchone()[0]

                # Step 4 & 5: Insert into Log_Data and Model_Result if model data is present
                if common_model_name and common_model_name.strip() and model_result is not None:
                    client_processing_ms = payload_details.get("client_processing_duration_ms")

                    cur.execute(
                        '''INSERT INTO "Log_Data" (watch_data_id, fps_num, extraction_type)
                           VALUES (%s, %s, %s) RETURNING log_data_id''',
                        (watch_data_id, fps_at_extraction, extraction_type)
                    )
                    log_data_id = cur.fetchone()[0]

                    cur.execute(
                        '''INSERT INTO "Model_Result" (log_data_id, model, result, client_processing_ms)
                           VALUES (%s, %s, %s, %s)''',
                        (log_data_id, common_model_name, model_result, client_processing_ms)
                    )
                processed_count += 1

            # Step 6: Update Watch_Item's overall current_time to batch_current_time_video
            if processed_count > 0:
                cur.execute(
                    '''UPDATE "Watch_Item"
                       SET "current_time" = %s,
                           last_updated   = NOW()
                       WHERE watch_item_id = %s''',
                    (batch_current_time_video, watch_item_id)
                )

            logger.info(
                f"Successfully processed {processed_count} items for batch (user {user_id}, youtube {common_youtube_id}).")
            return {"status": "success", "message": f"Processed {processed_count} items."}, 200

    except psycopg2.Error as db_err:
        logger.error(f"Database error during batch watch log for user {user_id}, youtube {common_youtube_id}: {db_err}")
        return {"status": "failed", "reason": f"Database error: {db_err}"}, 500
    except Exception as e:
        logger.error(f"Unexpected error during batch watch log for user {user_id}, youtube {common_youtube_id}: {e}",
                     exc_info=True)
        return {"status": "failed", "reason": f"Unexpected server error: {e}"}, 500
