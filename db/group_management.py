import psycopg2.errors
from datetime import datetime

from db.DB import DB
import group_item_management as gim  # For managing group items


# --- Helper to get group_id and next_item_order ---
def _get_group_details(cursor, user_id: int, group_name: str):
    """
    Helper: Retrieves group_id and next_item_order for a user and group_name.
    Returns (group_id (int), next_item_order (int)) or (None, None) if not found.
    Expects an active database cursor.
    """
    group_id_found = None
    next_order_val = None
    try:
        cursor.execute(
            'SELECT group_id, next_item_order FROM "Group" WHERE user_id = %s AND group_name = %s',
            (user_id, group_name)
        )
        group_row = cursor.fetchone()
        if group_row:
            group_id_found = group_row[0]
            next_order_val = group_row[1]
    except Exception as e:
        print(f"TODO: Error in _get_group_details for user {user_id}, group {group_name}: {e}")
    return group_id_found, next_order_val


def _increment_group_next_item_order(cursor, group_id: int):
    """
    Helper: Increments the next_item_order for a given group_id.
    Expects an active database cursor. Returns True if successful.
    """
    success = False
    try:
        cursor.execute(
            'UPDATE "Group" SET next_item_order = next_item_order + 1 WHERE group_id = %s',
            (group_id,)
        )
        if cursor.rowcount == 1:
            success = True
        else:
            print(f"TODO: Failed to increment next_item_order for group_id {group_id}, group might not exist.")
    except Exception as e:
        print(f"TODO: Error incrementing next_item_order for group {group_id}: {e}")
    return success


# --- Group Management Functions ---

