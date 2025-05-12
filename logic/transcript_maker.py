import json
import math
import os
import threading
import time
import traceback
from typing import Dict, Any
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from db.db_api import store_questions_in_db, questions_ready, release_lock, acquire_lock, get_transcript, \
    insert_transcript
from db.lock_management import DistributedLock
from db.question_management import get_questions_for_video
from logic.gemini_api_request import question_requests


def generation_task_wrapper(video_id_inner, lang_inner, lock_key_inner):
    """
    Wrapper executes the generation task and ensures lock release.
    Intended to be the target for the background thread.
    """
    print(f"Background thread starting for {lock_key_inner} [PID: {os.getpid()}]")
    try:
        # Ensure any required setup for the thread is done here if needed
        # e.g., load_dotenv() if env vars aren't inherited reliably
        _generate_and_store_questions(video_id_inner, lang_inner)
        print(f"Background thread finished task successfully for {lock_key_inner}.")
    except Exception as task_e:
        print(f"Error during background thread task for {lock_key_inner}: {task_e}")
        traceback.print_exc()
    finally:
        # Ensure lock is released *by the thread* after its work is done or if it fails
        print(f"Background thread attempting to release lock for {lock_key_inner}.")
        if not release_lock(lock_key_inner):
             print(f"Warning: Background thread failed to release lock for {lock_key_inner}.")
        else:
            print(f"Background thread released lock for {lock_key_inner}.")
        print(f"Background thread exiting for {lock_key_inner}.")


def sanitize_text(text: str) -> str:
    """Clean transcript text to avoid JSON parsing issues."""
    # Basic sanitization
    return (text.replace('\r', ' ')
            .replace('\n', ' ')
            .replace('"', '\\"')
            .replace('\t', ' ')
            .replace('\\', '\\\\'))


