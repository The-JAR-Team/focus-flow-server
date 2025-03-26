import math
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


def generate_questions_from_transcript(youtube_id: str, lang="Hebrew"):
    # 1. Get the transcript as a single string
    transcript_text = fetch_transcript_as_string(youtube_id)

    # 2. Now call your “generate” function from your genai snippet
    #    Replace "generate" with the actual function name you use,
    #    and pass 'transcript_text' as the argument for text_file or similar.
    #    For example, if your function is named "generate" and it expects a "text_file" param:
    result = generate(text_file=transcript_text, lang=lang)

    # # 3. Then do something with 'result'
    store_questions_in_db(youtube_id, lang, result)
    return result


def gen_if_empty(youtube_id: str, lang="Hebrew"):
    if questions_ready(youtube_id, lang) == 0:
        return generate_questions_from_transcript(youtube_id, lang)


if __name__ == "__main__":
    generate_questions_from_transcript(youtube_id=video_id_hard_coded)
