import datetime
import logging

from db.DB import DB

logger = logging.getLogger(__name__)


def upload_video(data, user_id):
    """
    Uploads a video and associates it with playlists using the DB context manager.
    """
    # Parse fields from the data payload.
    youtube_video_id = data.get("video_id")
    video_name = data.get("video_name")
    subject = data.get("subject")
    playlists = data.get("playlists") # Expected list of names
    description = data.get("description")
    length_str = data.get("length")
    uploadby = data.get("uploadby")

    # --- Input Validation ---
    if not all([youtube_video_id, video_name, subject, playlists, length_str]):
        return {"status": "failed", "reason": "Missing required video fields (video_id, name, subject, playlists, length)."}, 400
    if not isinstance(playlists, list) or len(playlists) == 0:
        return {"status": "failed", "reason": "Playlists must be a non-empty list of names."}, 400

    new_video_id = None # Initialize
    try:
        # --- Use the context manager ---
        # A single transaction for the entire upload process
        with DB.get_cursor() as cur:
            # Insert the new video into the Video table.
            cur.execute("""
                INSERT INTO "Video" (name, description, subject_name, added_date, youtube_id, upload_by, "length")
                VALUES (%s, %s, %s, NOW(), %s, %s, %s::interval)
                ON CONFLICT (youtube_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    subject_name = EXCLUDED.subject_name,
                    upload_by = EXCLUDED.upload_by,
                    length = EXCLUDED.length,
                    added_date = NOW() -- Update added_date on conflict too? Or keep original?
                RETURNING video_id
            """, (video_name, description, subject, youtube_video_id, uploadby, length_str))

            result = cur.fetchone()
            if result is None:
                # Should not happen with RETURNING if INSERT/UPDATE worked
                 raise Exception("Failed to insert or update video record.")
            new_video_id = result[0]

            # Process each playlist in the provided playlists array.
            for pl_name in playlists:
                # Look for an existing playlist with this name for the given user.
                cur.execute("""
                    SELECT playlist_id FROM "Playlist"
                    WHERE playlist_name = %s AND user_id = %s
                """, (pl_name, user_id))
                row = cur.fetchone()
                if row is None:
                    # Create a new playlist if not found.
                    cur.execute("""
                        INSERT INTO "Playlist" (playlist_name, user_id)
                        VALUES (%s, %s)
                        RETURNING playlist_id
                    """, (pl_name, user_id))
                    playlist_id = cur.fetchone()[0]
                else:
                    playlist_id = row[0]

                # Insert a record in Playlist_Item linking the playlist and the new video.
                # Add ON CONFLICT DO NOTHING to avoid errors if the link already exists
                cur.execute("""
                    INSERT INTO "Playlist_Item" (playlist_id, video_id)
                    VALUES (%s, %s)
                    ON CONFLICT (playlist_id, video_id) DO NOTHING
                """, (playlist_id, new_video_id))

            # Commit is handled automatically by context manager on successful exit

        # Return success outside the 'with' block
        return {"status": "success", "video_id": new_video_id}, 201 # 201 Created is often suitable here

    except Exception as e:
        logger.error(f"Failed to upload video {youtube_video_id} for user {user_id}: {e}", exc_info=True)
        # Rollback is handled automatically by context manager on exception
        return {"status": "failed", "reason": "failed to upload video"}, 500

def update_video_details(data, user_id):
    """
    Updates an existing video record using the DB context manager.
    """
    # Extract data from payload.
    playlist_item_id = data.get("playlist_item_id")
    youtube_id = data.get("video_id")
    video_name = data.get("video_name")
    subject = data.get("subject")
    description = data.get("description")
    length_str = data.get("length")
    uploadby = data.get("uploadby")

    # --- Input Validation ---
    if not playlist_item_id:
        return {"status": "failed", "reason": "missing playlist_item_id"}, 400
    # Add checks for other fields if they are mandatory for update
    if not all([youtube_id, video_name, subject, length_str]):
         return {"status": "failed", "reason": "Missing required fields for video update."}, 400

    video_pk = None # Initialize
    try:
         # --- Use the context manager ---
        with DB.get_cursor() as cur:
            # Retrieve the video_id from Playlist_Item and verify ownership via the Playlist table.
            cur.execute("""
                SELECT pi.video_id, p.user_id
                FROM "Playlist_Item" pi
                JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
                WHERE pi.playlist_item_id = %s
            """, (playlist_item_id,))
            result = cur.fetchone()

            if result is None:
                # No DB change, context manager handles connection return
                return {"status": "failed", "reason": "playlist item not found"}, 404

            video_pk, owner_user_id = result

            # Check that the playlist belongs to the authenticated user.
            if owner_user_id != user_id:
                # No DB change, context manager handles connection return
                return {"status": "failed", "reason": "not authorized to update video via this playlist item"}, 403

            # Update the Video record corresponding to video_pk.
            cur.execute("""
                UPDATE "Video"
                SET name = %s,
                    description = %s,
                    subject_name = %s,
                    youtube_id = %s, -- Allow updating youtube_id? Be careful if it's used elsewhere.
                    upload_by = %s,
                    "length" = %s::interval
                WHERE video_id = %s
            """, (video_name, description, subject, youtube_id, uploadby, length_str, video_pk))

            # Check that the update affected a row.
            if cur.rowcount == 0:
                # This means the video_id derived from playlist_item_id didn't exist in Video table
                # Should be rare if DB constraints are set up, but good to check.
                # Rollback is handled automatically by context manager on exception/exit if error occurs.
                # If no error but rowcount is 0, it implies the video linked does not exist.
                logger.warning(f"Update video details: Video with pk {video_pk} not found for update, though playlist item exists.")
                return {"status": "failed", "reason": "video associated with playlist item not found"}, 404

            # Commit is handled automatically by context manager on successful exit

        # Return success outside 'with' block
        return {"status": "success", "reason": "", "video_id": video_pk}, 200

    except Exception as e:
        logger.error(f"Failed to update video details for playlist_item {playlist_item_id}, user {user_id}: {e}", exc_info=True)
        # Rollback is handled automatically by context manager on exception
        return {"status": "failed", "reason": "failed to update video details"}, 500

