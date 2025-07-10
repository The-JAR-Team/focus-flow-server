from db.DB import DB
import logging
import psycopg2

logger = logging.getLogger(__name__)


def set_next_ticket(user_id: int, session_id: str, youtube_id: str):
    """
    Assigns a new main ticket. Creates Watch_Item if it doesn't exist.
    The sub_ticket is reset to 1 for this new main ticket instance.
    Updates Watch_Ticket for the given session_id.

    Args:
        user_id (int): The user's identifier.
        session_id (str): The session identifier (for Watch_Ticket PK).
        youtube_id (str): The YouTube video identifier.

    Returns:
        dict: {"main_ticket": <int>, "sub_ticket": <int>} on success,
              None on failure.
    """
    return_value = None
    assigned_main_ticket = None
    assigned_sub_ticket = None  # For a new main ticket instance, sub_ticket is 1

    if not all([user_id, session_id, youtube_id]):
        logger.error("set_next_ticket: user_id, session_id, and youtube_id are required.")
    else:
        try:
            with DB.get_cursor() as cur:
                # Try to update Watch_Item and get the current main ticket value
                sql_update_watch_item = """
                                        UPDATE "Watch_Item"
                                        SET next_ticket     = next_ticket + 1,
                                            next_sub_ticket = next_sub_ticket + 1
                                        WHERE user_id = %s \
                                          AND youtube_id = %s RETURNING next_ticket - 1, next_sub_ticket - 1; -- Returns the value of next_ticket *before* this increment \
                                        """
                cur.execute(sql_update_watch_item, (user_id, youtube_id))
                row = cur.fetchone()

                if row:
                    assigned_main_ticket = row[0]
                    assigned_sub_ticket = row[1]
                else:
                    logger.info(f"Watch_Item not found for user {user_id}, youtube {youtube_id}. Creating it.")
                    sql_insert_watch_item = """
                                            INSERT INTO "Watch_Item" (user_id, youtube_id, next_ticket, next_sub_ticket, \
                                                                      "current_time", last_updated)
                                            VALUES (%s, %s, 2, 2, 0.0, NOW()) ON CONFLICT (user_id, youtube_id) DO \
                                            UPDATE \
                                                SET next_ticket = GREATEST("Watch_Item".next_ticket, 2), \
                                                next_sub_ticket = GREATEST("Watch_Item".next_sub_ticket, 2)
                                            """
                    cur.execute(sql_insert_watch_item, (user_id, youtube_id))
                    assigned_main_ticket = 1  # We are assigning main_ticket 1 for this operation
                    assigned_sub_ticket = 1  # Sub ticket starts at 1 for the new main ticket

                # Proceed if assigned_main_ticket is determined
                if assigned_main_ticket is not None:
                    sql_upsert_watch_ticket = """
                                              INSERT INTO "Watch_Ticket" (youtube_id, session_id, ticket, sub_ticket)
                                              VALUES (%s, %s, %s, %s) ON CONFLICT (youtube_id, session_id)
                        DO \
                                              UPDATE SET ticket = EXCLUDED.ticket, \
                                                  sub_ticket = EXCLUDED.sub_ticket; \
                                              """
                    cur.execute(sql_upsert_watch_ticket,
                                (youtube_id, session_id, assigned_main_ticket, assigned_sub_ticket))
                    logger.info(
                        f"Set next ticket for user {user_id}, session {session_id}, youtube {youtube_id} to {assigned_main_ticket}.{assigned_sub_ticket}")
                    return_value = {"main_ticket": assigned_main_ticket, "sub_ticket": assigned_sub_ticket}
                else:
                    # This path should ideally not be hit if INSERT works
                    logger.error(f"Failed to determine assigned_main_ticket for user {user_id}, youtube {youtube_id}.")

        except psycopg2.Error as e:
            logger.error(
                f"Database error in set_next_ticket (user {user_id}, session {session_id}, video {youtube_id}): {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error in set_next_ticket (user {user_id}, session {session_id}, video {youtube_id}): {e}")

    return return_value


