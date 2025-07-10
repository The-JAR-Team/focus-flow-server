import logging
import os
import time
import json
import random
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Model configuration
DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"
logger = logging.getLogger(__name__)


def repair_json(json_str: str) -> str:
    """
    Attempts to repair potentially truncated or malformed JSON strings
    by finding the largest valid JSON object or array starting from the beginning.
    It tries to ignore trailing non-JSON characters or comments.

    Args:
        json_str: The potentially malformed JSON string.

    Returns:
        A string containing the largest valid JSON found, or an empty
        object '{}' or array '[]' if no valid JSON start is detected,
        or the original string if parsing attempts fail unexpectedly beyond simple truncation.
    """
    if not isinstance(json_str, str):
        logger.error("Input to repair_json must be a string.")
        return "{}" # Or raise TypeError

    # Strip leading/trailing whitespace
    json_str = json_str.strip()

    # Check if it starts like a JSON object or array
    if not json_str.startswith('{') and not json_str.startswith('['):
        logger.warning("Input string does not start with '{' or '['. Cannot parse as JSON.")
        return "{}" if not json_str.startswith('[') else "[]"

    # Determine if we're looking for an object or array end
    expected_end = '}' if json_str.startswith('{') else ']'

    # Find the last occurrence of the expected closing character
    last_bracket_pos = json_str.rfind(expected_end)

    if last_bracket_pos == -1:
        logger.warning(f"Could not find any closing bracket '{expected_end}'. Returning minimal structure.")
        return "{}" if expected_end == '}' else "[]"

    # Iterate backwards from the last found bracket, trying to parse
    best_valid_json_str = None
    for i in range(last_bracket_pos, 0, -1):
        # Only check positions where the character is the expected end bracket
        if json_str[i] != expected_end:
            continue

        potential_json = json_str[:i+1]
        try:
            # Attempt to parse the substring
            json.loads(potential_json)
            # If successful, this is the largest valid JSON found so far
            best_valid_json_str = potential_json
            logger.debug(f"Successfully parsed JSON substring ending at index {i}.")
            break # Found the largest valid JSON, no need to check shorter ones
        except json.JSONDecodeError:
            # This substring is not valid JSON, continue searching backwards
            logger.debug(f"Failed to parse JSON substring ending at index {i}.")
            continue

    if best_valid_json_str:
        logger.info("Successfully repaired JSON by finding the largest valid substring.")
        return best_valid_json_str
    else:
        # If no substring could be parsed, return a default empty structure or the original string
        logger.warning("Could not repair JSON string. No valid JSON substring found.")
        # Returning an empty structure might be safer than returning potentially broken original string
        return "{}" if expected_end == '}' else "[]"
        # Or return json_str # If you prefer to return the original on complete failure


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
    
    max_attempts = 1
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
