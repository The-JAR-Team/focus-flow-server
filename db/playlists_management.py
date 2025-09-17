import logging

from db.DB import DB
import psycopg2

logger = logging.getLogger(__name__)


def create_playlist(user_id, playlist_name, playlist_permission='unlisted'):
    """
    Creates a new playlist for the given user if one with the same name doesn't already exist.
    The playlist will have a default permission of 'unlisted'.
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE user_id = %s AND playlist_name = %s',
                (user_id, playlist_name)
            )
            if cur.fetchone():
                return {"status": "failed", "reason": "Playlist with that name already exists"}, 400

            # Insert the new playlist, initializing next_item_order to 1.
            cur.execute(
                'INSERT INTO "Playlist" (user_id, playlist_name, permission, next_item_order) VALUES (%s, %s, %s, 1) RETURNING playlist_id',
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
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
                (playlist_id, user_id)
            )
            if cur.fetchone() is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

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
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                'SELECT playlist_id FROM "Playlist" WHERE playlist_id = %s AND user_id = %s',
                (playlist_id, user_id)
            )
            if cur.fetchone() is None:
                return {"status": "failed", "reason": "Playlist not found or not owned by user"}, 404

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
    Removes a playlist item and re-orders the remaining items.
    """
    playlist_item_id = data.get("playlist_item_id")
    if not playlist_item_id:
        return {"status": "failed", "reason": "missing playlist_item_id"}, 400

    try:
        with DB.get_cursor() as cur:
            # Get item details and verify ownership.
            cur.execute("""
                SELECT pi.playlist_id, pi.item_order, p.user_id
                FROM "Playlist_Item" pi
                JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
                WHERE pi.playlist_item_id = %s
            """, (playlist_item_id,))
            result = cur.fetchone()

            if result is None:
                return {"status": "failed", "reason": "playlist item not found"}, 404

            playlist_id, item_order, owner_user_id = result
            if owner_user_id != user_id:
                return {"status": "failed", "reason": "not authorized to remove this playlist item"}, 403

            # Delete the specified playlist item.
            cur.execute("""
                DELETE FROM "Playlist_Item"
                WHERE playlist_item_id = %s
            """, (playlist_item_id,))

            # Re-order the remaining items in the playlist to fill the gap.
            cur.execute("""
                UPDATE "Playlist_Item"
                SET item_order = item_order - 1
                WHERE playlist_id = %s AND item_order > %s
            """, (playlist_id, item_order))

            # Decrement the next_item_order counter for the playlist.
            cur.execute("""
                UPDATE "Playlist"
                SET next_item_order = next_item_order - 1
                WHERE playlist_id = %s
            """, (playlist_id,))

        return {"status": "success", "reason": "Item removed and playlist re-ordered", "removed_playlist_item_id": playlist_item_id}, 200

    except Exception as e:
        logger.error(f"Failed to remove playlist item {playlist_item_id} for user {user_id}: {e}", exc_info=True)
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
        with DB.get_cursor() as cur:
            cur.execute("""
                SELECT 1 FROM "Playlist" WHERE playlist_name = %s AND user_id = %s LIMIT 1
            """, (new_name, user_id))
            if cur.fetchone():
                return {"status": "failed", "reason": f"Playlist with name '{new_name}' already exists"}, 400

            cur.execute("""
                SELECT playlist_id FROM "Playlist"
                WHERE playlist_name = %s AND user_id = %s
                LIMIT 1
            """, (old_name, user_id))
            result = cur.fetchone()

            if result is None:
                return {"status": "failed", "reason": f"Playlist with name '{old_name}' not found"}, 404

            playlist_id = result[0]

            cur.execute("""
                UPDATE "Playlist"
                SET playlist_name = %s
                WHERE playlist_id = %s
            """, (new_name, playlist_id))

        return {"status": "success", "reason": "Playlist name updated", "playlist_id": playlist_id}, 200

    except Exception as e:
        logger.error(f"Failed to update playlist name from '{old_name}' for user {user_id}: {e}", exc_info=True)
        return {"status": "failed", "reason": "failed to update playlist name"}, 500


