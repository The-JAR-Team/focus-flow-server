import sqlparse
import psycopg2
from sqlparse.tokens import DML
from tabulate import tabulate
from flask import Blueprint, request, jsonify
from db.DB import DB
from server.main.utils import get_authenticated_user

debug_bp = Blueprint('debug_bp', __name__)


def is_select_query(parsed):
    """
    Checks if the parsed SQL query is a single SELECT statement.

    Parameters:
    - parsed (list): Parsed SQL statements.

    Returns:
    - bool: True if it's a single SELECT statement, False otherwise.
    """
    if len(parsed) != 1:
        return False  # Only single statements are allowed

    stmt = parsed[0]
    if not stmt.tokens:
        return False  # Empty query

    # Find the first meaningful token
    first_token = stmt.token_first(skip_cm=True)
    if not first_token:
        return False

    # Check if the first token is a DML statement and is SELECT
    if first_token.ttype is DML and first_token.value.upper() == 'SELECT':
        return True

    return False


def format_as_aligned_table(headers, rows, tablefmt='grid'):
    """
    Format results as a table-like string based on the specified format.
    Uses 'tabulate' under the hood.
    """
    return tabulate(rows, headers, tablefmt=tablefmt)


@debug_bp.route('/sql', methods=['POST'])
def execute_sql():
    """
    POST /sql

    JSON Payload:
    {
      "query": "SELECT * FROM some_table LIMIT 10"
    }

    Query parameters:
      ?type=html | string_table | data
      Defaults to 'html'.

    Only single SELECT statements are allowed, for safety reasons.
    """

    auth_resp, user_id, auth_status = get_authenticated_user(min_permission=2)
    if auth_resp is not None:
        return auth_resp, auth_status  # Return authentication error directly

    try:
        # Parse JSON payload from the request
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload."}), 400

        sql_query = data.get("query")
        if not sql_query:
            return jsonify({"error": "No SQL query provided."}), 400

        # Get the 'type' query parameter, defaulting to 'html'
        type_param = request.args.get('type', 'html').lower()
        if type_param not in ['html', 'string_table', 'data']:
            return jsonify({"error": "Invalid type parameter. Allowed values are 'html', 'string_table', 'data'."}), 400

        # Execute the query using your PostgreSQL DB class
        with DB.get_cursor() as cursor:
            cursor.execute(sql_query)
            rows = []
            headers = []
            try:
                # Fetch all results
                rows = cursor.fetchall()
                headers = [desc[0] for desc in cursor.description]  # Extract column names
            except psycopg2.ProgrammingError as e:
                if "no results to fetch" in str(e):
                    headers = ['Status']
                    rows = [['Execution successful, no results returned.']]
                    pass
                else:
                    raise

        # Format and return the results based on 'type' parameter
        if type_param == 'html':
            if rows:
                table_html = format_as_aligned_table(headers, rows, tablefmt="html")
                return table_html, 200
            else:
                return "No results found.", 200

        elif type_param == 'string_table':
            if rows:
                table_str = format_as_aligned_table(headers, rows, tablefmt="grid")
                return table_str, 200
            else:
                return "No results found.", 200

        elif type_param == 'data':
            if rows:
                # Convert rows to list of dictionaries
                data_list = [dict(zip(headers, row)) for row in rows]
                return jsonify({"data": data_list}), 200
            else:
                return jsonify({"message": "No results found."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
