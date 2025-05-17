# group_item_management.py
import psycopg2.errors
from datetime import datetime


def add_video_to_group(cursor, group_id: int, video_id: int, item_order: int):
    """
    Adds a video to a specific group's video items with a given order.
    Expects an active database cursor.
    Returns True if successful, False otherwise.
    """
    success = False
    try:
        cursor.execute(
            'INSERT INTO "Group_Video_Item" (group_id, video_id, item_order) VALUES (%s, %s, %s)',
            (group_id, video_id, item_order)
        )
        success = True
    except psycopg2.errors.UniqueViolation:
        print(
            f"TODO: Unique constraint violation: Video ID {video_id} might already be in group ID {group_id}, or order {item_order} is taken.")
        success = False
    except psycopg2.errors.ForeignKeyViolation:
        print(f"TODO: Foreign key violation: Video ID {video_id} or Group ID {group_id} does not exist.")
        success = False
    except Exception as e:
        print(f"TODO: Error adding video {video_id} to group {group_id}: {e}")
        success = False
    return success


def add_playlist_to_group(cursor, group_id: int, playlist_id: int, item_order: int):
    """
    Adds a playlist to a specific group's playlist items with a given order.
    Expects an active database cursor.
    Returns True if successful, False otherwise.
    """
    success = False
    try:
        cursor.execute(
            'INSERT INTO "Group_Playlist_Item" (group_id, playlist_id, item_order) VALUES (%s, %s, %s)',
            (group_id, playlist_id, item_order)
        )
        success = True
    except psycopg2.errors.UniqueViolation:
        print(
            f"TODO: Unique constraint violation: Playlist ID {playlist_id} might already be in group ID {group_id}, or order {item_order} is taken.")
        success = False
    except psycopg2.errors.ForeignKeyViolation:
        print(f"TODO: Foreign key violation: Playlist ID {playlist_id} or Group ID {group_id} does not exist.")
        success = False
    except Exception as e:
        print(f"TODO: Error adding playlist {playlist_id} to group {group_id}: {e}")
        success = False
    return success


def remove_video_from_group(cursor, group_id: int, video_id: int):
    """
    Removes a video from a specific group.
    Expects an active database cursor.
    Returns the number of rows deleted (0 or 1).
    """
    rows_deleted = 0
    try:
        cursor.execute(
            'DELETE FROM "Group_Video_Item" WHERE group_id = %s AND video_id = %s',
            (group_id, video_id)
        )
        rows_deleted = cursor.rowcount
    except Exception as e:
        print(f"TODO: Error removing video {video_id} from group {group_id}: {e}")
    return rows_deleted


def remove_playlist_from_group(cursor, group_id: int, playlist_id: int):
    """
    Removes a playlist from a specific group.
    Expects an active database cursor.
    Returns the number of rows deleted (0 or 1).
    """
    rows_deleted = 0
    try:
        cursor.execute(
            'DELETE FROM "Group_Playlist_Item" WHERE group_id = %s AND playlist_id = %s',
            (group_id, playlist_id)
        )
        rows_deleted = cursor.rowcount
    except Exception as e:
        print(f"TODO: Error removing playlist {playlist_id} from group {group_id}: {e}")
    return rows_deleted


def get_videos_for_group(cursor, group_id: int):
    """
    Retrieves all videos associated with a specific group_id, ordered by item_order.
    Expects an active database cursor.
    Returns a list of video dictionaries.
    """
    videos_list = []
    try:
        cursor.execute(
            '''
            SELECT v.video_id, v.name, v.youtube_id, v.description AS video_description, 
                   v.length, v.upload_by, v.added_date AS video_added_date, 
                   gvi.added_at AS added_to_group_at, gvi.item_order
            FROM "Group_Video_Item" gvi
            JOIN "Video" v ON gvi.video_id = v.video_id
            WHERE gvi.group_id = %s
            ORDER BY gvi.item_order ASC, gvi.added_at ASC
            ''',
            (group_id,)
        )
        video_items = cursor.fetchall()
        for item in video_items:
            videos_list.append({
                "video_id": item[0],
                "name": item[1],
                "youtube_id": item[2],
                "description": item[3],
                "length": str(item[4]) if item[4] else None,
                "upload_by": item[5],
                "video_added_date": item[6].isoformat() if item[6] else None,
                "added_to_group_at": item[7].isoformat() if item[7] else None,
                "item_order": item[8]
            })
    except Exception as e:
        print(f"TODO: Error fetching videos for group {group_id}: {e}")
    return videos_list


