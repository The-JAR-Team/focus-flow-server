from google.genai import types

from logic.generation.gemini_api.gemini_api import generate


def question_requests(text_file, lang="Hebrew") -> str:
    prompt = (
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
    config = types.GenerateContentConfig(
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
        system_instruction=[types.Part.from_text(text=prompt)],
    )

    return generate(text_file=text_file, request_config=config, lang=lang)


def summery_request(text_file, lang="Hebrew") -> str:
    prompt = ("""# API Task: Transcript Analysis and Hierarchical Summarization by Subject

""" + f"Target Language = {lang}" + """

## Objective
Analyze the provided video transcript to identify distinct subjects of discussion. For each identified subject, generate a concise title, an overall summary, and a list of more granular sub-summaries. All textual output (titles and summaries) must be in the specified target language. The final output must be a JSON array adhering to the provided OpenAPI schema.

## Input
- **transcript_text**: A string containing the video transcript. The transcript format consists of lines with a timestamp in HH:MM:SS format, followed by a newline, followed by the transcribed text for that timestamp, followed by two newlines before the next timestamp entry.

  **Example:**
  ```
  00:00:00
  it seems like every developer in the

  00:00:01
  world is getting down with mCP right now

  00:00:04
  model context protocol is the hot new
  ```

- **target_language**: A string specifying the language for all generated textual output (e.g., \"en\" for English, \"es\" for Spanish, \"he\" for Hebrew).

## Output Requirements
Produce a JSON array where each object represents a distinct subject identified in the transcript. Each subject object must conform to the following structure:

- **subject_title** (string): A concise, descriptive title for the main subject discussed. This title must be in the target_language.
- **subject_overall_summary** (string): A brief summary covering the entire scope of this subject. This summary must be in the target_language.
- **subject_start_time** (string): The timestamp (format HH:MM:SS) of the first transcript line that contributes to this subject.
- **subject_end_time** (string): The timestamp (format HH:MM:SS) of the last transcript line that contributes to this subject.
- **sub_summaries** (array of objects): A list of sub-summary objects, each detailing a more granular part of the main subject. Each sub-summary object must contain:
  - **summary_text** (string): A detailed summary of this specific sub-segment of the subject. This summary must be in the target_language.
  - **source_start_time** (string): The timestamp (format HH:MM:SS) of the first transcript line that contributes to this sub-summary.
  - **source_end_time** (string): The timestamp (format HH:MM:SS) of the last transcript line that contributes to this sub-summary.

## Detailed Instructions

### Subject Segmentation
- Analyze the transcript content to identify natural breaks and shifts in topics.
- Each distinct topic or coherent segment of discussion should be treated as a separate \"subject.\"
- The segmentation should be logical and based on the semantic flow of the conversation.

### Timestamp Accuracy
- The subject_start_time, subject_end_time, source_start_time, and source_end_time fields must accurately reflect the timestamps from the input transcript text.
- Ensure subject_start_time is the timestamp of the very first line included in the overall subject, and subject_end_time is the timestamp of the very last line included in that overall subject.
- Similarly, for sub_summaries, source_start_time and source_end_time must correspond to the first and last transcript lines covered by that specific sub-summary.

### Summarization Quality
- All summaries (subject_overall_summary and summary_text in sub_summaries) should be concise, informative, and accurately reflect the content of the corresponding transcript segment.
- subject_title should be a clear and brief heading for the subject.

### Language
- Strictly adhere to the target_language parameter for all generated text fields (subject_title, subject_overall_summary, summary_text).

### JSON Format
- The output MUST be a valid JSON array, with each element being a subject object as described.
- Ensure all strings are properly escaped.

## Example

### Input transcript_text (partial):
```
00:00:00
it seems like every developer in the

00:00:01
world is getting down with mCP right now

00:00:04
model context protocol is the hot new

00:00:06
way to build apis and if you don't know

00:00:08
what that is you're ngmi people are

00:00:10
doing crazy things with it like this guy

00:00:12
got claud to design 3d art and blender
```

### Target Language:
\"en\"

### Expected Output Structure (Conceptual):
```json
[
  {
    \"subject_title\": \"Introduction to MCP\",
    \"subject_overall_summary\": \"Overview of Model Context Protocol (MCP) and its current significance.\",
    \"subject_start_time\": \"00:00:00\",
    \"subject_end_time\": \"00:00:08\",
    \"sub_summaries\": [
      {
        \"summary_text\": \"MCP is gaining widespread adoption among developers.\",
        \"source_start_time\": \"00:00:00\",
        \"source_end_time\": \"00:00:01\"
      },
      {
        \"summary_text\": \"It is described as a key new technology for API development, and lack of knowledge is considered detrimental.\",
        \"source_start_time\": \"00:00:04\",
        \"source_end_time\": \"00:00:08\"
      }
    ]
  }
  // ... more subject objects
]
```

Please process the provided transcript and generate the structured JSON summary as detailed above.""")

    generate_content_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Subject": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        required=["description", "subject_title", "subject_overall_summary", "subject_start_time",
                                  "subject_end_time"],
                        properties={
                            "description": types.Schema(
                                type=types.Type.STRING,
                            ),
                            "subject_title": types.Schema(
                                type=types.Type.STRING,
                            ),
                            "subject_overall_summary": types.Schema(
                                type=types.Type.STRING,
                            ),
                            "subject_start_time": types.Schema(
                                type=types.Type.STRING,
                            ),
                            "subject_end_time": types.Schema(
                                type=types.Type.STRING,
                            ),
                            "sub_summaries": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "description": types.Schema(
                                            type=types.Type.STRING,
                                        ),
                                        "properties": types.Schema(
                                            type=types.Type.ARRAY,
                                            items=types.Schema(
                                                type=types.Type.OBJECT,
                                                required=["summary_text", "source_start_time", "source_end_time"],
                                                properties={
                                                    "summary_text": types.Schema(
                                                        type=types.Type.STRING,
                                                    ),
                                                    "source_start_time": types.Schema(
                                                        type=types.Type.STRING,
                                                    ),
                                                    "source_end_time": types.Schema(
                                                        type=types.Type.STRING,
                                                    ),
                                                },
                                            ),
                                        ),
                                    },
                                ),
                            ),
                        },
                    ),
                ),
            },
        ),
        system_instruction=[types.Part.from_text(text=prompt)],
    )

    return generate(text_file=text_file, request_config=generate_content_config, lang=lang)

