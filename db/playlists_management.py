from db import DB


def create_playlist(user_id, playlist_name):
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
        conn = DB.get_connection()
        cur = conn.cursor()

        # Check if a playlist with the given name already exists for this user.
        cur.execute(
            'SELECT playlist_id FROM "Playlist" WHERE user_id = %s AND playlist_name = %s',
            (user_id, playlist_name)
        )
        if cur.fetchone():
            return {"status": "failed", "reason": "Playlist with that name already exists"}, 400

        # Insert the new playlist. Permission will default to 'unlisted'.
        cur.execute(
            'INSERT INTO "Playlist" (user_id, playlist_name) VALUES (%s, %s) RETURNING playlist_id',
            (user_id, playlist_name)
        )
        new_playlist_id = cur.fetchone()[0]
        conn.commit()

        return {"status": "success", "playlist_id": new_playlist_id}, 200
    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed to create playlist"}, 500


def delete_playlist(user_id, playlist_id):
    """
    Deletes a playlist for the given user.

    Parameters:
      user_id (int): The ID of the user.
      playlist_id (int): The ID of the playlist to delete.

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "reason": "playlist deleted"}
        On failure: {"status": "failed", "reason": "<explanation>"}
    """
    try:
        conn = DB.get_connection()
        cur = conn.cursor()

        # Ensure the playlist exists and belongs to the user.
        cur.execute(
            'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
            (playlist_id, user_id)
        )
        if cur.fetchone() is None:
            return {"status": "failed", "reason": "Playlist not found or access denied"}, 404

        # Delete the playlist.
        cur.execute(
            'DELETE FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
            (playlist_id, user_id)
        )
        conn.commit()

        return {"status": "success", "reason": "Playlist deleted"}, 200
    except Exception as e:
        print(e)
        conn.rollback()
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
        conn = DB.get_connection()
        cur = conn.cursor()

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
        conn = DB.get_connection()
        cur = conn.cursor()

        # Ensure the playlist belongs to the user.
        cur.execute(
            'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
            (playlist_id, user_id)
        )
        if cur.fetchone() is None:
            return {"status": "failed", "reason": "Playlist not found or access denied"}, 404

        # Update the permission.
        cur.execute(
            'UPDATE "Playlist" SET permission = %s WHERE playlist_id = %s AND user_id = %s',
            (new_permission, playlist_id, user_id)
        )
        conn.commit()
        return {"status": "success", "reason": "Permission updated"}, 200

    except Exception as e:
        print(e)
        conn.rollback()
        return {"status": "failed", "reason": "failed to update permission"}, 500
