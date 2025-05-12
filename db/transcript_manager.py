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
