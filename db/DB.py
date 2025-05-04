from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg2
import psycopg2.pool  # Import the pool module
import os
import threading  # For thread lock during initialization
import logging  # Use logging for messages

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DB:
    _pool = None  # Holds the connection pool instance
    _pool_lock = threading.Lock()  # Lock for thread-safe initialization

    @classmethod
    def _init_pool(cls):
        """Initializes the ThreadedConnectionPool."""
        # This should only be called while _pool_lock is held
        if cls._pool is None:
            load_dotenv()  # Load env vars if not already loaded globally
            min_conn = int(os.getenv("DB_POOL_MIN", 1))
            max_conn = int(os.getenv("DB_POOL_MAX", 10))  # Sensible default max
            db_name = os.getenv("DB_NAME")
            db_user = os.getenv("DB_USER")
            db_host = os.getenv("DB_HOST")
            # Ensure essential DB config is present
            if not all([db_name, db_user, db_host, os.getenv("DB_PASSWORD")]):
                logger.critical("Database connection parameters missing in environment variables.")
                raise ValueError("Missing database configuration in environment variables.")

            logger.info(
                f"Initializing DB connection pool (min: {min_conn}, max: {max_conn}) for db '{db_name}' on host '{db_host}'...")
            try:
                cls._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=min_conn,
                    maxconn=max_conn,
                    host=db_host,
                    user=db_user,
                    password=os.getenv("DB_PASSWORD"),
                    dbname=db_name,
                    port=os.getenv("DB_PORT", 5432)
                    # Add other psycopg2 connection params if needed (e.g., sslmode)
                )
                logger.info("DB connection pool initialized successfully.")
            except psycopg2.OperationalError as e:
                logger.critical(f"Failed to connect to database during pool initialization: {e}")
                raise RuntimeError(f"Database connection failed: {e}") from e
            except Exception as e:
                logger.critical(f"Failed to initialize DB connection pool: {e}")
                # Decide how to handle this critical error (e.g., raise, exit)
                raise RuntimeError(f"Failed to initialize DB connection pool: {e}") from e
        else:
            logger.warning("Pool initialization called when pool already exists.")

    @classmethod
    def get_pool(cls):
        """
        Gets the connection pool, initializing it thread-safely on first access.
        """
        # Quick check without lock first for performance
        if cls._pool is None:
            # Acquire lock only if pool might be None
            with cls._pool_lock:
                # Double-check inside lock to prevent race condition
                if cls._pool is None:
                    cls._init_pool()
        # Raise error if pool initialization failed previously and _pool is still None
        if cls._pool is None:
            raise RuntimeError("DB Pool is not available (initialization likely failed).")
        return cls._pool

    @classmethod
    @contextmanager
    def get_cursor(cls):
        """
        Context manager to get a connection and cursor from the pool.
        Handles connection lifecycle (get/put) and transaction commit/rollback
        for the single connection used within the 'with' block.
        """
        pool = cls.get_pool()
        conn = None  # Ensure conn is defined for the finally block
        cursor = None  # Ensure cursor is defined for the finally block
        try:
            conn = pool.getconn()  # Get a connection from the pool
            # Optional: Set transaction isolation level if needed, e.g.:
            # conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
            cursor = conn.cursor()
            yield cursor  # Make the cursor available in the 'with' block
            conn.commit()  # If the 'with' block completes without error, commit THIS connection
            logger.debug("DB transaction committed.")
        except psycopg2.pool.PoolError as pe:
            logger.error(f"Failed to get connection from pool: {pe}")
            # Handle pool errors specifically (e.g., pool exhausted)
            raise RuntimeError(f"Database pool error: {pe}") from pe
        except Exception as e:
            logger.error(f"DB operation failed: {e}", exc_info=True)  # Log exception info
            if conn:
                try:
                    conn.rollback()  # Rollback THIS connection on any error
                    logger.warning("DB transaction rolled back due to error.")
                except Exception as rb_e:
                    logger.error(f"Error during transaction rollback: {rb_e}", exc_info=True)
            raise  # Re-raise the original exception
        finally:
            # This block executes whether there was an error or not
            if cursor:
                try:
                    cursor.close()
                except Exception as c_e:
                    logger.error(f"Error closing cursor: {c_e}", exc_info=True)
            if conn:
                try:
                    # Return the connection to the pool VERY IMPORTANT
                    pool.putconn(conn)
                    logger.debug("DB connection returned to pool.")
                except Exception as p_e:
                    logger.error(f"Error returning connection to pool: {p_e}", exc_info=True)

    @classmethod
    def close_pool(cls):
        """Closes all connections in the pool. Call during application shutdown."""
        # Acquire lock to prevent getting pool while closing
        with cls._pool_lock:
            if cls._pool:
                logger.info("Closing DB connection pool...")
                try:
                    cls._pool.closeall()
                    logger.info("DB connection pool closed.")
                except Exception as e:
                    logger.error(f"Error closing DB connection pool: {e}", exc_info=True)
                finally:
                    cls._pool = None  # Ensure pool is marked as None even if closeall fails
