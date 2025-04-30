import psycopg2.errors  # To specifically catch unique constraint errors
from db.DB import DB  # Assuming DB class handles connection/cursor

# Define the specific error code for unique violation in PostgreSQL
UNIQUE_VIOLATION_CODE = '23505'


def acquire_lock(lock_key: str) -> bool:
    """
    Attempts to acquire a distributed lock by inserting a unique key into the Generation_Locks table.

    Args:
        lock_key (str): The unique identifier for the resource to lock (e.g., "youtubeId_language").

    Returns:
        bool: True if the lock was successfully acquired, False otherwise (lock already held or DB error).
    """
    acquired = False
    try:
        with DB.get_cursor() as cur:  # Ensure commit happens if insert succeeds
            # Attempt to insert the lock key.
            # The primary key constraint on lock_key handles uniqueness.
            # created_at defaults to NOW().
            cur.execute(
                '''INSERT INTO "Generation_Locks" (lock_key)
                   VALUES (%s)''',
                (lock_key,)
            )
            # If the insert succeeds without error, the lock is acquired
            acquired = True

    except psycopg2.errors.lookup(UNIQUE_VIOLATION_CODE) as e:
        # This specific error means the lock_key already exists (lock is held)
        acquired = False
    except Exception as e:
        # Handle other potential database errors during insert
        print(f"Error acquiring lock for {lock_key}: {e}")
        acquired = False
        # Consider re-raising the exception or logging more details if needed

    return acquired


def release_lock(lock_key: str) -> bool:
    """
    Releases a distributed lock by deleting the corresponding key from the Generation_Locks table.

    Args:
        lock_key (str): The unique identifier for the resource lock to release.

    Returns:
        bool: True if the lock was successfully deleted (or didn't exist), False if a DB error occurred.
    """
    released = False
    try:
        with DB.get_cursor() as cur:  # Ensure commit happens after delete
            # Delete the lock row. It's okay if the row doesn't exist (idempotent).
            cur.execute(
                '''DELETE FROM "Generation_Locks"
                   WHERE lock_key = %s''',
                (lock_key,)
            )
            # Check if any row was actually deleted (optional, indicates if lock existed)
            # rowcount = cur.rowcount
            # print(f"Lock released for: {lock_key}. Rows affected: {rowcount}")
            released = True  # Consider success if no error occurs

    except Exception as e:
        # Handle potential database errors during delete
        print(f"Error releasing lock for {lock_key}: {e}")
        released = False
        # Consider re-raising or logging

    return released
