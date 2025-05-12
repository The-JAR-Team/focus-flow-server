import logging
import json
from db.DB import DB
import psycopg2.errors
import psycopg2.extras

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def get_summary(youtube_id: str, language: str):
    """
    Retrieves the summary JSON object from the "Summary" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the summary.

    Returns:
        dict or None: The summary JSON object (as a Python dict) if found and not NULL,
                      otherwise None. Returns None and logs an error if a
                      database or unexpected error occurs.
    """
    retrieved_summary = None
    logger.debug(f"Attempting to retrieve summary for youtube_id='{youtube_id}', language='{language}' from 'Summary' table.")
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                """
                SELECT summary
                FROM "Summary"
                WHERE youtube_id = %s AND lang = %s
                """,
                (youtube_id, language)
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                retrieved_summary = row[0]
                logger.info(f"Successfully retrieved summary for youtube_id='{youtube_id}', language='{language}'")
            elif row and row[0] is None:
                logger.info(f"Summary field is NULL in DB for youtube_id='{youtube_id}', language='{language}'")
            else:
                logger.info(f"No summary entry found for youtube_id='{youtube_id}', language='{language}'")
    except psycopg2.Error as e:
        logger.error(f"Database error retrieving summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
        retrieved_summary = None
    except Exception as e:
        logger.error(f"Unexpected error retrieving summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
        retrieved_summary = None

    return retrieved_summary


def upsert_summary(youtube_id: str, language: str, summary_json: dict):
    """
    Inserts a new summary entry or updates the existing one for the given
    youtube_id and language combination in the "Summary" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the summary.
        summary_json (dict): The Python dictionary to be stored as JSONB in the 'summary' column.

    Returns:
        dict: A dictionary containing:
            - "status" (str): "success" or "failed".
            - "message" (str): A descriptive message about the operation.
            - "operation" (str): "insert" or "update" indicating what the DB did (best guess based on rowcount).
                                 Note: ON CONFLICT doesn't directly return this, so it's inferred.
    """
    result = {
        "status": "failed",
        "message": "An unexpected error occurred.",
        "operation": "unknown"
    }
    logger.debug(f"Attempting to upsert summary for youtube_id='{youtube_id}', language='{language}'.")
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO "Summary" (youtube_id, lang, summary)
                VALUES (%s, %s, %s)
                ON CONFLICT (youtube_id, lang) DO UPDATE SET
                    summary = EXCLUDED.summary;
                """,
                (youtube_id, language, psycopg2.extras.Json(summary_json))
            )

            result["status"] = "success"
            result["message"] = "Summary inserted or updated successfully."

            result["operation"] = "upsert"
            logger.info(f"Successfully upserted summary for youtube_id='{youtube_id}', language='{language}'.")

    except psycopg2.Error as e:
        result["message"] = f"Database error during upsert: {e}"
        logger.error(f"Database error upserting summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    except Exception as e:
        result["message"] = f"An unexpected error during upsert: {e}"
        logger.error(f"Unexpected error upserting summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)

    return result

