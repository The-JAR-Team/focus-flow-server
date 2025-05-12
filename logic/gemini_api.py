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


def generate(text_file: str, request_config, lang: str = "Hebrew") -> str:
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
                    config=request_config,
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
