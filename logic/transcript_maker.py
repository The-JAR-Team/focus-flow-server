import json
import math
import os
import threading
import time

from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from db.db_api import store_questions_in_db, questions_ready
from logic.gemini_api import generate


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
    try:
        print(f"Generating {lang} questions for {youtube_id} with chunk size {chunk_duration} seconds...")
        transcript_text = fetch_transcript_as_string(youtube_id)
        chunks = split_transcript(transcript_text, chunk_duration)

        results = [None] * len(chunks)

        def worker(i, chunk_text):
            try:
                # Call the generative API for this chunk.
                result_str = generate(text_file=chunk_text, lang=lang)
                result_dict = json.loads(result_str)
                questions = result_dict.get("questions", [])
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON for chunk {i+1}: {e}")
                questions = []
            except Exception as ex:
                print(f"Error in worker for chunk {i+1}: {ex}")
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

        print(f"Finished generation for {lang}. Found {len(all_questions)} questions total.")
        return {"questions": all_questions}
    except Exception as e:
        print(f"Error in generate_questions_from_transcript: {e}")
        # Instead of raising an error, return an error message with an empty list.
        return {"questions": [], "error": str(e)}


def gen_if_empty(youtube_id: str, lang="Hebrew"):
    # Suppose questions_ready() returns how many questions exist for that video & language
    if questions_ready(youtube_id, lang) == 0:
        return generate_questions_from_transcript(youtube_id, lang)