def get_playlist_subscribers(owner_id, playlist_id):
    """
    Retrieves subscriber details (email, full name) for a playlist,
    verifying ownership first.
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id FROM "Playlist" WHERE playlist_id = %s', (playlist_id,))
            row = cur.fetchone()
            if row is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

            if row[0] != owner_id:
                return {"status": "failed", "reason": "Not authorized"}, 403

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
            subscribers = [
                {
                    "email": r[0],
                    "full_name": f"{r[1] or ''} {r[2] or ''}".strip()
                }
                for r in rows
            ]
        return {"status": "success", "subscribers": subscribers}, 200

    except Exception as e:
        logger.error(f"Error getting subscribers for playlist {playlist_id}, owner {owner_id}: {e}", exc_info=True)
        return {"status": "failed", "reason": "failed to get subscribers"}, 500


def get_playlist_subscriber_count(owner_id, playlist_id):
    """
    Returns the number of subscribers for a given playlist_id,
    only if the playlist is owned by owner_id.
    """
    try:
        with DB.get_cursor() as cur:
            cur.execute('SELECT user_id FROM "Playlist" WHERE playlist_id = %s', (playlist_id,))
            row = cur.fetchone()
            if row is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404

            playlist_owner = row[0]
            if playlist_owner != owner_id:
                return {"status": "failed", "reason": "Not authorized to view subscriber for this playlist"}, 403

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


def update_playlist_item_order(user_id, playlist_item_id, new_order):
    """
    Updates the order of a specific item in a playlist, ensuring no two items
    have the same order by shifting subsequent items.
    """
    if not isinstance(new_order, int) or new_order <= 0:
        return {"status": "failed", "reason": "new_order must be a positive integer"}, 400

    try:
        with DB.get_cursor() as cur:
            # 1. Get current item details, playlist_id, and verify ownership in one go.
            cur.execute("""
                SELECT
                    pi.playlist_id,
                    pi.item_order,
                    p.user_id,
                    (SELECT MAX(item_order) FROM "Playlist_Item" WHERE playlist_id = p.playlist_id) as max_order
                FROM "Playlist_Item" pi
                JOIN "Playlist" p ON pi.playlist_id = p.playlist_id
                WHERE pi.playlist_item_id = %s
            """, (playlist_item_id,))
            result = cur.fetchone()

            if result is None:
                return {"status": "failed", "reason": "Playlist item not found"}, 404

            playlist_id, old_order, owner_id, max_order = result

            if owner_id != user_id:
                return {"status": "failed", "reason": "Not authorized to update this item"}, 403

            # 2. Validate new_order against the max order.
            if new_order > max_order:
                return {"status": "failed", "reason": f"new_order ({new_order}) cannot be greater than the max order ({max_order})"}, 400

            if new_order == old_order:
                return {"status": "success", "reason": "Item is already at the requested order"}, 200

            # 3. Perform the reordering within the transaction.
            if new_order > old_order:
                # Item is moving DOWN the list. Shift items between old and new UP.
                cur.execute("""
                    UPDATE "Playlist_Item"
                    SET item_order = item_order - 1
                    WHERE playlist_id = %s AND item_order > %s AND item_order <= %s
                """, (playlist_id, old_order, new_order))
            else:  # new_order < old_order
                # Item is moving UP the list. Shift items between new and old DOWN.
                cur.execute("""
                    UPDATE "Playlist_Item"
                    SET item_order = item_order + 1
                    WHERE playlist_id = %s AND item_order >= %s AND item_order < %s
                """, (playlist_id, new_order, old_order))

            # 4. Place the moved item into its new, now-vacant position.
            cur.execute("""
                UPDATE "Playlist_Item"
                SET item_order = %s
                WHERE playlist_item_id = %s
            """, (new_order, playlist_item_id))

        return {"status": "success", "reason": "Item order updated successfully"}, 200
    except Exception as e:
        logger.error(f"Failed to update order for playlist item {playlist_item_id}: {e}", exc_info=True)
        return {"status": "failed", "reason": "Failed to update item order"}, 500

