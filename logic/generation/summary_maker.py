import json
import traceback
from typing import Dict

from db.db_api import get_summary, update_summary
from db.lock_management import DistributedLock
from logic.generation.gemini_api.gemini_api_request import summery_request
from logic.generation.transcript_maker import fetch_transcript_as_string


def get_or_generate_summary(youtube_id: str, lang: str = "Hebrew") -> Dict[str, Any]:
    """
    Gets existing summary or starts generation in a background thread if needed,
    handling distributed locking.

    Returns:
        Dict[str, Any]: {"summary": str, "status": str, "reason": str}
            status: "success" (existing summary found),
                    "failed" (error occurred),
                    "blocked" (generation in progress or starting now)
    """
    lock_key = f"{youtube_id}_{lang}_Summery"
    response_payload = {
        "summary": "",
        "status": "failed",  # Default to failed
        "reason": "An unexpected error occurred."
    }

    try:
        with DistributedLock(lock_key=lock_key, blocking=False):
            summery = get_summary(youtube_id, lang)

            if summery is None:
                transcript = fetch_transcript_as_string(youtube_id)
                summery_str = summery_request(transcript, lang)
                summery = json.loads(summery_str)
                ret_check = update_summary(youtube_id=youtube_id, language=lang, summary_json=summery)
                if ret_check["status"] != "success":
                    print(f"Failed to update summary in DB for {lock_key}: {ret_check['message']}")
                    raise ValueError("Failed to update summary in DB.")

            response_payload["summary"] = summery
            response_payload["status"] = "success"
            response_payload["reason"] = ""

    except DistributedLock.LockAcquisitionFailed:
        response_payload["status"] = "blocked"
        response_payload["reason"] = "Generation already in progress by another request."
    except Exception as e:
        print(f"Error in get_or_generate_summery for {lock_key}: {e}")
        traceback.print_exc()
        if response_payload["status"] not in ["success", "blocked"]:
            response_payload["status"] = "failed"
        if response_payload["reason"] == "An unexpected error occurred.":
            response_payload["reason"] = f"An unexpected error occurred: {str(e)}"

    return response_payload
