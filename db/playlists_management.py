from db.DB import DB


def create_playlist(user_id, playlist_name, playlist_permission='unlisted'):
    """
    Creates a new playlist for the given user if one with the same name doesn't already exist.
    The playlist will have a default permission of 'unlisted'.

    Parameters:
      user_id (int): The ID of the user.
      playlist_name (str): The name of the playlist.

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "playlist_id": <new_playlist_id>}
        On failure: {"status": "failed", "reason": "<explanation>"}
    """
    try:
        with DB.get_cursor() as cur:
            # Check if a playlist with the given name already exists for this user.
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE user_id = %s AND playlist_name = %s',
                (user_id, playlist_name)
            )
            if cur.fetchone():
                return {"status": "failed", "reason": "Playlist with that name already exists"}, 400

            # Insert the new playlist; permission defaults to 'unlisted'.
            cur.execute(
                'INSERT INTO "Playlist" (user_id, playlist_name, permission) VALUES (%s, %s, %s) RETURNING playlist_id',
                (user_id, playlist_name, playlist_permission)
            )
            new_playlist_id = cur.fetchone()[0]
            return {"status": "success", "playlist_id": new_playlist_id}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to create playlist"}, 500


def delete_playlist(user_id, playlist_id):
    """
    Deletes a playlist for the given user.

    Parameters:
      user_id (int): The ID of the user.
      playlist_id (int): The ID of the playlist to delete.

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "reason": "Playlist deleted"}
        On failure: {"status": "failed", "reason": "<explanation>"}
    """
    try:
        with DB.get_cursor() as cur:
            # Ensure the playlist exists and belongs to the user.
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
                (playlist_id, user_id)
            )
            if cur.fetchone() is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

            # Delete the playlist.
            cur.execute(
                'DELETE FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
                (playlist_id, user_id)
            )
            return {"status": "success", "reason": "Playlist deleted"}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to delete playlist"}, 500


def get_all_user_playlists(user_id):
    """
    Retrieves all playlists for a given user.

    Parameters:
      user_id (int): The ID of the user.

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "playlists": [ { "playlist_id": <id>, "playlist_name": <name>, "permission": <permission> }, ... ]}
        On failure: {"status": "failed", "reason": "<explanation>"}
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT playlist_id, playlist_name, permission FROM "Playlist" WHERE user_id = %s ORDER BY playlist_id',
                (user_id,)
            )
            rows = cur.fetchall()
            playlists = [
                {"playlist_id": row[0], "playlist_name": row[1], "permission": row[2]}
                for row in rows
            ]
            return {"status": "success", "playlists": playlists}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to fetch playlists"}, 500


def update_playlist_permission(user_id, playlist_id, new_permission):
    """
    Updates the permission of a playlist belonging to a user.

    Parameters:
      user_id (int): The ID of the user.
      playlist_id (int): The ID of the playlist to update.
      new_permission (str): The new permission value ("public", "unlisted", or "private").

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "reason": "Permission updated"}
        On failure: {"status": "failed", "reason": "<explanation>"}
    """
    try:
        with DB.get_cursor() as cur:
            # Ensure the playlist belongs to the user.
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
                (playlist_id, user_id)
            )
            if cur.fetchone() is None:
                return {"status": "failed", "reason": "Playlist not found or not owned by user"}, 404

            # Update the permission.
            cur.execute(
                'UPDATE "Playlist" SET permission = %s WHERE playlist_id = %s AND user_id = %s',
                (new_permission, playlist_id, user_id)
            )
            return {"status": "success", "reason": "Permission updated"}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to update permission"}, 500


def remove_from_playlist(user_id, data):
    """
    Removes a playlist item.

    Expects:
      user_id (int): The ID of the user making the request.
      data (dict): JSON payload containing:
          {
             "playlist_item_id": <int>
          }

    Process:
      1. Verify that the playlist item exists and that the playlist it belongs to is owned by user_id.
      2. Delete the playlist item.

    Returns a tuple: (response_dict, http_status_code)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        playlist_item_id = data.get("playlist_item_id")
        if not playlist_item_id:
            return ({"status": "failed", "reason": "missing playlist_item_id"}, 400)

        # Verify the playlist item belongs to a playlist owned by the user.
        cur.execute("""
            SELECT p.user_id
            FROM "Playlist_Item" pi
            JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
            WHERE pi.playlist_item_id = %s
        """, (playlist_item_id,))
        result = cur.fetchone()
        if result is None:
            return ({"status": "failed", "reason": "playlist item not found"}, 400)

        owner_user_id = result[0]
        if owner_user_id != user_id:
            return ({"status": "failed", "reason": "not authorized to remove this playlist item"}, 400)

        # Delete the playlist item.
        cur.execute("""
            DELETE FROM "Playlist_Item"
            WHERE playlist_item_id = %s
        """, (playlist_item_id,))
        conn.commit()

        return ({"status": "success", "reason": "", "removed_playlist_item_id": playlist_item_id}, 200)
    except Exception as e:
        conn.rollback()
        return ({"status": "failed", "reason": str(e)}, 400)


def update_playlist_name(user_id, data):
    """
    Updates the name of a user's playlist.

    Expects a JSON payload like:
    {
      "old_name": "Old Playlist Name",
      "new_name": "New Playlist Name"
    }

    The function searches for a playlist owned by the given user with the specified old name.
    If found, it updates the playlist_name to the new name.

    Returns:
      tuple: (response_dict, http_status_code)
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        old_name = data.get("old_name")
        new_name = data.get("new_name")

        if not old_name or not new_name:
            return ({"status": "failed", "reason": "Missing old_name or new_name"}, 400)

        # Search for the playlist with the given old name for this user.
        cur.execute("""
            SELECT playlist_id FROM "Playlist"
            WHERE playlist_name = %s AND user_id = %s
            LIMIT 1
        """, (old_name, user_id))
        result = cur.fetchone()
        if result is None:
            return ({"status": "failed", "reason": "Playlist with the given old_name not found"}, 404)

        playlist_id = result[0]

        # Update the playlist name.
        cur.execute("""
            UPDATE "Playlist"
            SET playlist_name = %s
            WHERE playlist_id = %s
        """, (new_name, playlist_id))

        conn.commit()
        return ({"status": "success", "reason": "Playlist name updated", "playlist_id": playlist_id}, 200)

    except Exception as e:
        conn.rollback()
        return ({"status": "failed", "reason": str(e)}, 500)