def get_accessible_videos(user_id):
    """
    Returns a nested JSON-like structure of all playlists (and their videos)
    that the specified user can access.

    The output structure looks like:
    {
      "status": "success" or "failed",
      "playlists": [
        {
          "playlist_id": <int>,
          "playlist_name": <str>,
          "playlist_permission": <str>,
          "playlist_owner_name": <str>,
          "playlist_items": [
            {
              "playlist_item_id": <int>,
              "video_id": <int>,
              "video_name": <str>,
              "description": <str>,
              "subject": <str>,
              "external_id": <str>,   # e.g., YouTube video id
              "upload_by": <str>,
              "length": <interval string?>,
              "watch_item": {
                "watch_item_id": <int>,
                "current_time": <int>,
                "last_updated": <timestamp>
              } OR null if not found
            }, ...
          ]
        }, ...
      ]
    }
    """

    try:
        with DB.get_cursor() as cur:
            sql = """
                WITH accessible_playlists AS (
                    SELECT p.playlist_id
                      FROM "Playlist" p
                     WHERE p.user_id = %(user_id)s
                        OR p.permission = 'public'
                    UNION
                    SELECT s.playlist_id
                      FROM "Subscription" s
                      JOIN "Playlist" pl ON pl.playlist_id = s.playlist_id
                     WHERE s.user_id = %(user_id)s
                       AND pl.permission != 'private'
                )
                SELECT
                  p.playlist_id,
                  p.playlist_name,
                  p.permission as playlist_permission,
                  p.user_id as owner_id,
                  ou.first_name as owner_first_name,
                  ou.last_name as owner_last_name,
                  pi.playlist_item_id,
                  v.video_id,
                  v.name AS video_name,
                  v.description AS video_desc,
                  v.subject_name AS subject,
                  v.youtube_id AS external_id,
                  v.upload_by,
                  v."length",
                  w.watch_item_id,
                  w."current_time",
                  w.last_updated,
                  v.added_date
                FROM accessible_playlists a
                JOIN "Playlist" p ON p.playlist_id = a.playlist_id
                JOIN "User" ou ON ou.user_id = p.user_id
                JOIN "Playlist_Item" pi ON pi.playlist_id = p.playlist_id
                JOIN "Video" v ON v.video_id = pi.video_id
                LEFT JOIN "Watch_Item" w 
                       ON w.youtube_id = v.youtube_id
                      AND w.user_id = %(user_id)s
                ORDER BY p.playlist_id, pi.playlist_item_id;
            """

            cur.execute(sql, {"user_id": user_id})
            rows = cur.fetchall()

            # We'll group by playlist_id to build a nested structure.
            # Key = playlist_id, Value = dict with playlist info + items list.
            playlists_map = {}

            for row in rows:
                # Break out each field from the row
                playlist_id = row[0]
                playlist_name = row[1]
                playlist_permission = row[2]
                owner_id = row[3]
                owner_first_name = row[4]
                owner_last_name = row[5]
                playlist_item_id = row[6]
                video_id = row[7]
                video_name = row[8]
                video_desc = row[9]
                subject = row[10]
                external_id = row[11]
                upload_by = row[12]
                length = row[13]
                watch_item_id = row[14]
                current_time = row[15]
                last_updated = row[16]
                added_date = row[17]

                # If we haven't seen this playlist yet, create a dict for it.
                if playlist_id not in playlists_map:
                    owner_full_name = f"{owner_first_name} {owner_last_name}".strip()
                    playlists_map[playlist_id] = {
                        "playlist_id": playlist_id,
                        "playlist_name": playlist_name,
                        "playlist_permission": playlist_permission,
                        "playlist_owner_name": owner_full_name,
                        "playlist_owner_id": owner_id,
                        "playlist_items": []
                    }

                # Build the watch_item sub-dict only if watch_item_id is present.
                watch_item_data = None
                if watch_item_id is not None:
                    watch_item_data = {
                        "watch_item_id": watch_item_id,
                        "current_time": current_time,
                        "last_updated": str(last_updated) if last_updated else None
                    }

                # Add the item for this video
                playlists_map[playlist_id]["playlist_items"].append({
                    "playlist_item_id": playlist_item_id,
                    "video_id": video_id,
                    "video_name": video_name,
                    "description": video_desc,
                    "added_date": added_date,
                    "subject": subject,
                    "external_id": external_id,
                    "upload_by": upload_by,
                    "length": str(length) if length else None,
                    "watch_item": watch_item_data
                })

            # Convert the dictionary to a list for final JSON output
            playlists_list = list(playlists_map.values())
            return {
                "status": "success",
                "playlists": playlists_list
            }
    except Exception as e:
        print(e)
        return {
            "status": "failed",
            "reason": "error retrieving accessible videos"
        }