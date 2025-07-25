import math
import os
import time
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, CouldNotRetrieveTranscript, \
    TranscriptsDisabled
from youtube_transcript_api.proxies import GenericProxyConfig
from db.db_api import get_transcript, insert_transcript
from db.lock_management import DistributedLock


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

    Priority order for languages: Hebrew (he/iw), English (en), any available language
    Only retries for network/proxy errors, not for missing transcript errors.
    """
    max_attempts = 5
    attempt = 0
    last_exception = None
    lock_key = f"{video_id}_Generic_Transcript"
    transcript_str = ""

    try:
        with DistributedLock(lock_key, blocking=True, timeout=60, retry_interval=10):
            # Try to get from database first
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

                # First, try to get available transcripts
                while attempt < max_attempts:
                    try:
                        transcript_list = ytt_api.list(video_id=video_id)

                        try:
                            transcript_obj = transcript_list.find_transcript(['en', 'he', 'iw'])
                            lines = transcript_obj.fetch()
                            print(f"Found transcript for {video_id}")
                        except (NoTranscriptFound, CouldNotRetrieveTranscript):
                            try:
                                available_languages = [t.language for t in transcript_list]

                                if available_languages:
                                    first_lang = available_languages[0]
                                    transcript_obj = transcript_list.find_transcript([first_lang])
                                    lines = transcript_obj.fetch()
                                    print(f"Found transcript in {first_lang} for {video_id}")
                                else:
                                    print(f"No transcripts available for {video_id}")
                                    return ""
                            except Exception as e:
                                print(f"Error fetching any transcript for {video_id}: {e}")
                                return ""
                        break

                    except (TranscriptsDisabled, NoTranscriptFound) as e:
                        print(f"No transcripts available for {video_id}: {e}")
                        return ""
                    except Exception as e:
                        print(f"Attempt {attempt + 1} failed with network/proxy error: {e}")
                        last_exception = e
                        attempt += 1
                        if attempt >= max_attempts:
                            raise last_exception
                        time.sleep(0.01 * (0.2 * attempt))

                for line in lines:
                    start_time = seconds_to_hhmmss(line.start)
                    duration = seconds_to_hhmmss(line.duration)
                    text = line.text
                    transcript_str += f"Start: {start_time}, Duration: {duration}\n{text}\n\n"

                if transcript_str:
                    store_result = insert_transcript(video_id, "Generic", transcript_str)
                    if store_result != 0:
                        print(f"Transcript stored successfully for {video_id}.")
                    else:
                        print(f"Failed to store transcript for {video_id}.")

    except DistributedLock.LockAcquisitionFailed:
        print(f"Failed to acquire lock for {lock_key}.")
    except Exception as e:
        print(f"Error fetching transcript for {video_id}: {e}")
        if last_exception:
            print(f"Last exception encountered: {last_exception}")
        raise

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
