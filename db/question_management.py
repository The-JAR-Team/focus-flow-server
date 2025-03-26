import datetime
from db.DB import DB


def parse_hhmmss_to_time(hhmmss_str):
    """
    Converts a string in 'HH:MM:SS' format to a Python time object.
    E.g. '00:01:48' -> datetime.time(0, 1, 48)
    """
    if not hhmmss_str:
        return None  # If empty or missing
    return datetime.datetime.strptime(hhmmss_str, "%H:%M:%S").time()


def store_questions_in_db(youtube_id, language, questions):
    """
    Stores a batch of generated questions into the Question_Group and Question tables.

    Args:
      youtube_id (str): The ID of the YouTube video, stored in Question_Group.
      language (str): e.g. "Hebrew" or "en".
      questions (list): A list of dictionaries, each with fields:
        {
          "q_id": <str>,             # e.g. "q1"
          "question_origin": <str>,  # e.g. "00:01:48"
          "question": <str>,
          "answer1": <str>,
          "answer2": <str>,
          "answer3": <str>,
          "answer4": <str>
        }

    Returns:
      int: The newly created question_group_id, or 0 on failure.
    """
    try:
        with DB.get_cursor() as cur:
            # 1) Insert a row into Question_Group (one per youtube_id + language combo).
            cur.execute(
                '''INSERT INTO "Question_Group" (youtube_id, language)
                   VALUES (%s, %s)
                   RETURNING question_group_id
                ''',
                (youtube_id, language)
            )
            group_id = cur.fetchone()[0]

            # 2) Insert each question into Question, linked to group_id.
            for q in questions:
                q_id = q.get("q_id")
                question_origin_str = q.get("question_origin", "")  # e.g. "00:01:48"
                question_txt = q.get("question")
                answer1 = q.get("answer1")
                answer2 = q.get("answer2")
                answer3 = q.get("answer3")
                answer4 = q.get("answer4")

                # Convert "HH:MM:SS" -> time object
                question_origin_time = parse_hhmmss_to_time(question_origin_str)

                cur.execute(
                    '''INSERT INTO "Question"
                       (question_group_id, q_id, question_origin, question,
                        answer1, answer2, answer3, answer4)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        group_id,
                        q_id,
                        question_origin_time,
                        question_txt,
                        answer1,
                        answer2,
                        answer3,
                        answer4
                    )
                )
            return group_id
    except Exception as e:
        print("Error storing questions:", e)
        return 0


def time_to_hhmmss(time_obj):
    """
    Converts a Python time object (HH:MM:SS) to a 'HH:MM:SS' string.
    If None, returns an empty string or default.
    """
    if not time_obj:
        return ""
    return time_obj.strftime("%H:%M:%S")


def get_questions_for_video(youtube_id, language):
    """
    Retrieves questions from Question_Group and Question for the given youtube_id + language.

    Returns JSON in the format:
    {
      "id": <youtube_id>,
      "video_questions": {
        "questions": [
          {
            "q_id": <str>,
            "time_start_I_can_ask_about_it": "HH:MM:SS",
            "question": <str>,
            "answer1": <str>,
            "answer2": <str>,
            "answer3": <str>,
            "answer4": <str>
          },
          ...
        ]
      },
      "subject_questions": { "questions": [] },
      "generic_questions": { "questions": [] }
    }
    """
    try:
        with DB.get_cursor() as cur:
            # 1) Find the question_group row
            cur.execute(
                '''SELECT question_group_id
                   FROM "Question_Group"
                   WHERE youtube_id = %s AND language = %s
                   LIMIT 1''',
                (youtube_id, language)
            )
            row = cur.fetchone()
            if row is None:
                # No questions found for this video+lang
                return {
                    "id": youtube_id,
                    "video_questions": {"questions": []},
                    "subject_questions": {"questions": []},
                    "generic_questions": {"questions": []}
                }

            question_group_id = row[0]

            # 2) Fetch all related questions
            cur.execute(
                '''SELECT q_id,
                          question_origin,
                          question,
                          answer1,
                          answer2,
                          answer3,
                          answer4
                   FROM "Question"
                   WHERE question_group_id = %s
                   ORDER BY question_id''',
                (question_group_id,)
            )
            rows = cur.fetchall()

            # 3) Build the "questions" list
            questions_list = []
            for r in rows:
                q_id = r[0]
                question_origin_time = r[1]  # time object
                question_txt = r[2]
                a1 = r[3]
                a2 = r[4]
                a3 = r[5]
                a4 = r[6]

                # Convert time object to "HH:MM:SS"
                origin_str = time_to_hhmmss(question_origin_time)

                questions_list.append({
                    "q_id": q_id,
                    "time_start_I_can_ask_about_it": origin_str,
                    "question": question_txt,
                    "answer1": a1,
                    "answer2": a2,
                    "answer3": a3,
                    "answer4": a4
                })

            # 4) Return final JSON structure
            return {
                "id": youtube_id,
                "video_questions": {
                    "questions": questions_list
                },
                # Placeholders for optional future expansions
                "subject_questions": {"questions": []},
                "generic_questions": {"questions": []}
            }
    except Exception as e:
        print("Error retrieving questions for video:", e)
        # Return an empty set or an error structure
        return {
            "id": youtube_id,
            "video_questions": {"questions": []},
            "subject_questions": {"questions": []},
            "generic_questions": {"questions": []}
        }


def questions_ready(youtube_id, language="Hebrew"):
    """
    Checks if questions for the given YouTube video and language are ready.

    The method:
      1. Looks for a Question_Group row matching the youtube_id and language.
      2. If found, counts the number of Question rows linked to that group.

    Args:
      youtube_id (str): The YouTube video ID.
      language (str): The language code (default is "Hebrew").

    Returns:
      bool: True if questions exist, False otherwise.
    """
    try:
        with DB.get_cursor() as cur:
            # Find the matching Question_Group row.
            cur.execute(
                'SELECT question_group_id FROM "Question_Group" WHERE youtube_id = %s AND language = %s LIMIT 1',
                (youtube_id, language)
            )
            row = cur.fetchone()
            if row is None:
                return False

            question_group_id = row[0]

            # Count questions in the Question table for this group.
            cur.execute(
                'SELECT COUNT(*) FROM "Question" WHERE question_group_id = %s',
                (question_group_id,)
            )
            count = cur.fetchone()[0]
            return count
    except Exception as e:
        print("Error checking questions_ready:", e)
        return False
