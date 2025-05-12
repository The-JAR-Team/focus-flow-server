import logging

from db.DB import DB
import psycopg2

logger = logging.getLogger(__name__)


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
    Removes a playlist item using the DB context manager.
    """
    playlist_item_id = data.get("playlist_item_id")
    if not playlist_item_id:
        return {"status": "failed", "reason": "missing playlist_item_id"}, 400

    try:
        # Use the context manager
        with DB.get_cursor() as cur:
            # Verify the playlist item belongs to a playlist owned by the user.
            cur.execute("""
                SELECT p.user_id
                FROM "Playlist_Item" pi
                JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
                WHERE pi.playlist_item_id = %s
            """, (playlist_item_id,))
            result = cur.fetchone()

            if result is None:
                # No DB change, context manager handles connection return
                return {"status": "failed", "reason": "playlist item not found"}, 404 # Changed to 404 Not Found

            owner_user_id = result[0]
            if owner_user_id != user_id:
                 # No DB change, context manager handles connection return
                return {"status": "failed", "reason": "not authorized to remove this playlist item"}, 403 # Changed to 403 Forbidden

            # Delete the playlist item.
            cur.execute("""
                DELETE FROM "Playlist_Item"
                WHERE playlist_item_id = %s
            """, (playlist_item_id,))
            # Commit is handled automatically by the context manager on successful exit

        # Return success outside the 'with' block
        return {"status": "success", "reason": "", "removed_playlist_item_id": playlist_item_id}, 200

    except Exception as e:
        logger.error(f"Failed to remove playlist item {playlist_item_id} for user {user_id}: {e}", exc_info=True)
        # Rollback is handled automatically by the context manager on exception
        # Return a generic server error
        return {"status": "failed", "reason": "failed to remove playlist item"}, 500


def update_playlist_name(user_id, data):
    """
    Updates the name of a user's playlist using the DB context manager.
    """
    old_name = data.get("old_name")
    new_name = data.get("new_name")

    if not old_name or not new_name:
        return {"status": "failed", "reason": "Missing old_name or new_name"}, 400

    try:
         # Use the context manager
        with DB.get_cursor() as cur:
            # Check if new name already exists for this user (optional but good practice)
            cur.execute("""
                SELECT 1 FROM "Playlist" WHERE playlist_name = %s AND user_id = %s LIMIT 1
            """, (new_name, user_id))
            if cur.fetchone():
                 return {"status": "failed", "reason": f"Playlist with name '{new_name}' already exists"}, 400

            # Find the playlist by old name
            cur.execute("""
                SELECT playlist_id FROM "Playlist"
                WHERE playlist_name = %s AND user_id = %s
                LIMIT 1
            """, (old_name, user_id))
            result = cur.fetchone()

            if result is None:
                 # No DB change, context manager handles connection return
                return {"status": "failed", "reason": f"Playlist with name '{old_name}' not found"}, 404

            playlist_id = result[0]

            # Update the playlist name.
            cur.execute("""
                UPDATE "Playlist"
                SET playlist_name = %s
                WHERE playlist_id = %s
            """, (new_name, playlist_id))
            # Commit is handled automatically by context manager on successful exit

        # Return success outside 'with' block
        return {"status": "success", "reason": "Playlist name updated", "playlist_id": playlist_id}, 200

    except Exception as e:
        logger.error(f"Failed to update playlist name from '{old_name}' for user {user_id}: {e}", exc_info=True)
         # Rollback is handled automatically by context manager on exception
        return {"status": "failed", "reason": "failed to update playlist name"}, 500


def get_playlist_subscribers(owner_id, playlist_id):
    """
    Retrieves subscriber details (email, full name) for a playlist,
    verifying ownership first. (Already compatible, minor logging added).
    """
    try:
        with DB.get_cursor() as cur:
            # Verify ownership
            cur.execute('SELECT user_id FROM "Playlist" WHERE playlist_id = %s', (playlist_id,))
            row = cur.fetchone()
            if row is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

            if row[0] != owner_id:
                return {"status": "failed", "reason": "Not authorized"}, 403

            # Retrieve subscribers
            cur.execute(
                '''
                SELECT u.email, u.first_name, u.last_name
                FROM "Subscription" s
                JOIN "User" u ON s.user_id = u.user_id
                WHERE s.playlist_id = %s
                ''',
                (playlist_id,)
            )
            rows = cur.fetchall()
            # No commit/rollback needed for SELECT
            subscribers = [
                {
                    "email": r[0],
                    "full_name": f"{r[1] or ''} {r[2] or ''}".strip()
                }
                for r in rows
            ]
        return {"status": "success", "subscribers": subscribers}, 200

    except Exception as e: # Catch any other errors
        logger.error(f"Error getting subscribers for playlist {playlist_id}, owner {owner_id}: {e}", exc_info=True)
        return {"status": "failed", "reason": "failed to get subscribers"}, 500


def get_playlist_subscriber_count(owner_id, playlist_id):
    """
    Returns the number of subscribers for a given playlist_id,
    only if the playlist is owned by owner_id.

    Args:
        owner_id (int): The user who owns the playlist.
        playlist_id (int): The playlist ID.

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
    try:
        with DB.get_cursor() as cur:
            # Verify ownership
            cur.execute('SELECT user_id FROM "Playlist" WHERE playlist_id = %s', (playlist_id,))
            row = cur.fetchone()
            if row is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

            playlist_owner = row[0]
            if playlist_owner != owner_id:
                return {"status": "failed", "reason": "Not authorized to view subscriber for this playlist"}, 403

            # Count the subscribers
            cur.execute(
                '''
                SELECT COUNT(*)
                FROM "Subscription"
                WHERE playlist_id = %s
                ''',
                (playlist_id,)
            )
            count = cur.fetchone()[0]

            return {"status": "success", "count": count}, 200
    except Exception as e:
        print("Error in get_playlist_subscriber_count:", e)
        return {"status": "failed", "reason": str(e)}, 500
