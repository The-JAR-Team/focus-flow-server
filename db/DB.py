from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg2
import os


class DB:
    _instance = None  # Singleton instance
    _connection = None  # Holds the database connection

    @classmethod
    def get_connection(cls):
        """
        Returns a PostgreSQL database connection.
        Loads environment variables and creates the connection if needed.
        """
        if cls._connection and cls._connection.closed == 0:
            return cls._connection
        else:
            if not cls._instance:
                load_dotenv()
                cls._instance = cls()
            cls._connection = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                dbname=os.getenv("DB_NAME"),
                port=os.getenv("DB_PORT", 5432)
            )
            return cls._connection

    @classmethod
    @contextmanager
    def get_cursor(cls):
        """
        Context manager for getting a database cursor.
        Commits the transaction if no exception is raised, otherwise rolls back.
        """
        conn = cls.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    @classmethod
    def close_connection(cls):
        """Closes the PostgreSQL database connection if it is open."""
        if cls._connection and cls._connection.closed == 0:
            cls._connection.close()
            cls._connection = None
