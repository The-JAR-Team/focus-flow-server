import json
import traceback
import threading
import logging
import os
from typing import Dict, Any

from db.db_api import get_summary, upsert_summary, acquire_lock, release_lock
from logic.generation.gemini_api.gemini_api_request import summery_request
from logic.generation.transcript_maker import fetch_transcript_as_string

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# --- Private Generation Function ---
def _generate_and_store_summary(youtube_id: str, lang: str):
    """
    Internal function: Fetches transcript, generates summary, parses, and stores in DB.
    Intended to be called by the background task wrapper.
    """
    logger.info(f"Starting summary generation process for {youtube_id} ({lang})...")
    summary_json = None
    error_message = None

    try:
        transcript = fetch_transcript_as_string(youtube_id)
        if not transcript or transcript == "":
            raise ValueError(f"Transcript for {youtube_id} is empty or could not be fetched.")

        summary_str = summery_request(transcript, lang)
        if not summary_str:
            raise ValueError(f"Summary request returned empty result for {youtube_id} ({lang}).")

        try:
            summary_json = json.loads(summary_str)
            if not isinstance(summary_json, dict) or 'response' not in summary_json:
                logger.warning(
                    f"Parsed summary JSON for {youtube_id} ({lang}) lacks expected structure: {summary_json}")
        except json.JSONDecodeError as json_e:
            logger.error(
                f"Failed to parse summary JSON for {youtube_id} ({lang}). Raw: '{summary_str[:200]}...'. Error: {json_e}")
            raise ValueError(f"Failed to parse summary JSON: {json_e}") from json_e

        if summary_json:
            update_result = upsert_summary(youtube_id=youtube_id, language=lang, summary_json=summary_json)
            if update_result.get("status") != "success":
                db_error_msg = f"DB update_summary failed for {youtube_id} ({lang}): {update_result.get('message')}"
                logger.error(db_error_msg)
                raise RuntimeError(db_error_msg)
            else:
                logger.info(f"Successfully stored summary in DB for {youtube_id} ({lang}).")
        else:
            raise ValueError(f"Summary JSON was empty after parsing for {youtube_id} ({lang}).")

    except Exception as e:
        error_message = f"Error in _generate_and_store_summary for {youtube_id} ({lang}): {e}"
        logger.error(error_message, exc_info=True)
    finally:
        if error_message:
            print(f"Generation failed: {error_message}")


# --- Background Task Wrapper ---
def summary_generation_task_wrapper(video_id_inner, lang_inner, lock_key_inner):
    """
    Wrapper executes the summary generation task and ensures lock release.
    Intended to be the target for the background thread.
    """
    logger.info(f"Background summary thread starting for {lock_key_inner} [PID: {os.getpid()}]")
    try:
        _generate_and_store_summary(video_id_inner, lang_inner)
        logger.info(f"Background summary thread finished task successfully for {lock_key_inner}.")
    except Exception as task_e:
        logger.error(f"Error during background summary task for {lock_key_inner}: {task_e}", exc_info=True)
    finally:
        logger.info(f"Background summary thread attempting to release lock for {lock_key_inner}.")
        if not release_lock(lock_key_inner):
            logger.warning(f"Background summary thread failed to release lock for {lock_key_inner}.")
        else:
            logger.info(f"Background summary thread released lock for {lock_key_inner}.")
        logger.info(f"Background summary thread exiting for {lock_key_inner}.")


# --- Main Function ---
def get_or_generate_summary(youtube_id: str, lang: str = "Hebrew") -> Dict[str, Any]:
    """
    Gets existing summary or starts generation in a background thread if needed,
    handling distributed locking manually.

    Returns:
        Dict[str, Any]: {"summary": dict | None, "status": str, "reason": str}
            summary: The summary dict if status is "success", otherwise None.
            status: "success" (existing summary found),
                    "failed" (error occurred before starting generation),
                    "blocked" (generation already in progress by another request OR generation started by this request).
    """
    lock_key = f"{youtube_id}_{lang}_Summary"
    response_payload = {
        "summary": None,
        "status": "failed",
        "reason": "An unexpected error occurred."
    }
    lock_acquired = False

    try:
        lock_acquired = acquire_lock(lock_key)

        if not lock_acquired:
            response_payload["status"] = "blocked"
            response_payload["reason"] = "Summary generation already in progress by another request."
            logger.warning(f"Lock acquisition failed for {lock_key}, generation likely in progress.")
        else:
            logger.info(f"Lock acquired successfully for {lock_key}.")

            existing_summary = get_summary(youtube_id, lang)

            if existing_summary is not None:
                response_payload["summary"] = existing_summary
                response_payload["status"] = "success"
                response_payload["reason"] = "Summary retrieved from database."
                logger.info(f"Found existing summary in DB for {lock_key}.")
                if not release_lock(lock_key):
                    logger.warning(f"Failed to release lock for {lock_key} after finding existing summary.")
                else:
                    logger.info(f"Released lock for {lock_key} after finding existing summary.")
                lock_acquired = False

            else:
                logger.info(f"No existing summary for {lock_key}. Starting background generation thread.")

                generation_thread = threading.Thread(
                    target=summary_generation_task_wrapper,
                    args=(youtube_id, lang, lock_key),
                    name=f"DaemonSummaryGenThread-{lock_key}"
                )
                generation_thread.daemon = True
                generation_thread.start()

                response_payload["status"] = "blocked"
                response_payload["reason"] = "Started summary generation in background."

                lock_acquired = False

    except Exception as e:
        logger.error(f"Error in get_or_generate_summary for {lock_key}: {e}", exc_info=True)
        if response_payload["status"] not in ["success", "blocked"]:
            response_payload["status"] = "failed"
        if response_payload["reason"] == "An unexpected error occurred.":
            response_payload["reason"] = f"An unexpected error occurred: {str(e)}"

    finally:
        if lock_acquired:
            logger.warning(f"Releasing lock for {lock_key} in finally block (unexpected state).")
            if not release_lock(lock_key):
                logger.error(f"CRITICAL: Failed to release lock for {lock_key} in finally block.")
            else:
                logger.info(f"Released lock for {lock_key} in finally block.")

    return response_payload
