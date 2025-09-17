import datetime
import logging

from db.DB import DB

logger = logging.getLogger(__name__)


def upload_video(data, user_id):
    """
    Uploads a video and associates it with playlists using the DB context manager.
    Handles item ordering within playlists.
    """
    # Parse fields from the data payload.
    youtube_video_id = data.get("video_id")
    video_name = data.get("video_name")
    subject = data.get("subject")
    playlists = data.get("playlists")  # Expected list of names
    description = data.get("description")
    length_str = data.get("length")
    uploadby = data.get("uploadby")

    # --- Input Validation ---
    if not all([youtube_video_id, video_name, subject, playlists, length_str]):
        return {"status": "failed", "reason": "Missing required video fields (video_id, name, subject, playlists, length)."}, 400
    if not isinstance(playlists, list) or len(playlists) == 0:
        return {"status": "failed", "reason": "Playlists must be a non-empty list of names."}, 400

    new_video_id = None  # Initialize
    try:
        # --- Use the context manager ---
        # A single transaction for the entire upload process
        with DB.get_cursor() as cur:
            # Insert the new video into the Video table.
            cur.execute("""
                            INSERT INTO "Video" (name, description, subject_name, added_date, youtube_id, upload_by, "length")
                            VALUES (%s, %s, %s, NOW(), %s, %s, %s::interval)
                            RETURNING video_id
                        """, (video_name, description, subject, youtube_video_id, uploadby, length_str))

            result = cur.fetchone()
            if result is None:
                raise Exception("Failed to insert or update video record.")
            new_video_id = result[0]

            # Process each playlist in the provided playlists array.
            for pl_name in playlists:
                # Look for an existing playlist with this name for the given user.
                cur.execute("""
                    SELECT playlist_id, next_item_order FROM "Playlist"
                    WHERE playlist_name = %s AND user_id = %s
                """, (pl_name, user_id))
                row = cur.fetchone()
                if row is None:
                    # Create a new playlist if not found, starting with a counter of 1.
                    cur.execute("""
                        INSERT INTO "Playlist" (playlist_name, user_id, next_item_order)
                        VALUES (%s, %s, 1)
                        RETURNING playlist_id
                    """, (pl_name, user_id))
                    playlist_id = cur.fetchone()[0]
                    current_order = 1
                else:
                    playlist_id, current_order = row

                # Insert a record in Playlist_Item linking the playlist and the new video with the correct order.
                cur.execute("""
                    INSERT INTO "Playlist_Item" (playlist_id, video_id, item_order)
                    VALUES (%s, %s, %s)
                """, (playlist_id, new_video_id, current_order))

                # Increment the next_item_order for the playlist.
                cur.execute("""
                    UPDATE "Playlist" SET next_item_order = %s
                    WHERE playlist_id = %s
                """, (current_order + 1, playlist_id))

        return {"status": "success", "video_id": new_video_id}, 201

    except Exception as e:
        logger.error(f"Failed to upload video {youtube_video_id} for user {user_id}: {e}", exc_info=True)
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
    if not all([youtube_id, video_name, subject, length_str]):
        return {"status": "failed", "reason": "Missing required fields for video update."}, 400

    video_pk = None  # Initialize
    try:
        with DB.get_cursor() as cur:
            cur.execute("""
                SELECT pi.video_id, p.user_id
                FROM "Playlist_Item" pi
                JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
                WHERE pi.playlist_item_id = %s
            """, (playlist_item_id,))
            result = cur.fetchone()

            if result is None:
                return {"status": "failed", "reason": "playlist item not found"}, 404

            video_pk, owner_user_id = result

            if owner_user_id != user_id:
                return {"status": "failed", "reason": "not authorized to update video via this playlist item"}, 403

            cur.execute("""
                UPDATE "Video"
                SET name = %s,
                    description = %s,
                    subject_name = %s,
                    youtube_id = %s,
                    upload_by = %s,
                    "length" = %s::interval
                WHERE video_id = %s
            """, (video_name, description, subject, youtube_id, uploadby, length_str, video_pk))

            if cur.rowcount == 0:
                logger.warning(
                    f"Update video details: Video with pk {video_pk} not found for update, though playlist item exists.")
                return {"status": "failed", "reason": "video associated with playlist item not found"}, 404

        return {"status": "success", "reason": "", "video_id": video_pk}, 200

    except Exception as e:
        logger.error(
            f"Failed to update video details for playlist_item {playlist_item_id}, user {user_id}: {e}", exc_info=True)
        return {"status": "failed", "reason": "failed to update video details"}, 500


def get_accessible_videos(user_id):
    """
    Returns a nested JSON-like structure of all playlists (and their videos)
    that the specified user can access, ordered by the item_order.
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
                  pi.item_order,
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
                ORDER BY p.playlist_id, pi.item_order;
            """

            cur.execute(sql, {"user_id": user_id})
            rows = cur.fetchall()

            playlists_map = {}

            for row in rows:
                playlist_id = row[0]
                playlist_name = row[1]
                playlist_permission = row[2]
                owner_id = row[3]
                owner_first_name = row[4]
                owner_last_name = row[5]
                playlist_item_id = row[6]
                item_order = row[7]
                video_id = row[8]
                video_name = row[9]
                video_desc = row[10]
                subject = row[11]
                external_id = row[12]
                upload_by = row[13]
                length = row[14]
                watch_item_id = row[15]
                current_time = row[16]
                last_updated = row[17]
                added_date = row[18]

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

                watch_item_data = None
                if watch_item_id is not None:
                    watch_item_data = {
                        "watch_item_id": watch_item_id,
                        "current_time": current_time,
                        "last_updated": str(last_updated) if last_updated else None
                    }

                playlists_map[playlist_id]["playlist_items"].append({
                    "playlist_item_id": playlist_item_id,
                    "item_order": item_order,
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
