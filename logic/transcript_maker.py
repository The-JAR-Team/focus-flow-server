import json
import math
import os
import threading
import time
import traceback

from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from db.db_api import store_questions_in_db, questions_ready
from logic.gemini_api import generate

# Lock mechanism to prevent duplicate generations
generation_locks = {}  # key: "{youtube_id}_{lang}" -> Lock

# Track request patterns to identify duplicates
request_tracking = {}

def sanitize_text(text: str) -> str:
    """Clean transcript text to avoid JSON parsing issues"""
    # Replace problematic characters that can break JSON
    return (text.replace('\r', ' ')
                .replace('\n', ' ')
                .replace('"', '\\"')
                .replace('\t', ' ')
                .replace('\\', '\\\\'))


def seconds_to_hhmmss(seconds):
    """Convert a float (or int) number of seconds into 'HH:MM:SS' format."""
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

    while attempt < max_attempts:
        try:
            load_dotenv()
            ytt_api = YouTubeTranscriptApi(
                proxy_config=GenericProxyConfig(
                    http_url=os.getenv("PROXY_HTTP"),
                    https_url=os.getenv("PROXY_HTTPS"),
                )
            )

            transcript_list = ytt_api.list(video_id=video_id)
            transcript_obj = transcript_list.find_transcript(['en', 'iw', 'he'])
            lines = transcript_obj.fetch()
            # If successful, break out of the loop.
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            last_exception = e
            attempt += 1
            time.sleep(0.1)  # Wait 0.1 seconds before trying again.
    else:
        # If we've exhausted all attempts, raise the last encountered exception.
        raise last_exception

    transcript_str = ""
    for line in lines:
        start_time = seconds_to_hhmmss(line.start)
        duration = seconds_to_hhmmss(line.duration)
        text = line.text
        transcript_str += f"Start: {start_time}, Duration: {duration}\n{text}\n\n"
    return transcript_str


def split_transcript(transcript_text, chunk_duration=1800):
    """
    Splits the transcript into consecutive time-based chunks (0–chunk_duration,
    chunk_duration–2*chunk_duration, etc.), each chunk being up to chunk_duration seconds long.

    Each transcript block is assumed to begin with a line like:
       "Start: HH:MM:SS, Duration: HH:MM:SS"
    Then the text lines follow.

    Returns: list of strings, each chunk containing multiple blocks if
             those blocks' start times fit into the chunk boundary.
    """
    blocks = transcript_text.strip().split("\n\n")

    # Convert each block into (start_seconds, block_text), so we can sort and group them.
    block_info = []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split("\n")
        if not lines:
            continue
        try:
            # e.g. lines[0] = "Start: 00:01:48, Duration: 00:00:15"
            first_line = lines[0]
            start_part = first_line.split(",")[0]  # e.g. "Start: 00:01:48"
            time_str = start_part.split("Start:")[1].strip()
            h, m, s = map(int, time_str.split(":"))
            block_start_seconds = h * 3600 + m * 60 + s
        except:
            block_start_seconds = 0
        block_info.append((block_start_seconds, block))

    # Sort by start time, just in case they're not already in chronological order.
    block_info.sort(key=lambda x: x[0])

    chunks = []
    current_chunk_blocks = []
    # The boundary for the first chunk
    chunk_start = 0
    chunk_end = chunk_duration

    for start_sec, block_text in block_info:
        # If the current block belongs to a future chunk, flush the current chunk first.
        while start_sec >= chunk_end:
            if current_chunk_blocks:
                # finalize the current chunk
                chunks.append("\n\n".join(current_chunk_blocks))
                current_chunk_blocks = []
            # Advance the chunk boundaries
            chunk_start = chunk_end
            chunk_end += chunk_duration

        current_chunk_blocks.append(block_text)

    # Flush any leftover blocks into a final chunk
    if current_chunk_blocks:
        chunks.append("\n\n".join(current_chunk_blocks))

    return chunks


