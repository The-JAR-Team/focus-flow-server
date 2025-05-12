import logging
from db.DB import DB
import psycopg2.errors

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def insert_transcript(youtube_id: str, language: str, transcript_text: str):
    """
    Inserts a new transcript into the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language of the transcript (e.g., 'en', 'es').
        transcript_text (str): The actual transcript content.

    Returns:
        dict: A dictionary containing:
            - "status" (str): "success" or "failed".
            - "message" (str): A descriptive message about the operation.
            - "transcript_id" (tuple or None): A tuple (youtube_id, language) if successful, else None.
    """
    result = {
        "status": "failed",
        "message": "An unexpected error occurred.",
        "transcript_id": None
    }
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO "Transcript" (youtube_id, language, transcript)
                VALUES (%s, %s, %s)
                """,
                (youtube_id, language, transcript_text)
            )
        result["status"] = "success"
        result["message"] = "Transcript inserted successfully."
        result["transcript_id"] = (youtube_id, language)
        logger.info(f"Successfully inserted transcript for youtube_id='{youtube_id}', language='{language}'")

    except psycopg2.errors.UniqueViolation:
        result["message"] = "Transcript already exists for this YouTube ID and language."
        logger.warning(f"Transcript for youtube_id='{youtube_id}', language='{language}' already exists.")
    except psycopg2.Error as e:
        result["message"] = f"Database error: {e}"
        logger.error(f"Database error inserting transcript for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    except Exception as e:
        result["message"] = f"An unexpected error: {e}"
        logger.error(f"Unexpected error inserting transcript for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)

    return result


def get_transcript(youtube_id: str, language: str):
    """
    Retrieves a transcript from the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language of the transcript.

    Returns:
        str or None: The transcript text if found, otherwise None.
                     Returns None and logs an error if a database or unexpected error occurs.
    """
    retrieved_transcript = None
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                """
                SELECT transcript
                FROM "Transcript"
                WHERE youtube_id = %s AND language = %s
                """,
                (youtube_id, language)
            )
            row = cur.fetchone()
            if row:
                retrieved_transcript = row[0]
                logger.info(f"Successfully retrieved transcript for youtube_id='{youtube_id}', language='{language}'")
            else:
                logger.info(f"No transcript found for youtube_id='{youtube_id}', language='{language}'")

    except psycopg2.Error as e:
        logger.error(f"Database error retrieving transcript for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error retrieving transcript for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)

    return retrieved_transcript


def get_summary(youtube_id: str, language: str):
    """
    Retrieves the summary JSON object from the "Transcript" table.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the transcript/summary.

    Returns:
        dict or None: The summary JSON object (as a Python dict) if found,
                      otherwise None. Returns None and logs an error if a
                      database or unexpected error occurs.
    """
    retrieved_summary = None
    try:
        with DB.get_cursor() as cur:
            cur.execute(
                """
                SELECT summery
                FROM "Transcript"
                WHERE youtube_id = %s AND language = %s
                """,
                (youtube_id, language)
            )
            row = cur.fetchone()
            # Check if row exists and the summery column is not None
            if row and row[0] is not None:
                retrieved_summary = row[0] # psycopg2 automatically decodes JSONB to Python dict
                logger.info(f"Successfully retrieved summary for youtube_id='{youtube_id}', language='{language}'")
            elif row and row[0] is None:
                logger.info(f"Summary field is NULL for youtube_id='{youtube_id}', language='{language}'")
            else:
                logger.info(f"No transcript/summary entry found for youtube_id='{youtube_id}', language='{language}'")
    except psycopg2.Error as e:
        logger.error(f"Database error retrieving summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error retrieving summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    return retrieved_summary


def update_summary(youtube_id: str, language: str, summary_json: dict):
    """
    Updates the summary JSON object for a specific transcript entry.

    Args:
        youtube_id (str): The YouTube video ID.
        language (str): The language associated with the transcript/summary.
        summary_json (dict): The Python dictionary to be stored as JSONB in the 'summery' column.

    Returns:
        dict: A dictionary containing:
            - "status" (str): "success" or "failed".
            - "message" (str): A descriptive message about the operation.
            - "rows_affected" (int): The number of rows updated (should be 0 or 1).
    """
    result = {
        "status": "failed",
        "message": "An unexpected error occurred.",
        "rows_affected": 0
    }
    try:
        with DB.get_cursor() as cur:
            # Use psycopg2.extras.Json to handle JSONB adaptation properly
            cur.execute(
                """
                UPDATE "Transcript"
                SET summery = %s
                WHERE youtube_id = %s AND language = %s
                """,
                (psycopg2.extras.Json(summary_json), youtube_id, language)
            )
            rows_updated = cur.rowcount
            result["rows_affected"] = rows_updated
            if rows_updated == 1:
                result["status"] = "success"
                result["message"] = "Summary updated successfully."
                logger.info(f"Successfully updated summary for youtube_id='{youtube_id}', language='{language}'")
            elif rows_updated == 0:
                result["status"] = "failed" # Or potentially "not_found" depending on desired semantics
                result["message"] = "No matching transcript entry found to update."
                logger.warning(f"No transcript entry found for youtube_id='{youtube_id}', language='{language}' during summary update.")
            else:
                 # Should not happen with the primary key constraint, but good to log
                result["message"] = f"Unexpected number of rows updated: {rows_updated}"
                logger.error(f"Unexpected number of rows ({rows_updated}) updated for youtube_id='{youtube_id}', language='{language}'.")

    except psycopg2.Error as e:
        result["message"] = f"Database error: {e}"
        logger.error(f"Database error updating summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    except Exception as e:
        result["message"] = f"An unexpected error: {e}"
        logger.error(f"Unexpected error updating summary for youtube_id='{youtube_id}', language='{language}': {e}", exc_info=True)
    return result