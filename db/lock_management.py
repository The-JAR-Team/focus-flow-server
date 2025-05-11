import logging
import time
import psycopg2.errors  # To specifically catch unique constraint errors
from db.DB import DB  # Assuming DB class handles connection/cursor

# Configure a logger for this module
logger = logging.getLogger(__name__)
# Ensure basicConfig is called only if no handlers are configured
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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


class LockAcquisitionFailed(Exception):
    """Custom exception for when a distributed lock cannot be acquired."""
    pass


class DistributedLock:
    """
    A context manager for acquiring and releasing a distributed lock
    using the Generation_Locks table. Can operate in blocking or non-blocking mode.

    Usage (non-blocking, default):
        try:
            with DistributedLock("my_resource_key", blocking=False):
                # Critical section code
                pass
        except LockAcquisitionFailed:
            # Handle lock not acquired
            pass

    Usage (blocking with timeout):
        try:
            # Will try for up to 60 seconds, retrying every 2 seconds
            with DistributedLock("my_resource_key", blocking=True, timeout=60, retry_interval=2):
                # Critical section code
                pass
        except LockAcquisitionFailed:
            # Handle lock not acquired after timeout
            pass
    """
    def __init__(self, lock_key: str, blocking: bool = False, timeout: int = 600, retry_interval: float = 5.0):
        """
        Initializes the distributed lock context manager.

        Args:
            lock_key (str): The unique identifier for the resource to lock.
            blocking (bool): If True, will attempt to acquire the lock repeatedly until timeout.
                             If False (default), will try once and raise LockAcquisitionFailed if unsuccessful.
            timeout (int): Maximum time in seconds to wait for the lock if blocking is True. Default is 600 (10 minutes).
            retry_interval (float): Time in seconds to wait between retries if blocking is True. Default is 5.0 seconds.
        """
        self.lock_key = lock_key
        self.blocking = blocking
        self.timeout = timeout
        self.retry_interval = retry_interval
        self._acquired_by_this_instance = False

    def __enter__(self):
        """
        Called when entering the 'with' statement. Attempts to acquire the lock.

        Raises:
            LockAcquisitionFailed: If the lock cannot be acquired (either immediately if non-blocking,
                                     or after timeout if blocking).

        Returns:
            self: The instance of the DistributedLock.
        """
        logger.info(
            f"Context manager: Attempting to acquire lock for key: '{self.lock_key}' "
            f"(blocking={self.blocking}, timeout={self.timeout}s, retry_interval={self.retry_interval}s)"
        )
        start_time = time.monotonic()

        while True:
            if acquire_lock(self.lock_key):
                self._acquired_by_this_instance = True
                logger.info(f"Context manager: Successfully acquired lock for key: '{self.lock_key}'")
                return self

            if not self.blocking:
                logger.warning(f"Context manager: Failed to acquire lock for key '{self.lock_key}' (non-blocking).")
                raise LockAcquisitionFailed(f"Failed to acquire lock for key '{self.lock_key}' (non-blocking).")

            elapsed_time = time.monotonic() - start_time
            if elapsed_time >= self.timeout:
                logger.error(
                    f"Context manager: Timeout ({self.timeout}s) exceeded while trying to acquire lock for key '{self.lock_key}'."
                )
                raise LockAcquisitionFailed(
                    f"Timeout ({self.timeout}s) exceeded while trying to acquire lock for key '{self.lock_key}'."
                )

            logger.info(
                f"Context manager: Lock for key '{self.lock_key}' not acquired. Retrying in {self.retry_interval}s. "
                f"Elapsed: {elapsed_time:.2f}s / {self.timeout}s"
            )
            time.sleep(self.retry_interval)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Called when exiting the 'with' statement. Ensures the lock is released
        if it was acquired by this instance.

        Args:
            exc_type: The type of the exception that caused the context to be exited (None if no exception).
            exc_val: The exception instance (None if no exception).
            exc_tb: A traceback object (None if no exception).

        Returns:
            bool: False to propagate any exceptions that occurred within the 'with' block.
        """
        if self._acquired_by_this_instance:
            logger.info(f"Context manager: Releasing lock for key: '{self.lock_key}'")
            if release_lock(self.lock_key):
                logger.info(f"Context manager: Successfully released lock for key: '{self.lock_key}'")
            else:
                logger.error(
                    f"Context manager: CRITICAL - Failed to release lock for key: '{self.lock_key}'. "
                    "Manual intervention may be required."
                )
            self._acquired_by_this_instance = False
        return False
