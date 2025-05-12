import os
import time
import json
import random
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Model configuration
DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"


def repair_json(json_str):
    """
    Attempts to repair truncated or malformed JSON, focusing on finding the
    last complete object within the 'questions' array.
    """
    # 1. Try to find the start of the questions array
    match = re.search(r'"questions"\s*:\s*\[', json_str)
    if not match:
        return json_str # Cannot find the array start

    array_start_index = match.end()
    prefix = json_str[:array_start_index] # e.g., '{\n  "questions": ['

    # 2. Work backwards from the end to find the last complete object '}'
    content_after_array_start = json_str[array_start_index:]
    last_brace_index = content_after_array_start.rfind('}')
    if last_brace_index == -1:
        # Try closing the array immediately if empty
        repaired = prefix + ']}'
        try:
            json.loads(repaired)
            return repaired
        except:
            return json_str # Give up

    # 3. Assume the content up to the last '}' might be a valid object or list of objects
    potential_array_content = content_after_array_start[:last_brace_index + 1]

    # 4. Construct the potential JSON string
    # Ensure proper closing brackets/braces for the overall structure
    repaired = prefix + potential_array_content + ']}'

    # 5. Try parsing the repaired string
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError as e:
        # Fallback: Try the simple rfind(']}') approach from before
        pos = json_str.rfind(']}')
        if pos != -1:
            final_fallback = json_str[:pos+2]
            try:
                json.loads(final_fallback)
                return final_fallback
            except:
                return json_str # All repair attempts failed
        else:
            return json_str # All repair attempts failed


