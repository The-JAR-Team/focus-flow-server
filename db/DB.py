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
        # Check if connection exists and is open (closed==0 means open)
        if cls._connection and cls._connection.closed == 0:
            return cls._connection
        else:
            # Load environment variables on first use
            if not cls._instance:
                load_dotenv()
                cls._instance = cls()
            cls._connection = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                dbname=os.getenv("DB_NAME"),
                port=os.getenv("DB_PORT", 5432)  # Default PostgreSQL port is 5432
            )
            return cls._connection

    @classmethod
    def close_connection(cls):
        """Closes the PostgreSQL database connection if it is open."""
        if cls._connection and cls._connection.closed == 0:
            cls._connection.close()
            cls._connection = None


def print_all_tables(schema_name):
    # Get the connection using the DB class
    conn = DB.get_connection()
    cur = conn.cursor()

    # Query to fetch all table names in the specified schema
    query = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = %s;
    """
    cur.execute(query, (schema_name,))
    tables = cur.fetchall()

    print(f"Tables in schema '{schema_name}':")
    for table in tables:
        print(table[0])

    cur.close()


if __name__ == "__main__":
    # Replace "MyDatabase" with your target schema name if needed.
    print_all_tables("MyDatabase")
    DB.close_connection()

