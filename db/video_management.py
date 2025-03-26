from db.DB import DB


def upload_video(data, user_id):
    """
    Uploads a video and associates it with one or more playlists.

    Expects a JSON payload like:
    {
        "video_id": "2tM1LFFxeKg",      // goes into Video.youtube_id
        "video_name": "What makes muscles grow?",
        "subject": "Health",
        "playlists": ["Playlist A", "Playlist B"], // Array of playlist names
        "description": "Some description...",
        "length": "00:12:34",           // Will be cast to INTERVAL
        "uploadby": "Prof. Jane AI"
    }

    The user_id (an int) is provided separately for playlist lookup.

    Inserts the video into the Video table and, for each playlist name:
      - Looks for an existing playlist with that name for the given user_id.
      - If not found, creates a new playlist.
      - Inserts a row in Playlist_Item linking the video and the playlist.

    Returns a tuple: (response_dict, http_status_code)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Parse fields from the data payload.
        youtube_video_id = data.get("video_id")
        video_name = data.get("video_name")
        subject = data.get("subject")
        playlists = data.get("playlists")  # Expected to be an array of playlist names.
        description = data.get("description")
        length_str = data.get("length")  # Example: "00:12:34"
        uploadby = data.get("uploadby")

        # Insert the new video into the Video table.
        # Note: the "length" column is of type INTERVAL, so we cast the string.
        cur.execute("""
            INSERT INTO "Video" (name, description, subject_name, added_date, youtube_id, upload_by, length)
            VALUES (%s, %s, %s, NOW(), %s, %s, %s::interval)
            RETURNING video_id
        """, (video_name, description, subject, youtube_video_id, uploadby, length_str))

        new_video_id = cur.fetchone()[0]

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
            cur.execute("""
                INSERT INTO "Playlist_Item" (playlist_id, video_id)
                VALUES (%s, %s)
            """, (playlist_id, new_video_id))

        conn.commit()
        return {"status": "success", "video_id": new_video_id}, 200

    except Exception as e:
        conn.rollback()
        return {"status": "failed", "reason": str(e)}, 400


def update_video_details(data):
    """
    Updates an existing video record.

    Expects a JSON payload like:
    {
        "id": int,                  // Server's video_id (primary key)
        "video_id": "2tM1LFFxeKg",    // YouTube video id
        "video_name": "What makes muscles grow?",
        "subject": "Health",
        "description": "Some description...",
        "length": "00:12:34",         // As a string, cast to INTERVAL
        "uploadby": "Prof. Jane AI"
    }

    This function updates the record with the given id in the Video table.
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        video_pk = data.get("id")  # the server's video id (primary key)
        youtube_id = data.get("video_id")  # external YouTube video id
        video_name = data.get("video_name")
        subject = data.get("subject")
        description = data.get("description")
        length_str = data.get("length")
        uploadby = data.get("uploadby")

        if not video_pk:
            return {"status": "failed", "reason": "missing video primary id"}, 400

        # Update the video record.
        cur.execute("""
            UPDATE "Video"
            SET name = %s,
                description = %s,
                subject_name = %s,
                youtube_id = %s,
                upload_by = %s,
                length = %s::interval
            WHERE video_id = %s
        """, (video_name, description, subject, youtube_id, uploadby, length_str, video_pk))

        # Check that at least one row was updated.
        if cur.rowcount == 0:
            conn.rollback()
            return {"status": "failed", "reason": "video not found"}, 404

        conn.commit()
        return {"status": "success", "reason": "", "video_id": video_pk}, 200

    except Exception as e:
        conn.rollback()
        return {"status": "failed", "reason": str(e)}, 400
