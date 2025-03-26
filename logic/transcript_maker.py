import json
import math
import threading

from youtube_transcript_api import YouTubeTranscriptApi

from db.db_api import store_questions_in_db, questions_ready
from logic.gemini_api import generate

video_id_hard_coded = 'OJu7kIFXzxg'  # Hebrew


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
    By default, tries Hebrew transcript if 'language_codes' is not provided.
    """

    # 1. Fetch transcript
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript_obj = transcript_list.find_transcript(['en', 'iw', 'he'])

    lines = transcript_obj.fetch()

    # 2. Build one big string:
    #    (Alternatively, you could build a list of lines and then "\n".join them.)
    transcript_str = ""
    for line in lines:
        start_time = seconds_to_hhmmss(line['start'])
        duration = seconds_to_hhmmss(line['duration'])
        text = line['text']
        # Format the output:
        transcript_str += f"Start: {start_time}, Duration: {duration}\n{text}\n\n"

    return transcript_str


def fetch_transcript_as_string(video_id: str) -> str:
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript_obj = transcript_list.find_transcript(['en', 'iw', 'he'])
    lines = transcript_obj.fetch()
    transcript_str = ""
    for line in lines:
        start_time = seconds_to_hhmmss(line['start'])
        duration = seconds_to_hhmmss(line['duration'])
        text = line['text']
        transcript_str += f"Start: {start_time}, Duration: {duration}\n{text}\n\n"
    return transcript_str


def split_transcript(transcript_text, chunk_duration=1800):
    """
    Splits the transcript text into chunks, where each chunk covers up to chunk_duration seconds.
    """
    blocks = transcript_text.strip().split("\n\n")
    chunks = []
    current_chunk = []
    start_time_first = None
    for block in blocks:
        if not block.strip():
            continue
        try:
            first_line = block.split("\n")[0]
            # Expected format: "Start: HH:MM:SS, Duration: ..."
            parts = first_line.split(",")
            start_part = parts[0]  # "Start: HH:MM:SS"
            time_str = start_part.split("Start:")[1].strip()
            h, m, s = map(int, time_str.split(":"))
            block_start_seconds = h * 3600 + m * 60 + s
        except Exception:
            block_start_seconds = 0
        if start_time_first is None:
            start_time_first = block_start_seconds
        if block_start_seconds - start_time_first < chunk_duration:
            current_chunk.append(block)
        else:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            start_time_first = block_start_seconds
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks


def generate_questions_from_transcript(youtube_id: str, lang="Hebrew", chunk_duration=1800):
    """
    Splits the transcript into chunks (default 30 minutes per chunk) and processes
    each chunk concurrently. The questions generated from all chunks are combined,
    stored in the database, and returned as a dict in the form:

    {
      "questions": [ { "q_id": ..., "question_origin": ..., "question": ..., "answer1": ..., ... }, ... ]
    }
    """
    print("Generating questions...")
    transcript_text = fetch_transcript_as_string(youtube_id)
    chunks = split_transcript(transcript_text, chunk_duration)

    # Create a list to store results from each thread, indexed by chunk index.
    results = [None] * len(chunks)

    def worker(i, chunk):
        result_str = generate(text_file=chunk, lang=lang)
        try:
            result_dict = json.loads(result_str)
            questions = result_dict.get("questions", [])
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for chunk {i + 1}: {e}")
            questions = []
        results[i] = questions

    threads = []
    for i, chunk in enumerate(chunks):
        t = threading.Thread(target=worker, args=(i, chunk))
        t.start()
        threads.append(t)
    # Wait for all threads to finish.
    for t in threads:
        t.join()

    # Combine all questions, ensuring no duplicates.
    all_questions = []
    seen_qids = set()
    for q_list in results:
        for q in q_list:
            q_id = q.get("q_id")
            if q_id not in seen_qids:
                seen_qids.add(q_id)
                all_questions.append(q)

    # Store the combined questions in the database.
    store_questions_in_db(youtube_id, lang, all_questions)

    print("Finished generation for:", lang)
    return {"questions": all_questions}


def gen_if_empty(youtube_id: str, lang="Hebrew"):
    if questions_ready(youtube_id, lang) == 0:
        return generate_questions_from_transcript(youtube_id, lang)


if __name__ == "__main__":
    generate_questions_from_transcript(youtube_id=video_id_hard_coded)
