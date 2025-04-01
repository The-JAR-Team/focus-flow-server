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
      questions (list): A list of dictionaries, each expected to have fields:
        {
          "q_id": <str>,                     # e.g. "q1"
          "question_origin": <str>,          # e.g. "00:01:48"
          "question_explanation_end": <str>, # e.g. "00:02:15"
          "difficulty": <int>,               # e.g. 3 (1-10)
          "keywords": <list[str]>,           # e.g. ["term", "definition"]
          "question": <str>,
          "answer1": <str>,
          "answer2": <str>,
          "answer3": <str>,
          "answer4": <str>,
          "explanation_snippet": <str>
        }

    Returns:
      int: The newly created question_group_id, or 0 on failure.
    """
    group_id = 0  # Initialize group_id
    try:
        # Use the provided DB class's context manager
        with DB.get_cursor() as cur:
            # 1) Insert a row into Question_Group (one per youtube_id + language combo).
            cur.execute(
                '''INSERT INTO "Question_Group" (youtube_id, language)
                   VALUES (%s, %s)
                   RETURNING question_group_id
                ''',
                (youtube_id, language)
            )
            # Ensure fetchone() didn't return None before accessing [0]
            result = cur.fetchone()
            if result is None:
                # Rollback should happen automatically due to exception + context manager
                raise Exception("Failed to insert into Question_Group or retrieve group_id.")
            group_id = result[0]

            # 2) Insert each question into Question, linked to group_id.
            for q in questions:
                # Extract all fields, providing defaults (None) if missing
                q_id = q.get("q_id")
                question_origin_str = q.get("question_origin")
                question_explanation_end_str = q.get("question_explanation_end")  # New
                difficulty = q.get("difficulty")  # New
                keywords = q.get("keywords")  # New (should be a list)
                question_txt = q.get("question")
                answer1 = q.get("answer1")
                answer2 = q.get("answer2")
                answer3 = q.get("answer3")
                answer4 = q.get("answer4")
                explanation_snippet = q.get("explanation_snippet")  # New

                # --- Data Type Preparations ---
                # Convert time strings -> time objects (or None) using the provided helper
                question_origin_time = parse_hhmmss_to_time(question_origin_str)
                question_explanation_end_time = parse_hhmmss_to_time(question_explanation_end_str)

                # Ensure keywords is a list or None for db array insertion
                # psycopg2 typically handles Python lists correctly for text[] columns
                db_keywords = keywords if isinstance(keywords, list) else None

                # Ensure difficulty is an integer or None
                db_difficulty = int(difficulty) if difficulty is not None else None

                # --- Execute INSERT ---
                cur.execute(
                    '''INSERT INTO "Question" (
                           question_group_id,          -- 1
                           q_id,                       -- 2
                           question_origin,            -- 3
                           question_explanation_end,   -- 4 (New)
                           difficulty,                 -- 5 (New)
                           keywords,                   -- 6 (New)
                           question,                   -- 7 
                           answer1,                    -- 8
                           answer2,                    -- 9
                           answer3,                    -- 10
                           answer4,                    -- 11
                           explanation_snippet         -- 12 (New)
                       )
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        group_id,  # 1
                        q_id,  # 2
                        question_origin_time,  # 3
                        question_explanation_end_time,  # 4 (New)
                        db_difficulty,  # 5 (New)
                        db_keywords,  # 6 (New, pass list or None)
                        question_txt,  # 7
                        answer1,  # 8
                        answer2,  # 9
                        answer3,  # 10
                        answer4,  # 11
                        explanation_snippet  # 12 (New)
                    )
                )

            # Commit happens automatically when 'with' block exits without error

            return group_id

    except Exception as e:
        # Rollback happens automatically due to exception + context manager
        print(f"Error storing questions for youtube_id {youtube_id} (group_id {group_id}): {e}")
        # Consider more specific error handling/logging based on exception type
        return 0  # Return 0 or raise exception as appropriate


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
                print(f"Info: No question group found for youtube_id={youtube_id}, language={language}")
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
