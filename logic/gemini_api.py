import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


def generate(text_file: str, lang: str = "Hebrew"):
    """
    :param text_file: The transcript or other text to feed into the model.
    :param lang: The language for question-generation instructions (default is 'Hebrew').
    :return: A string of generated output OR parsed JSON (if return_json=True).
    """
    load_dotenv()

    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    model = "gemini-2.0-flash"

    # Prepare the user content (the transcript / text input)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=text_file),
            ],
        ),
    ]

    # Build a system instruction, injecting the lang param:
    # (We replace the "in Hebrew" requirement with "in {lang}")
    system_instruction_text = f"""---------------
You are a question-generation assistant. Follow these steps carefully:

1. **Task**: Create multiple-choice questions in {lang} from the provided text transcript.
   - All questions and answers must be written in {lang}.
   - Each question must have exactly four possible answers (answer1 is correct; answers 2–4 must be incorrect but plausible).

2. **Avoid Trivial or Irrelevant Questions**:
   - Do not create questions about random filler or trivial exclamations that do not convey meaningful information.
   - Ensure each question addresses a key concept, explanation, or example actually discussed in that portion of the transcript.

3. **Even Coverage Across the Entire Transcript**:
   - The transcript is ~3 hours long.
   - Break it into **6 segments** of ~30 minutes each.
   - For each 30-minute segment, generate **5 to 7** meaningful questions.
     - This ensures that the final JSON has ~30–42 total questions overall.

4. **Timestamp Requirements**:
   - Each question’s `question_origin` must be a valid timestamp (`HH:MM:SS`) **that appears in the transcript during that 30-minute window**.
   - If an idea appears at “00:45:12” in the text, for example, that question must use `"question_origin": "00:45:12"` or the closest relevant time.

5. **Output Format** (JSON only):
   - Your final output must be valid JSON with **no extra commentary or explanations**.
   - The JSON object has exactly one key: `"questions"`.
   - `"questions"` is an array of objects. Each object has the keys:
     {{
       "q_id": "q1",
       "question_origin": "HH:MM:SS",
       "question": "…",
       "answer1": "…",
       "answer2": "…",
       "answer3": "…",
       "answer4": "…"
     }}
   - No other keys are allowed.

6. **Correct vs. Incorrect Answers**:
   - `answer1` must be factually correct based on that portion of the transcript.
   - `answer2`, `answer3`, and `answer4` must be believable distractors but **incorrect** per the transcript.

7. **Example** (just a structural sample, not from your real transcript):
   ```json
   {{
     "questions": [
       {{
         "q_id": "q1",
         "question_origin": "00:00:11",
         "question": "כמה שרירים יש לנו?",
         "answer1": "יותר מ-600",
         "answer2": "יותר מ-500",
         "answer3": "יותר מ-700",
         "answer4": "יותר מ-400"
       }},
       {{
         "q_id": "q2",
         "question_origin": "00:00:13",
         "question": "באיזה אחוז ממשקל הגוף שלנו מהווים השרירים?",
         "answer1": "בין שליש למחצית",
         "answer2": "בין רבע לשליש",
         "answer3": "בין חצי לשני שליש",
         "answer4": "בין חמישית לרבע"
       }}
     ]
   }}
"""

    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        top_k=40,
        max_output_tokens=8192,
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["questions"],
            properties={
                "questions": genai.types.Schema(
                    type=genai.types.Type.ARRAY,
                    items=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=[
                            "q_id",
                            "question_origin",
                            "question",
                            "answer1",
                            "answer2",
                            "answer3",
                            "answer4",
                        ],
                        properties={
                            "q_id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Unique identifier for the question (e.g., q1, q2).",
                            ),
                            "question_origin": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Timestamp in HH:MM:SS format, indicating the starting time in the transcript.",
                            ),
                            "question": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="The question",
                            ),
                            "answer1": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="The correct answer",
                            ),
                            "answer2": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect answer",
                            ),
                            "answer3": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect answer",
                            ),
                            "answer4": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect answer",
                            ),
                        },
                    ),
                ),
            },
        ),
        system_instruction=[
            types.Part.from_text(text=system_instruction_text),
        ],
    )

    # Collect the output from the streaming call
    generated_output = ""
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        generated_output += chunk.text

    # Otherwise, return the raw text
    return generated_output


if __name__ == "__main__":
    # Example usage:
    transcript_data = "Your transcript text goes here..."
    result = generate(text_file=transcript_data, lang="Hebrew")
    print(result)
