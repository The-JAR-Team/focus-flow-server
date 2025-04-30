import datetime
from db.DB import DB


def parse_hhmmss_to_time(time_str):
    """
    Parses an "HH:MM:SS" string into a datetime.time object.
    Returns None if input is None, empty, or invalid format.
    """
    if not time_str:
        return None
    try:
        # Use strptime to parse the time string
        parsed_time = datetime.datetime.strptime(time_str, '%H:%M:%S').time()
        return parsed_time
    except ValueError:
        print(f"Warning: Could not parse time string '{time_str}'. Skipping time field.")
        return None


def store_questions_in_db(youtube_id, language, questions):
    """
    Stores a batch of generated questions. Reuses existing Question_Group if found,
    otherwise creates a new one. Optionally clears old questions first.

    Args:
      youtube_id (str): The ID of the YouTube video, stored in Question_Group.
      language (str): e.g. "Hebrew" or "en".
      questions (list): A list of dictionaries with question data.
      clear_existing (bool): If True, deletes existing questions for this group
                               before inserting new ones. Defaults to False.

    Returns:
      int: The relevant question_group_id, or 0 on failure.
    """
    group_id = 0 # Initialize group_id
    clear_existing = False # Set to True if you want to replace old questions

    try:
        with DB.get_cursor() as cur:
            # 1) UPSERT: Try to insert the group. If youtube_id + language combo
            # already exists (violates unique constraint), do nothing.
            # This relies on the unique_youtube_language constraint existing.
            cur.execute(
                '''INSERT INTO "Question_Group" (youtube_id, language)
                   VALUES (%s, %s)
                   ON CONFLICT (youtube_id, language) DO NOTHING
                ''',
                (youtube_id, language)
            )

            # 2) SELECT the group_id. It will exist either because it was just
            # inserted or because it was already there (ON CONFLICT).
            cur.execute(
                '''SELECT question_group_id
                   FROM "Question_Group"
                   WHERE youtube_id = %s AND language = %s
                ''',
                (youtube_id, language)
            )
            result = cur.fetchone()
            if result is None:
                # This should generally not happen if the UPSERT logic works and
                # the unique constraint exists. Could indicate a deeper issue.
                raise Exception(f"Failed to find or create Question_Group for youtube_id={youtube_id}, language={language}")
            group_id = result[0]

            # 3) OPTIONAL: Clear existing questions for this group if desired.
            if clear_existing:
                print(f"Clearing existing questions for group_id: {group_id}")
                cur.execute('DELETE FROM "Question" WHERE question_group_id = %s', (group_id,))

            # 4) Insert each new question into Question, linked to the group_id.
            for q in questions:
                # --- Extract fields ---
                q_id = q.get("q_id")
                question_origin_str = q.get("question_origin")
                question_explanation_end_str = q.get("question_explanation_end")
                difficulty = q.get("difficulty")
                keywords = q.get("keywords")
                question_txt = q.get("question")
                answer1 = q.get("answer1")
                answer2 = q.get("answer2")
                answer3 = q.get("answer3")
                answer4 = q.get("answer4")
                explanation_snippet = q.get("explanation_snippet")

                # --- Data Type Preparations ---
                question_origin_time = parse_hhmmss_to_time(question_origin_str)
                question_explanation_end_time = parse_hhmmss_to_time(question_explanation_end_str)
                db_keywords = keywords if isinstance(keywords, list) else None
                db_difficulty = int(difficulty) if difficulty is not None else None

                # --- Execute INSERT ---
                cur.execute(
                    '''INSERT INTO "Question" (
                           question_group_id, q_id, question_origin, question_explanation_end,
                           difficulty, keywords, question, answer1, answer2, answer3, answer4,
                           explanation_snippet
                       )
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        group_id, q_id, question_origin_time, question_explanation_end_time,
                        db_difficulty, db_keywords, question_txt, answer1, answer2, answer3,
                        answer4, explanation_snippet
                    )
                )

            # Commit happens automatically when 'with' block exits without error
            return group_id

    except Exception as e:
        # Rollback happens automatically due to exception + context manager
        print(f"Error storing questions for youtube_id {youtube_id} (group_id {group_id}): {e}")
        return 0



def time_to_hhmmss(time_obj):
    """
    Converts a Python time object (HH:MM:SS) to a 'HH:MM:SS' string.
    If None, returns an empty string or default.
    """
    if not time_obj:
        # Consider returning None instead of "" if that's better for your JSON consumer
        return None
        # return ""
    # Ensure time_obj is actually a datetime.time object
    if isinstance(time_obj, datetime.time):
        return time_obj.strftime("%H:%M:%S")
    else:
        # Handle cases where DB might return something else unexpectedly
        print(f"Warning: Expected datetime.time object, got {type(time_obj)}. Returning None.")
        return None


def get_questions_for_video(youtube_id, language):
    """
    Retrieves questions from Question_Group and Question for the given youtube_id + language.

    Returns JSON structure including all generated fields:
    {
      "id": <youtube_id>,
      "video_questions": {
        "questions": [
          {
            "q_id": <str>,
            "question_origin": "HH:MM:SS",          # Start time
            "question_explanation_end": "HH:MM:SS", # End time
            "difficulty": <int | None>,            # 1-10 or null
            "keywords": <list[str] | None>,        # List of keywords or null
            "question": <str>,
            "answer1": <str>,
            "answer2": <str>,
            "answer3": <str>,
            "answer4": <str>,
            "explanation_snippet": <str | None>     # Justification snippet or null
          },
          ...
        ]
      },
      "subject_questions": { "questions": [] }, # Placeholder
      "generic_questions": { "questions": [] }  # Placeholder
    }
    Returns an empty structure if no questions found or on error.
    """
    # Default empty structure
    empty_result = {
        "id": youtube_id,
        "video_questions": {"questions": []},
        "subject_questions": {"questions": []},
        "generic_questions": {"questions": []}
    }

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
                #print(f"Info: No question group found for youtube_id={youtube_id}, language={language}")
                return empty_result  # No questions found

            question_group_id = row[0]

            # 2) Fetch all related questions, including the new columns
            cur.execute(
                '''SELECT q_id,                     -- 0
                          question_origin,          -- 1
                          question_explanation_end, -- 2 (New)
                          difficulty,               -- 3 (New)
                          keywords,                 -- 4 (New)
                          question,                 -- 5
                          answer1,                  -- 6
                          answer2,                  -- 7
                          answer3,                  -- 8
                          answer4,                  -- 9
                          explanation_snippet       -- 10 (New)
                   FROM "Question"
                   WHERE question_group_id = %s
                   ORDER BY question_id''',  # Order by insertion order/primary key
                (question_group_id,)
            )
            rows = cur.fetchall()

            # 3) Build the "questions" list
            questions_list = []
            for r in rows:
                # Extract data using indices based on SELECT statement
                # Handle potential None values returned from DB for nullable columns
                q_id = r[0]
                question_origin_time = r[1]  # time object or None
                question_explanation_end_time = r[2]  # time object or None
                difficulty = r[3]  # integer or None
                keywords = r[4]  # list or None (psycopg2 usually converts text[] to list)
                question_txt = r[5]
                a1 = r[6]
                a2 = r[7]
                a3 = r[8]
                a4 = r[9]
                explanation_snippet = r[10]  # string or None

                # Convert time objects to "HH:MM:SS" strings (or None)
                origin_str = time_to_hhmmss(question_origin_time)
                explanation_end_str = time_to_hhmmss(question_explanation_end_time)

                # Append dictionary with all fields in the standard order
                questions_list.append({
                    "q_id": q_id,
                    "question_origin": origin_str,  # Renamed, formatted string or None
                    "question_explanation_end": explanation_end_str,  # New, formatted string or None
                    "difficulty": difficulty,  # New, integer or None
                    "keywords": keywords,  # New, list or None
                    "question": question_txt,
                    "answer1": a1,
                    "answer2": a2,
                    "answer3": a3,
                    "answer4": a4,
                    "explanation_snippet": explanation_snippet  # New, string or None
                })

            # 4) Return final JSON structure
            return {
                "id": youtube_id,
                "video_questions": {
                    "questions": questions_list
                },
                "subject_questions": {"questions": []},  # Placeholder
                "generic_questions": {"questions": []}  # Placeholder
            }

    except Exception as e:
        print(f"Error retrieving questions for youtube_id {youtube_id}: {e}")
        # Return the empty structure on error
        return empty_result


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
