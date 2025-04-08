from db.DB import DB
from datetime import datetime


def log_watch(user_id, data):
    """
    Logs or updates watch data for the given user and video.

    Expects:
    {
      "video_id": <int>,
      "current_time": <float>,   // optional, defaults to 0.0 if missing
    }

    If a Watch_Item row already exists for (user_id, video_id), it updates it.
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
            video_id = data.get("youtube_id")
            if not video_id:
                return {"status": "failed", "reason": "Missing video_id"}, 400

            current_time = data.get("current_time", 0.0)

            # Check if a watch item already exists for (user_id, video_id).
            cur.execute(
                '''SELECT watch_item_id
                   FROM "Watch_Item"
                   WHERE user_id = %s AND video_id = %s
                   LIMIT 1''',
                (user_id, video_id)
            )
            row = cur.fetchone()

            if row is None:
                # Insert a new watch item
                cur.execute(
                    '''INSERT INTO "Watch_Item"
                       (user_id, video_id, current_time, last_updated)
                       VALUES (%s, %s, %s, NOW())
                       RETURNING watch_item_id''',
                    (user_id, video_id, current_time)
                )
                watch_item_id = cur.fetchone()[0]
            else:
                # Update existing watch item
                watch_item_id = row[0]
                cur.execute(
                    '''UPDATE "Watch_Item"
                       SET current_time = %s,
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
      "video_id": <int>
    }

    Returns: (response_dict, http_status_code)

    Example success:
      {
        "status": "success",
        "watch_item": {
          "watch_item_id": <int>,
          "video_id": <int>,
          "current_watch_time": <int>,
          "time_before_jump": <int>,
          "last_updated": <string date>
        }
      }, 200

    If no watch item is found, returns a 404 with a "not found" reason.
    """
    try:
        with DB.get_cursor() as cur:
            video_id = data.get("video_id")
            if not video_id:
                return {"status": "failed", "reason": "Missing video_id"}, 400

            cur.execute(
                '''SELECT watch_item_id, current_time, last_updated
                   FROM "Watch_Item"
                   WHERE user_id = %s AND video_id = %s''',
                (user_id, video_id)
            )
            row = cur.fetchone()

            if row is None:
                return {"status": "failed", "reason": "Watch item not found"}, 404

            watch_item_id, current_time, last_updated = row
            return {
                "status": "success",
                "watch_item": {
                    "watch_item_id": watch_item_id,
                    "video_id": video_id,
                    "current_time": current_time,
                    "last_updated": str(last_updated) if last_updated else None
                }
            }, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "Error retrieving watch item"}, 500
