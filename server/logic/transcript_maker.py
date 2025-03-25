import json
from youtube_transcript_api import YouTubeTranscriptApi


def make_transcript(video_id='5MuIMqhT8DM', lang='iw'):
    lang_type = [lang]
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript = transcript_list.find_transcript(lang_type)
    transcript = transcript.fetch()

    with open("./transcript.txt", "w", encoding="utf-8") as file:
        for line in transcript:
            start_time = line['start']
            duration = line['duration']
            text = line['text']
            file.write(f"Start: {start_time}s, Duration: {duration}s\n{text}\n\n")

    print("Transcript saved to transcript.txt")
