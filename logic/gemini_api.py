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

    # Build a system instruction with the new prompt, replacing {lang} with the provided language
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
    * **Also Capture Higher Difficulties:** While maximizing Level 1-2 questions, continue to identify and generate questions for moderate (5-7) and higher complexity (8-10) whenever the material supports it (e.g., comparisons, analysis, synthesis). Do not neglect these harder questions if valid opportunities exist.
    * **Generate Concurrently:** Generate a question whenever a valid opportunity (at any difficulty level) is identified. Finding an opportunity for an easy question should not preclude generating a medium or hard question based on the same or overlapping content if distinct, relevant questions can be formulated, and vice-versa.
    * **Allow Detail & Granularity:** Focus on covering the material thoroughly at a detailed level. It is acceptable to generate questions focusing on specific details within a broader topic, or to have multiple questions relating to the same core concept asked in different ways or focusing on different facets.
    * **Distribution & Density:** Distribute questions frequently throughout the transcript's duration. As a guideline, aim for high density by generating questions covering specific points or pieces of information roughly every **1-2 minutes *of relevant discussion*** found in the transcript (this applies to the overall rate). Maximize the total number of relevant questions generated.

5.  **Timestamp Requirements**:
    * Identify the primary segment for each question's answer.
    * Set `question_origin` (`HH:MM:SS`) **just before** the relevant information begins (err up to 10s early if unsure, aim for close).
    * Set `question_explanation_end` (`HH:MM:SS`) where the relevant information concludes (err slightly later if unsure).

6.  **Add Metadata & Justification**:
    * **`difficulty`**: Assign an integer score **1 to 10** based on the complexity of the required understanding, using the definitions below. Tag each generated question accurately for later filtering. **Ensure frequent use of levels 1-2 for simple recall checks.**
        * **1-2: Very Easy Recall** (specific name, number, term, definition *just stated*, direct fact).
        * **3-4: Simple Comprehension/Application** (understanding a simple concept *as explained*, result of a *direct* example).
        * **5-7: Moderate Complexity** (linking related ideas *discussed separately*, applying a concept slightly differently, explaining a process, comparing/contrasting).
        * **8-10: Higher Complexity** (synthesizing info, analyzing implications, evaluating arguments, complex problems). *Use when genuinely warranted.*
    * **`keywords`**: Extract 1-3 relevant `keywords` (array of strings).
    * **`explanation_snippet`**: Provide a brief (1-2 sentences) **direct quote** or **very close paraphrase** from the `origin`-`end` transcript segment justifying `answer1`. Keep it concise.

7.  **Output Format** (Strict JSON only):
    * Your final output must be **only** valid JSON, with **no introductory text, explanations, apologies, summaries, or any text outside the JSON structure**.
    * One top-level key: "questions" (an array of objects).
    * Each object must have exactly these keys, **in this specific order**:
        1.  `q_id` (string, sequential identifier like "q1", "q2", ...)
        2.  `question_origin` (string, HH:MM:SS)
        3.  `question_explanation_end` (string, HH:MM:SS)
        4.  `difficulty` (integer, 1-10)
        5.  `keywords` (array of strings)
        6.  `question` (string, question text in {lang})
        7.  `answer1` (string, correct answer, primarily in {lang}, potentially with Original Term per Step 2)
        8.  `answer2` (string, incorrect answer, primarily in {lang}, potentially with Original Term per Step 2)
        9.  `answer3` (string, incorrect answer, primarily in {lang}, potentially with Original Term per Step 2)
        10. `answer4` (string, incorrect answer, primarily in {lang}, potentially with Original Term per Step 2)
        11. `explanation_snippet` (string, justification text in {lang})
    * Ensure all specified keys are present for every question object.

8.  **Example JSON Structure** (Illustrative content):
    ```json
    {{
      "questions": [
        {{
          "q_id": "q1",
          "question_origin": "00:01:15",
          "question_explanation_end": "00:01:28",
          "difficulty": 1,
          "keywords": ["term", "definition"],
          "question": "What specific term was just defined?",
          "answer1": "The correct term",
          "answer2": "A related but incorrect term",
          "answer3": "A plausible sounding incorrect term",
          "answer4": "A completely unrelated term",
          "explanation_snippet": "The transcript stated, 'The term X is defined as...'"
         }},
         {{
           "q_id": "q2",
           "question_origin": "00:01:16",
           "question_explanation_end": "00:01:25",
           "difficulty": 1,
           "keywords": ["fact", "recall"],
           "question": "What specific number was associated with X?",
           "answer1": "The number mentioned (e.g., 5)",
           "answer2": "A slightly different number (e.g., 6)",
           "answer3": "A number related to Y",
           "answer4": "An irrelevant number",
           "explanation_snippet": "'...and the value for X is 5.'"
         }},
         {{
           "q_id": "q3",
           "question_origin": "00:01:18",
           "question_explanation_end": "00:01:35",
           "difficulty": 5,
           "keywords": ["term", "comparison"],
           "question": "How does term X compare to term Y mentioned earlier?",
           "answer1": "Correct comparison based on text",
           "answer2": "Incorrect comparison",
           "answer3": "Plausible but wrong comparison",
           "answer4": "Comparison not supported by text",
           "explanation_snippet": "Later, it says 'Unlike term Y, term X has the property...'"
         }}
      ]
    }}
    ```

Remember to replace **{lang}** with the actual target language name (e.g., "Hebrew", "English")."""

    # Updated configuration with new temperature (0.8) and schema
    generate_content_config = types.GenerateContentConfig(
        temperature=0.8,
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
                            "q_id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Unique sequential identifier for the question (e.g., q1, q2).",
                            ),
                            "question_origin": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Timestamp (HH:MM:SS) just before the relevant explanation starts in the transcript.",
                            ),
                            "question_explanation_end": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Timestamp (HH:MM:SS) where the relevant explanation ends in the transcript.",
                            ),
                            "difficulty": genai.types.Schema(
                                type=genai.types.Type.INTEGER,
                                description="Estimated difficulty level of the question on a scale of 1 (easy) to 10 (hard).",
                            ),
                            "keywords": genai.types.Schema(
                                type=genai.types.Type.ARRAY,
                                description="Array of 1-3 keywords related to the question's topic.",
                                items=genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                ),
                            ),
                            "question": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="The question text in the specified language.",
                            ),
                            "answer1": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="The correct answer based on the transcript, primarily in the specified language. May include original term formatting (e.g., 'Translation - OriginalTerm') if source/target languages differ and term is technical jargon/acronym.",
                            ),
                            "answer2": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect but plausible distractor answer, primarily in the specified language. May include original term formatting.",
                            ),
                            "answer3": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect but plausible distractor answer, primarily in the specified language. May include original term formatting.",
                            ),
                            "answer4": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="An incorrect but plausible distractor answer, primarily in the specified language. May include original term formatting.",
                            ),
                            "explanation_snippet": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="A brief quote or close paraphrase from the transcript justifying answer1, primarily in the specified language.",
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

    # Return the raw text
    return generated_output


if __name__ == "__main__":
    # Example usage:
    transcript_data = "Your transcript text goes here..."
    result = generate(text_file=transcript_data, lang="Hebrew")
    print(result)