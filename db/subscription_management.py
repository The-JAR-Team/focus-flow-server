from db.DB import DB


def subscribe_playlist(owner_id, data):
    """
    Subscribes a user to a playlist.

    Expected input data (dict):
      {
         "email": <str>,         // Email of the subscriber.
         "playlist_id": <int>      // The target playlist's ID.
      }
    Parameters:
      owner_id (int): The owner (creator) ID of the playlist (from the authenticated session).

    Process:
      1. Verify that the playlist exists and is owned by owner_id.
      2. Look up the subscriber's user_id in the User table using the provided email.
      3. Insert a new row in the Subscription table with:
             - user_id: subscriber's user ID,
             - playlist_id: as provided,
             - start_date: NOW().

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "reason": "subscription added"}
        On failure: {"status": "failed", "reason": "<error message>"}
    """
    try:
        with DB.get_cursor() as cur:
            playlist_id = data.get("playlist_id")
            subscriber_email = data.get("email")
            if not playlist_id or not subscriber_email:
                return {"status": "failed", "reason": "Missing playlist_id or email"}, 400

            # Verify that the playlist exists and is owned by owner_id.
            cur.execute(
                'SELECT user_id FROM "Playlist" WHERE playlist_id = %s',
                (playlist_id,)
            )
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404
            playlist_owner = result[0]
            if playlist_owner != owner_id:
                return {"status": "failed", "reason": "Not authorized: owner mismatch"}, 403

            # Look up the subscriber's user_id using their email.
            cur.execute(
                'SELECT user_id FROM "User" WHERE email = %s',
                (subscriber_email,)
            )
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "Subscriber not found"}, 404
            subscriber_id = result[0]

            # Insert the new subscription (without an active column).
            cur.execute(
                'INSERT INTO "Subscription" (user_id, playlist_id, start_date) VALUES (%s, %s, NOW())',
                (subscriber_id, playlist_id)
            )
            return {"status": "success", "reason": "subscription added"}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to subscribe"}, 500


def unsubscribe_playlist(owner_id, data):
    """
    Unsubscribes a user from a playlist.

    Expected input data (dict):
      {
         "email": <str>,         // Email of the subscriber.
         "playlist_id": <int>      // The target playlist's ID.
      }
    Parameters:
      owner_id (int): The owner (creator) ID of the playlist.

    Process:
      1. Verify that the playlist exists and is owned by owner_id.
      2. Look up the subscriber's user_id using their email.
      3. Delete the corresponding row from the Subscription table.

    Returns:
      tuple: (response_dict, http_status_code)
        On success: {"status": "success", "reason": "subscription removed"}
        On failure: {"status": "failed", "reason": "<error message>"}
    """
    try:
        with DB.get_cursor() as cur:
            playlist_id = data.get("playlist_id")
            subscriber_email = data.get("email")
            if not playlist_id or not subscriber_email:
                return {"status": "failed", "reason": "Missing playlist_id or email"}, 400

            # Verify that the playlist exists and is owned by owner_id.
            cur.execute(
                'SELECT user_id FROM "Playlist" WHERE playlist_id = %s',
                (playlist_id,)
            )
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "Playlist not found"}, 404
            playlist_owner = result[0]
            if playlist_owner != owner_id:
                return {"status": "failed", "reason": "Not authorized: owner mismatch"}, 403

            # Look up the subscriber's user_id using their email.
            cur.execute(
                'SELECT user_id FROM "User" WHERE email = %s',
                (subscriber_email,)
            )
            result = cur.fetchone()
            if result is None:
                return {"status": "failed", "reason": "Subscriber not found"}, 404
            subscriber_id = result[0]

            # Delete the subscription row.
            cur.execute(
                'DELETE FROM "Subscription" WHERE user_id = %s AND playlist_id = %s',
                (subscriber_id, playlist_id)
            )
            if cur.rowcount == 0:
                return {"status": "failed", "reason": "Subscription not found"}, 404
            return {"status": "success", "reason": "subscription removed"}, 200
    except Exception as e:
        print(e)
        return {"status": "failed", "reason": "failed to unsubscribe"}, 500