def get_playlists_for_group(cursor, group_id: int):
    """
    Retrieves all playlists associated with a specific group_id, ordered by item_order.
    Expects an active database cursor.
    Returns a list of playlist dictionaries.
    """
    playlists_list = []
    try:
        cursor.execute(
            '''
            SELECT p.playlist_id, p.playlist_name, p.permission AS playlist_permission, 
                   p.user_id AS playlist_owner_id, 
                   gpi.added_at AS added_to_group_at, gpi.item_order
            FROM "Group_Playlist_Item" gpi
            JOIN "Playlist" p ON gpi.playlist_id = p.playlist_id
            WHERE gpi.group_id = %s
            ORDER BY gpi.item_order ASC, gpi.added_at ASC
            ''',
            (group_id,)
        )
        playlist_items = cursor.fetchall()
        for item in playlist_items:
            playlists_list.append({
                "playlist_id": item[0],
                "playlist_name": item[1],
                "permission": item[2],
                "playlist_owner_id": item[3],
                "added_to_group_at": item[4].isoformat() if item[4] else None,
                "item_order": item[5]
            })
    except Exception as e:
        print(f"TODO: Error fetching playlists for group {group_id}: {e}")
    return playlists_list


def switch_item_order_in_group(cursor, group_id: int, item_type: str, order1: int, order2: int):
    """
    Swaps the item_order of two items within the same group and of the same type.
    Items are identified by their current order values.
    Expects an active database cursor.
    Returns True if successful and two distinct items were found and swapped, False otherwise.
    """
    swapped_successfully = False
    junction_table_name = ""
    id_column_name = ""  # The actual ID column of the item (e.g., video_id, playlist_id)

    if item_type == "video":
        junction_table_name = '"Group_Video_Item"'
        id_column_name = "video_id"
    elif item_type == "playlist":
        junction_table_name = '"Group_Playlist_Item"'
        id_column_name = "playlist_id"
    else:
        print(f"TODO: Invalid item_type '{item_type}' for switching order.")
        return False

    if not isinstance(order1, int) or not isinstance(order2, int) or order1 <= 0 or order2 <= 0:
        print(f"TODO: Invalid order numbers for switching: {order1}, {order2}.")
        return False

    if order1 == order2:
        # No switch needed if orders are the same, consider this a "success" in terms of state.
        return True

    try:
        # Find the primary IDs (video_id or playlist_id) of the items at the given order positions
        sql_find_item1 = f'SELECT {id_column_name} FROM {junction_table_name} WHERE group_id = %s AND item_order = %s'
        cursor.execute(sql_find_item1, (group_id, order1))
        item1_row = cursor.fetchone()

        sql_find_item2 = f'SELECT {id_column_name} FROM {junction_table_name} WHERE group_id = %s AND item_order = %s'
        cursor.execute(sql_find_item2, (group_id, order2))
        item2_row = cursor.fetchone()

        if item1_row and item2_row:
            item1_pk_id = item1_row[0]  # Actual ID of the video/playlist at order1
            item2_pk_id = item2_row[0]  # Actual ID of the video/playlist at order2

            if item1_pk_id == item2_pk_id:
                print(
                    f"TODO: Items at order {order1} and {order2} are the same item (ID: {item1_pk_id}). No swap needed.")
                swapped_successfully = True
            else:
                # Perform the swap
                # Update item1's order to order2
                sql_update1 = f'UPDATE {junction_table_name} SET item_order = %s WHERE group_id = %s AND {id_column_name} = %s AND item_order = %s'
                cursor.execute(sql_update1, (order2, group_id, item1_pk_id, order1))

                # Update item2's order to order1
                sql_update2 = f'UPDATE {junction_table_name} SET item_order = %s WHERE group_id = %s AND {id_column_name} = %s AND item_order = %s'
                cursor.execute(sql_update2, (order1, group_id, item2_pk_id, order2))

                # Assuming success if no exceptions were raised during the updates.
                # For more robustness, you could check cursor.rowcount for each update.
                swapped_successfully = True
        else:
            print(
                f"TODO: One or both items not found at specified orders ({order1}, {order2}) in group {group_id} for type {item_type}.")
            # swapped_successfully remains False

    except Exception as e:
        print(f"TODO: Error switching item order in group {group_id} for type {item_type}: {e}")
        # swapped_successfully remains False
    return swapped_successfully