def set_next_sub_ticket(user_id: int, session_id: str, youtube_id: str):
    """
    Assigns the next sub_ticket. Creates Watch_Item if it doesn't exist.
    If no main ticket has been assigned yet to Watch_Ticket for this session,
    it behaves like set_next_ticket.

    Args:
        user_id (int): The user's identifier.
        session_id (str): The session identifier.
        youtube_id (str): The YouTube video identifier.

    Returns:
        dict: {"main_ticket": <int>, "sub_ticket": <int>} on success,
              None on failure.
    """
    return_value = None
    final_main_ticket = None
    final_sub_ticket = None

    if not all([user_id, session_id, youtube_id]):
        logger.error("set_next_sub_ticket: user_id, session_id, and youtube_id are required.")
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'SELECT ticket FROM "Watch_Ticket" WHERE youtube_id = %s AND session_id = %s',
                    (youtube_id, session_id)
                )
                watch_ticket_row = cur.fetchone()

                if watch_ticket_row is None:
                    logger.info(
                        f"No existing Watch_Ticket for session {session_id}, youtube {youtube_id}. Calling set_next_ticket logic.")
                    return_value = set_next_ticket(user_id, session_id, youtube_id)
                else:
                    final_main_ticket = watch_ticket_row[0]

                    sql_update_watch_item_sub_ticket = """
                                                       UPDATE "Watch_Item"
                                                       SET next_sub_ticket = next_sub_ticket + 1
                                                       WHERE user_id = %s \
                                                         AND youtube_id = %s RETURNING next_sub_ticket - 1; \
                                                       """
                    cur.execute(sql_update_watch_item_sub_ticket, (user_id, youtube_id))
                    watch_item_sub_row = cur.fetchone()

                    if watch_item_sub_row:
                        final_sub_ticket = watch_item_sub_row[0]
                    else:
                        # Watch_Item not found for this user/video, create it.
                        # This is an edge case: Watch_Ticket exists for session, but Watch_Item for user/video is missing.
                        # We are about to use sub_ticket 1 for the final_main_ticket.
                        # Watch_Item's next_ticket should be for the *next* main ticket (final_main_ticket + 1).
                        # Watch_Item's next_sub_ticket should be 2.
                        logger.info(
                            f"Watch_Item not found for user {user_id}, youtube {youtube_id} during sub_ticket update. Creating it.")
                        sql_insert_watch_item = """
                                                INSERT INTO "Watch_Item" (user_id, youtube_id, next_ticket, \
                                                                          next_sub_ticket, "current_time", last_updated)
                                                VALUES (%s, %s, %s, 2, 0.0, NOW()) ON CONFLICT (user_id, youtube_id) DO \
                                                UPDATE \
                                                    SET next_ticket = GREATEST("Watch_Item".next_ticket, EXCLUDED.next_ticket), \
                                                    next_sub_ticket = GREATEST("Watch_Item".next_sub_ticket, 2)
                                                -- Removed semicolon from end of SET clause \
                                                """
                        cur.execute(sql_insert_watch_item, (user_id, youtube_id, final_main_ticket + 1))
                        final_sub_ticket = 1  # Assigning sub_ticket 1 for the current main_ticket

                    if final_sub_ticket is not None:
                        sql_update_watch_ticket = """
                                                  UPDATE "Watch_Ticket" \
                                                  SET sub_ticket = %s
                                                  WHERE youtube_id = %s \
                                                    AND session_id = %s; \
                                                  """
                        cur.execute(sql_update_watch_ticket, (final_sub_ticket, youtube_id, session_id))
                        logger.info(
                            f"Set next sub-ticket for user {user_id}, session {session_id}, youtube {youtube_id} to {final_main_ticket}.{final_sub_ticket}")
                        return_value = {"main_ticket": final_main_ticket, "sub_ticket": final_sub_ticket}
                    else:
                        logger.error(f"Failed to determine final_sub_ticket for user {user_id}, youtube {youtube_id}.")

        except psycopg2.Error as e:
            logger.error(
                f"Database error in set_next_sub_ticket (user {user_id}, session {session_id}, video {youtube_id}): {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error in set_next_sub_ticket (user {user_id}, session {session_id}, video {youtube_id}): {e}")

    return return_value


def get_tickets(session_id: str, youtube_id: str):
    """
    Retrieves the current ticket and sub_ticket for the given session_id and youtube_id
    from the Watch_Ticket table.

    Args:
        session_id (str): The session identifier.
        youtube_id (str): The YouTube video identifier.

    Returns:
        tuple: (ticket, sub_ticket) if found, otherwise (None, None).
    """
    return_ticket = None
    return_sub_ticket = None

    if not session_id or not youtube_id:
        logger.error("get_tickets: session_id and youtube_id are required.")
    else:
        try:
            with DB.get_cursor() as cur:
                cur.execute(
                    'SELECT ticket, sub_ticket FROM "Watch_Ticket" WHERE youtube_id = %s AND session_id = %s',
                    (youtube_id, session_id)
                )
                row = cur.fetchone()
                if row:
                    return_ticket = row[0]
                    return_sub_ticket = row[1]
                else:
                    logger.info(f"No Watch_Ticket found for session {session_id}, youtube {youtube_id}")
        except psycopg2.Error as e:
            logger.error(f"Database error in get_tickets for session {session_id}, youtube {youtube_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in get_tickets for session {session_id}, youtube {youtube_id}: {e}")

    return return_ticket, return_sub_ticket