def generate_questions_from_transcript(youtube_id: str, lang="Hebrew", chunk_duration=1200):
    """
    Splits the transcript into multiple consecutive 30-minute (by default) chunks,
    processes them in parallel, and combines all resulting questions.

    Example return:
      {
        "questions": [
          { "q_id": "q1", "question_origin": "...", "question": "...", "answer1": "..." },
          ...
        ],
        "error": <error message if any, otherwise omitted>
      }
    """
    # Track caller to identify source of duplicate requests
    stack = traceback.extract_stack()
    caller_info = f"{stack[-2].name}:{stack[-2].lineno}" if len(stack) > 1 else "unknown"
    
    # Log request info
    request_key = f"{youtube_id}_{lang}"
    request_count = request_tracking.get(request_key, 0) + 1
    request_tracking[request_key] = request_count
    print(f"[DEBUG] Request #{request_count} for {request_key} from caller {caller_info}")
    
    try:
        transcript_text = fetch_transcript_as_string(youtube_id)
        chunks = split_transcript(transcript_text, chunk_duration)

        results = [None] * len(chunks)

        def worker(i, chunk_text):
            result_str = ""  # ensure defined for error logging
            try:
                # Sanitize text before sending to the model
                clean_chunk = sanitize_text(chunk_text)
                result_str = generate(text_file=clean_chunk, lang=lang)
                result_dict = json.loads(result_str)
                questions = result_dict.get("questions", [])
            except json.JSONDecodeError as e:
                # one retry
                try:
                    time.sleep(0.5)  # Increased delay on retry
                    clean_chunk = sanitize_text(chunk_text)
                    result_str = generate(text_file=clean_chunk, lang=lang)
                    result_dict = json.loads(result_str)
                    questions = result_dict.get("questions", [])
                except Exception as ex2:
                    print(f"Retry failed for chunk {i+1}: {ex2}")
                    questions = []
            except Exception as ex:
                print(f"Worker#{i} fatal error: {ex}")
                questions = []
            results[i] = questions

        # Start a thread for each chunk.
        threads = []
        for i, chunk_text in enumerate(chunks):
            t = threading.Thread(target=worker, args=(i, chunk_text))
            t.start()
            threads.append(t)

        # Wait for all threads to finish.
        for t in threads:
            t.join()

        # Combine questions from all chunks (without deduping).
        all_questions = []
        for q_list in results:
            if q_list:
                all_questions.extend(q_list)

        # Store the questions in the database.
        store_questions_in_db(youtube_id, lang, all_questions)

        # If we got nothing back, let the caller know.
        if not all_questions:
            return {"questions": [], "error": "No questions generated. See server logs for details."}

        print(f"Finished generation for {lang}. Found {len(all_questions)} questions total.")
        return {"questions": all_questions}
    except Exception as e:
        print(f"Error in generate_questions_from_transcript for {youtube_id} ({lang}): {e}")
        return {"questions": [], "error": str(e)}


def gen_if_empty(youtube_id: str, lang="Hebrew"):
    """
    Generate questions if none exist, using locks to prevent duplicate requests.
    """
    # Get a lock for this specific youtube_id and language combination
    key = f"{youtube_id}_{lang}"
    
    # Create a new lock if this is the first time we're seeing this combination
    if key not in generation_locks:
        generation_locks[key] = threading.Lock()
    
    lock = generation_locks[key]

    # Check if questions already exist - quick check before acquiring lock
    question_count = questions_ready(youtube_id, lang)
    if question_count > 0:
        return None
        
    if not lock.acquire(blocking=False):
        return {"questions": [], "error": "Generation already in progress"}
        
    try:
        # Double-check if questions exist now that we have the lock
        question_count_in_lock = questions_ready(youtube_id, lang)
        if question_count_in_lock == 0:
            generation_result = generate_questions_from_transcript(youtube_id, lang)
            if generation_result and "error" in generation_result and generation_result["error"]:
                return generation_result
            elif generation_result:
                return generation_result
            else:
                return {"questions": [], "error": "Internal generation error"}
        else:
            return None
    except Exception as e:
        print(f"Exception occurred during locked generation for {key}: {e}")
        return {"questions": [], "error": f"Generation failed: {e}"}
    finally:
        lock.release()