def seconds_to_hhmmss(seconds):
    """Convert seconds to 'HH:MM:SS' format."""
    if seconds is None: return "00:00:00"
    total_seconds = int(math.floor(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def fetch_transcript_as_string(video_id: str) -> str:
    """
    Fetches the transcript from YouTube for the given `video_id` and returns
    a combined string with each line's timestamp and text.
    By default, tries Hebrew or English transcripts if available.
    Retries up to 15 times (with a 0.1 sec delay between attempts) before raising an exception.
    """
    max_attempts = 15
    attempt = 0
    last_exception = None
    lock_key = f"{video_id}_Generic"
    transcript_str = ""

    try:
        with DistributedLock(lock_key, blocking=True, timeout=600, retry_interval=5):
            transcript_str = get_transcript(video_id, "Generic")
            if transcript_str is None:
                transcript_str = ""

                load_dotenv()
                ytt_api = YouTubeTranscriptApi(
                    proxy_config=GenericProxyConfig(
                        http_url=os.getenv("PROXY_HTTP"),
                        https_url=os.getenv("PROXY_HTTPS"),
                    )
                )

                while attempt < max_attempts:
                    try:
                        transcript_list = ytt_api.list(video_id=video_id)
                        transcript_obj = transcript_list.find_transcript(['en', 'iw', 'he'])
                        lines = transcript_obj.fetch()
                        # If successful, break out of the loop.
                        break
                    except Exception as e:
                        print(f"Attempt {attempt + 1} failed: {e}")
                        last_exception = e
                        attempt += 1
                        time.sleep(0.1 * (2**attempt))  # Wait 0.1 seconds before trying again.
                else:
                    # If we've exhausted all attempts, raise the last encountered exception.
                    raise last_exception

                for line in lines:
                    start_time = seconds_to_hhmmss(line.start)
                    duration = seconds_to_hhmmss(line.duration)
                    text = line.text
                    transcript_str += f"Start: {start_time}, Duration: {duration}\n{text}\n\n"

                # Store the transcript in the database after checking its not empty
                if transcript_str != "":
                    store_result = insert_transcript(video_id, "Generic", transcript_str)
                    if store_result != 0:
                        print(f"Transcript stored successfully for {video_id}.")
                    else:
                        print(f"Failed to store transcript for {video_id}.")
    except DistributedLock.LockAcquisitionFailed:
        print(f"Failed to acquire lock for {lock_key}.")
        pass

    return transcript_str


def split_transcript(transcript_text, chunk_duration=1800):
    """
    Splits the transcript into consecutive time-based chunks.
    Parses blocks like: "Start: HH:MM:SS, Duration: HH:MM:SS\nText\n\n"
    """
    # Split into blocks based on the double newline separator
    blocks = transcript_text.strip().split("\n\n")
    if not blocks:
        return []

    block_info = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n', 1)  # Split into first line and the rest
        if not lines:
            continue

        first_line = lines[0]
        block_text_content = lines[1] if len(lines) > 1 else ""  # The actual text

        # Parse the start time from the first line
        try:
            if first_line.startswith("Start:"):
                # Extract "HH:MM:SS" part after "Start: " and before the first comma
                time_str = first_line.split("Start:")[1].split(",")[0].strip()
                h, m, s = map(int, time_str.split(':'))
                block_start_seconds = h * 3600 + m * 60 + s
                # Store the start time and the original full block text
                block_info.append((block_start_seconds, block))
            else:
                print(f"Warning: Skipping block without expected 'Start:' prefix: {first_line}")
        except (ValueError, IndexError) as e:
            print(f"Warning: Could not parse timestamp from block header '{first_line}': {e}")
            continue  # Skip blocks with unparsable headers

    if not block_info:  # Handle case where no blocks had valid headers
        print("Warning: No blocks with valid timestamps found for splitting.")
        return []

    # Sort blocks by their start time
    block_info.sort(key=lambda x: x[0])

    # Group blocks into time-based chunks
    chunks = []
    current_chunk_blocks_text = []
    # Initialize based on the first block's time
    chunk_start_time = block_info[0][0]
    chunk_end_time = chunk_start_time + chunk_duration

    for start_sec, full_block_text in block_info:
        # Finalize previous chunk if current block starts after its end time
        while start_sec >= chunk_end_time:
            if current_chunk_blocks_text:
                chunks.append("\n\n".join(current_chunk_blocks_text))  # Join blocks with original separator
            current_chunk_blocks_text = []  # Reset for next chunk
            # Advance chunk boundaries
            chunk_start_time = chunk_end_time
            chunk_end_time += chunk_duration

        # Add the full block text to the current chunk
        current_chunk_blocks_text.append(full_block_text)

    # Add the last chunk if it has content
    if current_chunk_blocks_text:
        chunks.append("\n\n".join(current_chunk_blocks_text))

    return chunks


# --- Private Generation Function ---
def _generate_and_store_questions(youtube_id: str, lang="Hebrew", chunk_duration=1200, max_retries=15):
    """
    Internal: Fetches, splits, generates questions via threads, stores in DB.
    Returns dict: {"questions": list, "error": str_or_none}
    """
    print(f"Starting generation process for {youtube_id} ({lang})...")
    all_questions = []
    return_message = None  # Used to ensure single return point

    try:
        transcript_text = fetch_transcript_as_string(youtube_id)
        if transcript_text == "":
            raise ValueError(f"Transcript for {youtube_id} is empty.")
        chunks = split_transcript(transcript_text, chunk_duration)
        if not chunks: raise ValueError("Transcript yielded no processable chunks.")

        print(f"Transcript split into {len(chunks)} chunks for {youtube_id} ({lang}).")
        results = [None] * len(chunks)

        def worker(index, chunk_text):
            """Processes a single chunk to generate questions with retries."""
            thread_questions = []
            last_error = None
            for attempt in range(max_retries):
                result_str = ""
                try:
                    clean_chunk = sanitize_text(chunk_text)
                    result_str = question_requests(text_file=clean_chunk, lang=lang)
                    result_dict = json.loads(result_str)
                    thread_questions = result_dict.get("questions", [])
                    if thread_questions is None or len(thread_questions) == 0:
                        if attempt < max_retries - 1:
                            sleep_time = 0.5 * (2 ** attempt)  # Exponential backoff
                            time.sleep(sleep_time)
                    else:
                        last_error = None
                        break  # Success
                except (json.JSONDecodeError, Exception) as e:
                    last_error = e
                    if isinstance(e, json.JSONDecodeError): print(f"   Raw result: '{result_str[:200]}...'")
                    if attempt < max_retries - 1:
                        sleep_time = 0.5 * (2 ** attempt)  # Exponential backoff
                        time.sleep(sleep_time)
                    else:
                        print(
                            f"Worker {index + 1} for {youtube_id} ({lang}) failed after {max_retries} attempts. Last error: {last_error}")
            results[index] = thread_questions  # Store result (empty list if all retries failed)

        threads = []
        for i, chunk_text in enumerate(chunks):
            t = threading.Thread(target=worker, args=(i, chunk_text), name=f"GenWorker-{youtube_id}-{lang}-{i + 1}")
            t.start()
            threads.append(t)
        for t in threads: t.join()  # Wait for all threads

        # Combine results
        for q_list in results:
            if isinstance(q_list, list): all_questions.extend(q_list)
        print(f"Total questions generated across all chunks for {youtube_id} ({lang}): {len(all_questions)}")

        # Store results and check success
        if all_questions:
            store_result = store_questions_in_db(youtube_id, lang, all_questions)
            if store_result != 0:  # Check for non-zero success (adjust if DB function returns bool)
                return_message = {"questions": all_questions}  # Success state
            else:
                db_error_msg = f"DB storage function returned failure code ({store_result}) for {youtube_id} ({lang})."
                print(db_error_msg)
                return_message = {"questions": all_questions,
                                  "error": db_error_msg}  # Partial success (generated but not stored)
        else:
            # No questions generated by AI or no chunks processed
            error_msg = "No questions were generated by the AI model." if len(
                chunks) > 0 else "No transcript chunks to process."
            return_message = {"questions": [], "error": error_msg}

    except Exception as e:
        # Catch errors during fetch/split or other main thread issues
        print(f"Error in _generate_and_store_questions for {youtube_id} ({lang}): {e}")
        traceback.print_exc()
        return_message = {"questions": [], "error": f"Generation process failed: {str(e)}"}

    # Final check and return
    if return_message is None:
        print(f"Warning: Reached end of _generate_and_store_questions for {youtube_id} ({lang}) unexpectedly.")
        return_message = {"questions": [], "error": "Unknown internal generation state."}
    return return_message


def get_or_generate_questions(youtube_id: str, lang: str = "Hebrew") -> Dict[str, Any]:
    """
    Gets existing questions or starts generation in a background thread if needed,
    handling distributed locking.

    Returns:
        Dict[str, Any]: {"questions": list, "status": str, "reason": str}
            status: "success" (existing questions found),
                    "failed" (error occurred),
                    "blocked" (generation in progress or starting now)
    """
    lock_key = f"{youtube_id}_{lang}"
    response_payload = {
        "questions": [],
        "status": "failed",  # Default to failed
        "reason": "An unexpected error occurred."
    }
    lock_acquired = False

    try:
        lock_acquired = acquire_lock(lock_key)
        if not lock_acquired:
            response_payload["status"] = "blocked"
            response_payload["reason"] = "Generation already in progress by another request."
        else:
            if questions_ready(youtube_id, lang) > 0:
                fetched_data = get_questions_for_video(youtube_id, lang)
                if (isinstance(fetched_data, dict) and
                        "video_questions" in fetched_data and
                        isinstance(fetched_data["video_questions"], dict) and
                        "questions" in fetched_data["video_questions"] and
                        isinstance(fetched_data["video_questions"]["questions"], list)):

                    response_payload["questions"] = fetched_data["video_questions"]["questions"]
                    response_payload["status"] = "success"
                    response_payload["reason"] = ""
                    print(
                        f"Successfully fetched {len(response_payload['questions'])} existing questions for {lock_key}.")
                else:
                    response_payload["status"] = "failed"
                    response_payload["reason"] = ("Failed to fetch or parse existing questions from DB (unexpected "
                                                  "format) despite holding lock.")
                    print(
                        f"Failed to fetch existing questions for {lock_key}. Fetch result format: {type(fetched_data)}")
                    if isinstance(fetched_data, dict):
                        print(f"Fetched data keys: {fetched_data.keys()}")
            else:
                print(f"No existing questions for {lock_key}. Starting background generation thread.")

                generation_thread = threading.Thread(
                    target=generation_task_wrapper,
                    args=(youtube_id, lang, lock_key),
                    name=f"DaemonGenThread-{lock_key}"
                )
                generation_thread.daemon = True
                generation_thread.start()

                response_payload["status"] = "blocked"
                response_payload["reason"] = "Started generation of questions"

                lock_acquired = False

    except Exception as e:
        print(f"Error in get_or_generate_questions for {lock_key}: {e}")
        traceback.print_exc()
        if response_payload["status"] not in ["success", "blocked"]:
            response_payload["status"] = "failed"
        if response_payload["reason"] == "An unexpected error occurred.":
            response_payload["reason"] = f"An unexpected error occurred: {str(e)}"

    finally:
        if lock_acquired:
            if not release_lock(lock_key):
                print(f"Warning: Main thread failed to release lock for {lock_key} in finally block.")
            else:
                print(
                    f"Main thread released lock for {lock_key} in finally block (likely due to fetching existing data "
                    f"or an error before generation).")

    return response_payload
