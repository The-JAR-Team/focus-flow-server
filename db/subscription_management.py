import psycopg2 # Import for specific error handling like UniqueViolation
from db.DB import DB


def subscribe_playlist(owner_id, data):
    """
    Subscribes a user (identified by email) to a specific playlist,
    ensuring the requestor owns the playlist.

    Args:
        owner_id (int): The user_id of the user making the request (assumed playlist owner).
        data (dict): Dictionary containing 'playlist_id' (int) and 'email' (str) of the user to subscribe.

    Returns:
        tuple: A tuple containing:
            - response (dict): {"status": "success/failed", "reason": "message"}
            - status_code (int): HTTP status code (e.g., 201, 400, 403, 404, 409, 500).
    """
    # Initialize default failure response. These will be updated upon success or specific errors.
    response = {"status": "failed", "reason": "failed to subscribe"}
    status_code = 500 # Default to Internal Server Error

    try:
        playlist_id = data.get("playlist_id")
        subscriber_email = data.get("email")

        # --- 1. Input Validation ---
        if not isinstance(playlist_id, int) or not isinstance(subscriber_email, str) or not subscriber_email:
            # Check if essential data is missing or of the wrong type
            response["reason"] = "Missing or invalid playlist_id (int) or email (str)"
            status_code = 400 # Bad Request
        else:
            # --- Use context manager for cursor and transaction handling ---
            with DB.get_cursor() as cur:
                # --- 2. Verify Playlist Existence and Ownership ---
                cur.execute(
                    'SELECT user_id FROM "Playlist" WHERE playlist_id = %s',
                    (playlist_id,)
                )
                playlist_result = cur.fetchone()

                if playlist_result is None:
                    # Playlist does not exist
                    response["reason"] = f"Playlist with ID {playlist_id} not found"
                    status_code = 404 # Not Found
                elif playlist_result[0] != owner_id:
                    # Playlist found, but does not belong to the requestor
                    response["reason"] = "Not authorized: You do not own this playlist"
                    status_code = 403 # Forbidden
                else:
                    # --- 3. Find Subscriber's User ID ---
                    cur.execute(
                        'SELECT user_id FROM "User" WHERE email = %s',
                        (subscriber_email,)
                    )
                    user_result = cur.fetchone()

                    if user_result is None:
                        # User with the provided email does not exist
                        response["reason"] = f"User with email {subscriber_email} not found"
                        status_code = 404 # Not Found
                    else:
                        # --- 4. Attempt to Insert Subscription ---
                        subscriber_id = user_result[0]
                        try:
                            # Execute the INSERT command
                            cur.execute(
                                '''
                                INSERT INTO "Subscription" (user_id, playlist_id, start_date)
                                VALUES (%s, %s, NOW())
                                ''',
                                (subscriber_id, playlist_id)
                            )
                            # If INSERT succeeds (no exception), update to success response
                            response = {"status": "success", "reason": "Subscription added successfully"}
                            status_code = 201 # Created - Appropriate for successful resource creation

                        except psycopg2.errors.UniqueViolation:
                            # Specific handling if the user is already subscribed (primary key or unique constraint violation)
                            # The DB context manager (get_cursor) will automatically rollback on exception.
                            response["reason"] = "User is already subscribed to this playlist"
                            status_code = 409 # Conflict - Indicates the request cannot be processed because of conflict
                        # Other psycopg2 errors during INSERT will be caught by the outer db_err handler below

    except psycopg2.Error as db_err:
        # Handle general database errors (connection, syntax, etc.) not caught specifically above
        print(f"Database error in subscribe_playlist: {db_err}")
        response["reason"] = f"Database error occurred: {db_err}"
        # Keep status_code 500 (Internal Server Error)
    except Exception as e:
        # Handle any other unexpected errors during execution
        print(f"Unexpected error in subscribe_playlist: {e}")
        response["reason"] = f"An unexpected server error occurred: {e}"
        # Keep status_code 500 (Internal Server Error)

    # --- Single Return Point ---
    return response, status_code


def unsubscribe_playlist(owner_id, data):
    """
    Unsubscribes a user (identified by email) from a specific playlist,
    ensuring the requestor owns the playlist.

    Args:
        owner_id (int): The user_id of the user making the request (assumed playlist owner).
        data (dict): Dictionary containing 'playlist_id' (int) and 'email' (str) of the user to unsubscribe.

    Returns:
        tuple: A tuple containing:
            - response (dict): {"status": "success/failed", "reason": "message"}
            - status_code (int): HTTP status code (e.g., 200, 204, 400, 403, 404, 500).
    """
    # Initialize default failure response
    response = {"status": "failed", "reason": "failed to unsubscribe"}
    status_code = 500 # Default to Internal Server Error

    try:
        playlist_id = data.get("playlist_id")
        subscriber_email = data.get("email")

        # --- 1. Input Validation ---
        if not isinstance(playlist_id, int) or not isinstance(subscriber_email, str) or not subscriber_email:
            response["reason"] = "Missing or invalid playlist_id (int) or email (str)"
            status_code = 400 # Bad Request
        else:
             # --- Use context manager for cursor and transaction handling ---
            with DB.get_cursor() as cur:
                # --- 2. Verify Playlist Existence and Ownership ---
                # (Same check as in subscribe_playlist)
                cur.execute(
                    'SELECT user_id FROM "Playlist" WHERE playlist_id = %s',
                    (playlist_id,)
                )
                playlist_result = cur.fetchone()

                if playlist_result is None:
                    response["reason"] = f"Playlist with ID {playlist_id} not found"
                    status_code = 404 # Not Found
                elif playlist_result[0] != owner_id:
                    response["reason"] = "Not authorized: You do not own this playlist"
                    status_code = 403 # Forbidden
                else:
                    # --- 3. Find Subscriber's User ID ---
                    # (Same check as in subscribe_playlist)
                    cur.execute(
                        'SELECT user_id FROM "User" WHERE email = %s',
                        (subscriber_email,)
                    )
                    user_result = cur.fetchone()

                    if user_result is None:
                        response["reason"] = f"User with email {subscriber_email} not found"
                        status_code = 404 # Not Found
                    else:
                        # --- 4. Attempt to Delete Subscription ---
                        subscriber_id = user_result[0]
                        cur.execute(
                            'DELETE FROM "Subscription" WHERE user_id = %s AND playlist_id = %s',
                            (subscriber_id, playlist_id)
                        )

                        # --- 5. Check if a row was actually deleted ---
                        if cur.rowcount == 0:
                            # No subscription found matching the user and playlist
                            response["reason"] = "Subscription not found for this user and playlist"
                            status_code = 404 # Not Found - The specific resource (subscription) to delete was not found
                        else:
                            # Deletion successful, update to success response
                            response = {"status": "success", "reason": "Subscription removed successfully"}
                            status_code = 200 # OK - Or 204 No Content if you prefer not to send a body on success
                            # If using 204, the response dict might be ignored by the framework/client

    except psycopg2.Error as db_err:
        # Handle general database errors
        print(f"Database error in unsubscribe_playlist: {db_err}")
        response["reason"] = f"Database error occurred: {db_err}"
        # Keep status_code 500
    except Exception as e:
        # Handle any other unexpected errors
        print(f"Unexpected error in unsubscribe_playlist: {e}")
        response["reason"] = f"An unexpected server error occurred: {e}"
        # Keep status_code 500

    # --- Single Return Point ---
    return response, status_code