def create_group(data: dict, user_id: int):
    """
    Creates a new group for the given user. Initializes next_item_order to 1 (by DB default).
    Expects data: {"group_name": <string>, "description": <string (optional)>}
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Group creation failed."}
    http_status_code = 500

    group_name = data.get("group_name")
    description = data.get("description", None)

    if not group_name:
        response_dict = {"status": "failed", "reason": "group_name is required."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                # next_item_order defaults to 1 due to table DDL
                cur.execute(
                    'INSERT INTO "Group" (user_id, group_name, description) VALUES (%s, %s, %s) RETURNING group_id, created_at, updated_at, next_item_order',
                    (user_id, group_name, description)
                )
                new_group = cur.fetchone()
                if new_group:
                    response_dict = {
                        "status": "success",
                        "message": "Group created successfully.",
                        "group_id": new_group[0],
                        "group_name": group_name,
                        "description": description,
                        "created_at": new_group[1].isoformat() if new_group[1] else None,
                        "updated_at": new_group[2].isoformat() if new_group[2] else None,
                        "next_item_order": new_group[3]
                    }
                    http_status_code = 201
                else:
                    response_dict["reason"] = "Failed to retrieve group details after creation."
        except psycopg2.errors.UniqueViolation:
            response_dict = {"status": "failed",
                             "reason": f"A group named '{group_name}' already exists for this user."}
            http_status_code = 409
        except Exception as e:
            print(f"TODO: Error in create_group: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def update_group(data: dict, user_id: int):
    """
    Updates an existing group for the given user.
    Expects data: {"old_group_name": <string>, "new_group_name": <string (optional)>, "new_description": <string (optional)>}
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Group update failed."}
    http_status_code = 500

    old_group_name = data.get("old_group_name")
    new_group_name = data.get("new_group_name")
    new_description = data.get("new_description")

    if not old_group_name:
        response_dict = {"status": "failed", "reason": "old_group_name is required."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    elif new_group_name is None and "new_description" not in data:
        response_dict = {"status": "failed",
                         "reason": "Either new_group_name or new_description must be provided for an update."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                group_id_to_update, _ = _get_group_details(cur, user_id, old_group_name)

                if not group_id_to_update:
                    response_dict = {"status": "failed", "reason": f"Group '{old_group_name}' not found for this user."}
                    http_status_code = 404
                else:
                    fields_to_update_sql = []
                    params_for_sql = []

                    if new_group_name is not None and new_group_name != old_group_name:
                        cur.execute(
                            'SELECT group_id FROM "Group" WHERE user_id = %s AND group_name = %s AND group_id != %s',
                            (user_id, new_group_name, group_id_to_update)
                        )
                        if cur.fetchone():
                            response_dict = {"status": "failed",
                                             "reason": f"A group named '{new_group_name}' already exists for this user."}
                            http_status_code = 409
                            raise psycopg2.errors.UniqueViolation("Simulated: New group name conflict")

                        fields_to_update_sql.append("group_name = %s")
                        params_for_sql.append(new_group_name)

                    if "new_description" in data:
                        fields_to_update_sql.append("description = %s")
                        params_for_sql.append(new_description)

                    if not fields_to_update_sql:
                        response_dict = {"status": "success", "message": "No changes applied to the group."}
                        http_status_code = 200
                    else:
                        fields_to_update_sql.append("updated_at = CURRENT_TIMESTAMP")
                        params_for_sql.append(group_id_to_update)

                        update_query = f'UPDATE "Group" SET {", ".join(fields_to_update_sql)} WHERE group_id = %s RETURNING group_name, description, updated_at'
                        cur.execute(update_query, tuple(params_for_sql))
                        updated_group = cur.fetchone()

                        if updated_group:
                            response_dict = {
                                "status": "success",
                                "message": "Group updated successfully.",
                                "group_id": group_id_to_update,
                                "group_name": updated_group[0],
                                "description": updated_group[1],
                                "updated_at": updated_group[2].isoformat() if updated_group[2] else None
                            }
                            http_status_code = 200
                        else:
                            response_dict["reason"] = "Failed to retrieve group details after update."

        except psycopg2.errors.UniqueViolation as e:
            if "Simulated: New group name conflict" not in str(e):
                response_dict = {"status": "failed", "reason": f"A group with the new name might already exist."}
                http_status_code = 409
            # If it IS the simulated one, response_dict and http_status_code are already set
        except Exception as e:
            print(f"TODO: Error in update_group: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def get_group_names(user_id: int):
    """
    Retrieves all group names, descriptions, and timestamps for a given user.
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to retrieve groups."}
    http_status_code = 500
    groups_list = []

    if not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'SELECT group_id, group_name, description, created_at, updated_at, next_item_order FROM "Group" WHERE user_id = %s ORDER BY group_name',
                    (user_id,)
                )
                rows = cur.fetchall()
                for row in rows:
                    groups_list.append({
                        "group_id": row[0],
                        "group_name": row[1],
                        "description": row[2],
                        "created_at": row[3].isoformat() if row[3] else None,
                        "updated_at": row[4].isoformat() if row[4] else None,
                        "next_item_order": row[5]
                    })
                response_dict = {"status": "success", "groups": groups_list}
                http_status_code = 200
        except Exception as e:
            print(f"TODO: Error in get_group_names: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def get_groups(user_id: int):
    """
    Retrieves all groups for a user, including all items (videos and playlists) within each group.
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to retrieve groups and items."}
    http_status_code = 500
    final_groups_data = []

    if not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'SELECT group_id, group_name, description, created_at, updated_at, next_item_order FROM "Group" WHERE user_id = %s ORDER BY group_name',
                    (user_id,)
                )
                groups = cur.fetchall()

                for group_row in groups:
                    group_id, group_name, description, created_at, updated_at, next_item_order = group_row

                    videos_in_group = gim.get_videos_for_group(cur, group_id)
                    playlists_in_group = gim.get_playlists_for_group(cur, group_id)

                    group_data = {
                        "group_id": group_id,
                        "group_name": group_name,
                        "description": description,
                        "created_at": created_at.isoformat() if created_at else None,
                        "updated_at": updated_at.isoformat() if updated_at else None,
                        "next_item_order": next_item_order,
                        "videos": videos_in_group,
                        "playlists": playlists_in_group
                    }
                    final_groups_data.append(group_data)

                response_dict = {"status": "success", "groups": final_groups_data}
                http_status_code = 200
        except Exception as e:
            print(f"TODO: Error in get_groups: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def get_group(user_id: int, group_name: str):
    """
    Retrieves a specific group for a user by name, including its items.
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to retrieve group."}
    http_status_code = 500
    group_data_to_return = None

    if not group_name:
        response_dict = {"status": "failed", "reason": "group_name is required."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'SELECT group_id, description, created_at, updated_at, next_item_order FROM "Group" WHERE user_id = %s AND group_name = %s',
                    (user_id, group_name)
                )
                group_info = cur.fetchone()

                if not group_info:
                    response_dict = {"status": "failed", "reason": f"Group '{group_name}' not found for this user."}
                    http_status_code = 404
                else:
                    group_id, description, created_at, updated_at, next_item_order = group_info

                    videos_in_group = gim.get_videos_for_group(cur, group_id)
                    playlists_in_group = gim.get_playlists_for_group(cur, group_id)

                    group_data_to_return = {
                        "group_id": group_id,
                        "group_name": group_name,
                        "description": description,
                        "created_at": created_at.isoformat() if created_at else None,
                        "updated_at": updated_at.isoformat() if updated_at else None,
                        "next_item_order": next_item_order,
                        "videos": videos_in_group,
                        "playlists": playlists_in_group
                    }
                    response_dict = {"status": "success", "group": group_data_to_return}
                    http_status_code = 200
        except Exception as e:
            print(f"TODO: Error in get_group: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def insert_group_item(data: dict, user_id: int):
    """
    Inserts an item (video or playlist) into a user's group, assigning it the next available order.
    If the group doesn't exist, it's created.
    Expects data: {"group_name": <string>, "item_type": <"video" or "playlist">, "item_id": <int>}
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to add item to group."}
    http_status_code = 500

    group_name = data.get("group_name")
    item_type = data.get("item_type")
    item_id = data.get("item_id")
    # item_order is now determined by next_item_order from Group table

    if not group_name or not item_type or item_id is None:
        response_dict = {"status": "failed", "reason": "group_name, item_type, and item_id are required."}
        http_status_code = 400
    elif item_type not in ["video", "playlist"]:
        response_dict = {"status": "failed", "reason": "Invalid item_type. Must be 'video' or 'playlist'."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    elif not isinstance(item_id, int) or item_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid item_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                group_id_to_use, assigned_order = _get_group_details(cur, user_id, group_name)
                item_added_successfully = False

                if not group_id_to_use:
                    # Group doesn't exist, create it. next_item_order will default to 1.
                    cur.execute(
                        'INSERT INTO "Group" (user_id, group_name) VALUES (%s, %s) RETURNING group_id, next_item_order',
                        (user_id, group_name)
                    )
                    group_id_row = cur.fetchone()
                    if not group_id_row:
                        # This should not happen if INSERT RETURNING is used and no error
                        raise Exception("Critical: Failed to create group during item insertion and retrieve ID.")
                    group_id_to_use = group_id_row[0]
                    assigned_order = group_id_row[1]  # This will be 1 for a new group
                    print(
                        f"TODO: Group '{group_name}' created for user {user_id} with id {group_id_to_use}, next_order: {assigned_order}")

                # Use assigned_order (which is the current next_item_order) for the new item
                if item_type == "video":
                    item_added_successfully = gim.add_video_to_group(cur, group_id_to_use, item_id, assigned_order)
                elif item_type == "playlist":
                    item_added_successfully = gim.add_playlist_to_group(cur, group_id_to_use, item_id, assigned_order)

                if item_added_successfully:
                    # Increment next_item_order for the group
                    if _increment_group_next_item_order(cur, group_id_to_use):
                        response_dict = {
                            "status": "success",
                            "message": f"{item_type.capitalize()} with ID {item_id} added to group '{group_name}' at order {assigned_order}."
                        }
                        http_status_code = 201
                    else:
                        response_dict = {"status": "failed",
                                         "reason": "Item added but failed to update group order. Operation rolled back."}
                        http_status_code = 500
                        raise Exception("Failed to increment group order after item insertion.")
                else:
                    # This means gim.add_..._to_group returned False (e.g. unique violation for item/order, or FK violation)
                    response_dict = {"status": "failed",
                                     "reason": f"Failed to add {item_type} ID {item_id} to group. It might already exist or the item ID is invalid."}
                    http_status_code = 409  # Or 404 if item_id was invalid and gim indicates that

        except psycopg2.errors.UniqueViolation as e:
            # This primarily catches unique violation for group name if creation was attempted and failed due to race.
            # Item-level unique violations within gim functions should ideally be handled by their False return.
            response_dict = {"status": "failed",
                             "reason": f"A group named '{group_name}' might already exist, or the item is already in the group with that order. Details: {e}"}
            http_status_code = 409
        except psycopg2.errors.ForeignKeyViolation:
            # This would catch if the item_id (video_id/playlist_id) does not exist in their respective tables.
            response_dict = {"status": "failed", "reason": f"The specified {item_type} ID {item_id} does not exist."}
            http_status_code = 404
        except Exception as e:
            print(f"TODO: Error in insert_group_item: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def remove_group_item(data: dict, user_id: int):
    """
    Removes an item (video or playlist) from a user's group.
    Expects data: {"group_name": <string>, "item_type": <"video" or "playlist">, "item_id": <int>}
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to remove item from group."}
    http_status_code = 500

    group_name = data.get("group_name")
    item_type = data.get("item_type")
    item_id = data.get("item_id")

    if not group_name or not item_type or item_id is None:
        response_dict = {"status": "failed", "reason": "group_name, item_type, and item_id are required."}
        http_status_code = 400
    elif item_type not in ["video", "playlist"]:
        response_dict = {"status": "failed", "reason": "Invalid item_type. Must be 'video' or 'playlist'."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    elif not isinstance(item_id, int) or item_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid item_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                group_id_to_use, _ = _get_group_details(cur, user_id, group_name)
                rows_affected = 0

                if not group_id_to_use:
                    response_dict = {"status": "failed", "reason": f"Group '{group_name}' not found for this user."}
                    http_status_code = 404
                else:
                    if item_type == "video":
                        rows_affected = gim.remove_video_from_group(cur, group_id_to_use, item_id)
                    elif item_type == "playlist":
                        rows_affected = gim.remove_playlist_from_group(cur, group_id_to_use, item_id)

                    if rows_affected > 0:
                        response_dict = {"status": "success",
                                         "message": f"{item_type.capitalize()} with ID {item_id} removed from group '{group_name}'."}
                        http_status_code = 200
                        # todo: Consider if item_order values need to be re-sequenced (compacted) after a deletion.
                        # For now, they will have gaps. This also means next_item_order does not need to be decremented.
                    else:
                        response_dict = {"status": "failed",
                                         "reason": f"{item_type.capitalize()} with ID {item_id} not found in group '{group_name}'."}
                        http_status_code = 404
        except Exception as e:
            print(f"TODO: Error in remove_group_item: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def remove_group(data: dict, user_id: int):
    """
    Removes a group and all its items for a user.
    (Items are removed via ON DELETE CASCADE on the Group table's group_id in junction tables)
    Expects data: {"group_name": <string>}
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to remove group."}
    http_status_code = 500

    group_name = data.get("group_name")

    if not group_name:
        response_dict = {"status": "failed", "reason": "group_name is required."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'DELETE FROM "Group" WHERE user_id = %s AND group_name = %s',
                    (user_id, group_name)
                )
                if cur.rowcount > 0:
                    response_dict = {"status": "success",
                                     "message": f"Group '{group_name}' and all its items removed successfully."}
                    http_status_code = 200
                else:
                    response_dict = {"status": "failed", "reason": f"Group '{group_name}' not found for this user."}
                    http_status_code = 404
        except Exception as e:
            print(f"TODO: Error in remove_group: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code


def switch_group_item_placement(data: dict, user_id: int):
    """
    Switches the placement (item_order) of two items within a user's group.
    Expects data: {
        "group_name": <string>,
        "item_type": <"video" or "playlist">,
        "order1": <int>, # Current order of the first item
        "order2": <int>  # Current order of the second item
    }
    Returns a tuple: (response_dict, http_status_code)
    """
    response_dict = {"status": "failed", "reason": "Failed to switch item placement."}
    http_status_code = 500

    group_name = data.get("group_name")
    item_type = data.get("item_type")
    order1 = data.get("order1")
    order2 = data.get("order2")

    if not all([group_name, item_type, isinstance(order1, int), isinstance(order2, int)]):
        response_dict = {"status": "failed",
                         "reason": "group_name, item_type, order1 (int), and order2 (int) are required."}
        http_status_code = 400
    elif item_type not in ["video", "playlist"]:
        response_dict = {"status": "failed", "reason": "Invalid item_type. Must be 'video' or 'playlist'."}
        http_status_code = 400
    elif not isinstance(user_id, int) or user_id <= 0:
        response_dict = {"status": "failed", "reason": "Invalid user_id."}
        http_status_code = 400
    elif order1 <= 0 or order2 <= 0:  # Order numbers should be positive
        response_dict = {"status": "failed", "reason": "Order numbers must be positive integers."}
        http_status_code = 400
    elif order1 == order2:
        response_dict = {"status": "success",
                         "message": "Items are already in the same order position; no switch performed."}
        http_status_code = 200
    else:
        try:
            with DB.get_cursor() as cur:
                group_id_to_use, _ = _get_group_details(cur, user_id, group_name)

                if not group_id_to_use:
                    response_dict = {"status": "failed", "reason": f"Group '{group_name}' not found for this user."}
                    http_status_code = 404
                else:
                    switched = gim.switch_item_order_in_group(cur, group_id_to_use, item_type, order1, order2)
                    if switched:
                        response_dict = {"status": "success",
                                         "message": f"Placement of items at order {order1} and {order2} in group '{group_name}' for type '{item_type}' switched successfully."}
                        http_status_code = 200
                    else:
                        response_dict = {"status": "failed",
                                         "reason": f"Could not switch items. Ensure items exist at order {order1} and {order2} of type '{item_type}' in group '{group_name}', or another error occurred."}
                        http_status_code = 404
        except Exception as e:
            print(f"TODO: Error in switch_group_item_placement: {e}")
            response_dict["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_dict, http_status_code