def generate(text_file: str, lang: str = "Hebrew") -> str:
    """
    Uses Gemini API to generate questions, with robust JSON parsing and repair.
    """
    load_dotenv()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    #print(f"[DEBUG] Using model: {model}")

    # Prepare the user content (the transcript / text input)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=text_file)]
        )
    ]

    system_instruction_text = (
        "Ensure the output is valid JSON: escape all double‑quotes inside strings and do not truncate the JSON structure.\n"
        + f"""You are a question-generation assistant creating a large pool of questions from a transcript, covering various difficulty levels for later filtering and use. Maximize the number of relevant questions generated according to the guidelines, with a special emphasis on frequent, simple recall questions. Follow these steps carefully:

1.  **Task**: Create multiple-choice questions in **{lang}** from the provided text transcript.
    * All questions and answers must be written primarily in **{lang}**.
    * Each question must have exactly four possible answers: `answer1` must be the correct answer based *only* on the transcript content, while `answer2`, `answer3`, and `answer4` must be incorrect but plausible distractors related to the topic.

2.  **Terminology Handling (Cross-Language)**:
    * **Apply this step ONLY IF the source transcript language is different from the target language `{lang}`.**
    * When generating answer options (`answer1`-`answer4`), identify technical acronyms or jargon.
    * For such terms, consider formatting the answer as "{{Translation/Explanation in {lang}}} - {{Original Term}}" if it enhances clarity. Use judgment based on standard translations and context.

3.  **Handle Imperfect Transcripts & Identify Usable Content**:
    * The transcript may contain errors, noise (e.g., `[MUSIC]`, `[APPLAUSE]`), filler words, tangents, or unintelligible sections. **Skip over these parts.**
    * **Identify and prioritize** sections conveying clear information: concepts, definitions, explanations, processes, examples, **specific stated facts, details, figures, or key terms mentioned.**

4.  **Generate High-Volume, Varied Questions with Emphasis on Recall**:
    * **Maximize Opportunities:** Your goal is to generate a large volume of relevant questions covering the material at a granular level, across all difficulty levels simultaneously.
    * **Aggressively Generate Level 1-2 Questions:** Make a strong effort to generate **numerous Difficulty 1-2 questions** (Very Easy Recall) whenever a specific name, number, term, simple definition, or direct statement of fact is presented in the transcript. **For these Level 1-2 questions specifically, repetition or slight variations testing the same basic fact are acceptable** to ensure maximum coverage of simple recall points. Generate these whenever the opportunity arises.
    * **Also Capture Higher Difficulties:** While maximizing Level 1-2 questions, continue to identify and generate questions for moderate (5-7) and higher complexity (8-10) whenever the material supports it.
    * **Generate Concurrently:** Generate a question whenever a valid opportunity (at any difficulty level) is identified.
    * **Allow Detail & Granularity:** Focus on covering the material thoroughly at a detailed level.
    * **Distribution & Density:** Distribute questions frequently throughout the transcript's duration. Aim for high density by generating questions covering specific points roughly every 1-2 minutes of relevant discussion.

5.  **Timestamp Requirements**:
    * Set `question_origin` (HH:MM:SS) just before the relevant explanation begins.
    * Set `question_explanation_end` (HH:MM:SS) where the relevant explanation ends.

6.  **Add Metadata & Justification**:
    * **`difficulty`**: Assign an integer score (1 to 10) based on complexity.
    * **`keywords`**: Extract 1-3 relevant keywords.
    * **`explanation_snippet`**: Provide a brief quote or close paraphrase justifying `answer1`.

7.  **Output Format** (Strict JSON only):
    * Output must be only valid JSON with one top-level key "questions" (an array of objects).
    * Each question object must have exactly these keys in this order:
        1. `q_id`
        2. `question_origin`
        3. `question_explanation_end`
        4. `difficulty`
        5. `keywords`
        6. `question`
        7. `answer1`
        8. `answer2`
        9. `answer3`
        10. `answer4`
        11. `explanation_snippet`
"""
    )

    generate_content_config = types.GenerateContentConfig(
        temperature=0.8,
        top_p=0.95,
        top_k=40,
        max_output_tokens=32768,
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            required=["questions"],
            properties={
                "questions": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        required=[
                            "q_id",
                            "question_origin",
                            "question_explanation_end",
                            "difficulty",
                            "keywords",
                            "question",
                            "answer1",
                            "answer2",
                            "answer3",
                            "answer4",
                            "explanation_snippet"
                        ],
                        properties={
                            "q_id": types.Schema(
                                type=types.Type.STRING,
                                description="Unique sequential identifier for the question (e.g., q1, q2).",
                            ),
                            "question_origin": types.Schema(
                                type=types.Type.STRING,
                                description="Timestamp (HH:MM:SS) just before the relevant explanation starts.",
                            ),
                            "question_explanation_end": types.Schema(
                                type=types.Type.STRING,
                                description="Timestamp (HH:MM:SS) where the relevant explanation ends.",
                            ),
                            "difficulty": types.Schema(
                                type=types.Type.INTEGER,
                                description="Difficulty level of the question (1-10).",
                            ),
                            "keywords": types.Schema(
                                type=types.Type.ARRAY,
                                description="Array of 1-3 keywords related to the question.",
                                items=types.Schema(
                                    type=types.Type.STRING,
                                ),
                            ),
                            "question": types.Schema(
                                type=types.Type.STRING,
                                description="The question text.",
                            ),
                            "answer1": types.Schema(
                                type=types.Type.STRING,
                                description="The correct answer.",
                            ),
                            "answer2": types.Schema(
                                type=types.Type.STRING,
                                description="An incorrect but plausible answer.",
                            ),
                            "answer3": types.Schema(
                                type=types.Type.STRING,
                                description="An incorrect but plausible answer.",
                            ),
                            "answer4": types.Schema(
                                type=types.Type.STRING,
                                description="An incorrect but plausible answer.",
                            ),
                            "explanation_snippet": types.Schema(
                                type=types.Type.STRING,
                                description="A brief explanation justifying answer1.",
                            ),
                        },
                    ),
                ),
            },
        ),
        system_instruction=[types.Part.from_text(text=system_instruction_text)],
    )
    
    max_attempts = 3
    attempt = 0
    last_exception = None
    generated_output = ""
    
    while attempt < max_attempts:
        generated_output = "" # Reset for each attempt
        try:
            for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
            ):
                if chunk and getattr(chunk, "text", None):
                    generated_output += chunk.text

            try:
                # Attempt 1: Direct parse
                parsed_output = json.loads(generated_output)

            except json.JSONDecodeError as e:
                # Attempt 2: Use the repair function
                repaired_json = repair_json(generated_output)
                try:
                    parsed_output = json.loads(repaired_json)
                    generated_output = repaired_json # IMPORTANT: Update output if repair worked
                except json.JSONDecodeError as repair_e:
                    raise ValueError(f"JSON repair failed after initial error: {e}") from repair_e

            # Schema Validation (remains the same)
            if "questions" not in parsed_output:
                raise ValueError("Missing 'questions' key in output")
            question_count = len(parsed_output.get("questions", []))
            if question_count == 0:
                pass # Keep allowing empty results

            break # Exit loop if successful.

        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(min(2 ** attempt + random.random(), 10)) # Keep backoff
            
            last_exception = e
            attempt += 1
            time.sleep(1.0 + random.random()) # Slightly longer backoff
    else:
        raise last_exception if last_exception else Exception("Unknown generation error after multiple attempts")

    return generated_output


if __name__ == "__main__":
    transcript_data = "Your transcript text goes here..."
    try:
        result = generate(text_file=transcript_data, lang="Hebrew")
        print(f"Generated result:\n{result}")
    except Exception as err:
        print(f"Generation failed in __main__: {err}")
