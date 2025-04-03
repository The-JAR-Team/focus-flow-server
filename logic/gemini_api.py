import os
import time
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types


def generate(text_file: str, lang: str = "Hebrew") -> str:
    """
    Uses Gemini API to generate questions from the provided text.
    Retries up to 3 times if the response is not valid JSON per the defined schema.

    Args:
        text_file (str): The transcript or other text to feed into the model.
        lang (str): The target language for question-generation instructions.

    Returns:
        str: The raw generated output (expected to be valid JSON).

    Raises:
        Exception: If all retry attempts fail.
    """
    load_dotenv()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model = "gemini-2.0-flash"

    # Prepare the user content (the transcript / text input)
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=text_file)]
        )
    ]

    # Build system instructions with the provided language.
    system_instruction_text = f"""You are a question-generation assistant creating a large pool of questions from a transcript, covering various difficulty levels for later filtering and use. Maximize the number of relevant questions generated according to the guidelines, with a special emphasis on frequent, simple recall questions. Follow these steps carefully:

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
    generate_content_config = types.GenerateContentConfig(
        temperature=0.8,
        top_p=0.95,
        top_k=40,
        max_output_tokens=8192,
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
        try:
            generated_output = ""
            for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
            ):
                generated_output += chunk.text

            # Validate that the output is valid JSON and conforms to our expected schema.
            parsed_output = json.loads(generated_output)
            if "questions" not in parsed_output:
                raise ValueError("Missing 'questions' key in output")
            break  # Exit loop if successful.
        except Exception as e:
            print(f"Attempt {attempt + 1} failed during generation: {e}")
            last_exception = e
            attempt += 1
            time.sleep(0.1)
    else:
        raise last_exception

    return generated_output


if __name__ == "__main__":
    transcript_data = "Your transcript text goes here..."
    try:
        result = generate(text_file=transcript_data, lang="Hebrew")
        print(result)
    except Exception as err:
        print("Generation failed:", err)
