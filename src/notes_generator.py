# import os
# import json
# import logging
# import re
# import requests
# from pathlib import Path
# from dotenv import load_dotenv

# # Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# def load_api_key():
#     """Load OpenRouter API key from .env file."""
#     load_dotenv()
#     api_key = os.getenv("OPENROUTER_API_KEY")
#     if not api_key:
#         logger.error("OpenRouter API key not found in .env file")
#         raise ValueError("OpenRouter API key not found")
#     return api_key

# def load_transcript(transcript_path: str) -> str:
#     """Load transcript from file."""
#     try:
#         if not os.path.exists(transcript_path):
#             logger.error(f"Transcript file {transcript_path} does not exist")
#             raise FileNotFoundError(f"Transcript file {transcript_path} does not exist")
#         with open(transcript_path, 'r', encoding='utf-8') as f:
#             return f.read()
#     except Exception as e:
#         logger.error(f"Failed to load transcript: {str(e)}")
#         raise

# def save_notes(notes: str, notes_path: str):
#     """Save lecture notes to file."""
#     try:
#         Path(notes_path).parent.mkdir(parents=True, exist_ok=True)
#         with open(notes_path, 'w', encoding='utf-8') as f:
#             f.write(notes)
#         logger.info(f"Saved lecture notes to {notes_path}")
#     except Exception as e:
#         logger.error(f"Failed to save lecture notes: {str(e)}")
#         raise

# def get_notes_path(transcript_path: str) -> str:
#     """Generate notes file path from transcript path."""
#     transcript_name = Path(transcript_path).stem
#     return f"data/notes/{transcript_name}_notes.md"

# def load_mapping_file() -> dict:
#     """Load the JSON mapping file or initialize an empty one."""
#     mapping_file = 'data/video_transcript_map.json'
#     try:
#         if os.path.exists(mapping_file):
#             with open(mapping_file, 'r', encoding='utf-8') as f:
#                 return json.load(f)
#         return {}
#     except Exception as e:
#         logger.error(f"Failed to load mapping file: {str(e)}")
#         raise

# def update_mapping_file(mapping: dict, input_path: str, notes_path: str, validation_status: bool):
#     """Update the JSON mapping file with notes path and validation status."""
#     mapping_file = 'data/video_transcript_map.json'
#     try:
#         if input_path in mapping:
#             mapping[input_path]['notes_path'] = notes_path
#             mapping[input_path]['notes_validation_status'] = 'valid' if validation_status else 'invalid'
#             Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
#             with open(mapping_file, 'w', encoding='utf-8') as f:
#                 json.dump(mapping, f, indent=2)
#             logger.info(f"Updated mapping file with notes path: {notes_path}, validation_status: {'valid' if validation_status else 'invalid'}")
#     except Exception as e:
#         logger.error(f"Failed to update mapping file: {str(e)}")
#         raise

# def generate_clean_notes(transcript: str, api_key: str, model: str) -> str:
#     """Generate clean Markdown notes from transcript."""
#     prompt = """
#     You are a helpful AI assistant specialized in academic note-taking for undergraduate to graduate-level students. Your task is to create detailed, structured lecture notes in **Markdown format** from the provided transcript text appended at the end of this prompt.

#     **Primary Goal:** Produce comprehensive notes (typically 50-60% of transcript length) that faithfully represent the lecture's content and delivery style, enabling readers to understand the material as if they attended the session.

#     **Expected Processing:** Allow approximately 1 minute per 500 words of transcript.

#     ## Core Instructions:

#     1. **Maintain Lecture Flow and Style:**
#     - Start with Introduction, preserve the natural progression and narrative flow of the lecture
#     - Retain the lecturer's specific tone and style (e.g., conversational, formal, storytelling)
#     - Include rhetorical questions or instructive pauses where relevant
#     - Capture characteristic phrasing that contributes to understanding

#     2. **Sequential Content Revelation:**
#     - Present information exactly as it unfolds in the lecture
#     - Do NOT summarize prematurely or jump ahead of reveals
#     - Reflect gradual build-ups to conclusions or definitions
#     - Maintain suspense or pedagogical reveals as intended

#     3. **Accurate Examples and Methods:**
#     - Faithfully reproduce specific examples, analogies, case studies, and calculations
#     - Capture step-by-step explanations exactly as presented
#     - For visual references: Use neutral brackets, e.g., `[visual: diagram shown]`
#     - Never add explanatory guesswork beyond explicit statements
#     - Convert all content to direct, objective prose (no "the lecturer says...")

#     4. **Detailed Yet Systematic Organization:**
#     - Use clear hierarchical structure in Markdown:
#         * `## Main Topics`
#         * `### Subtopics`
#         * `•` Bullet points
#         * `-` Sub-bullets
#     - Balance comprehensiveness with clarity: Include all educational content while maintaining logical organization

#     5. **Content Filtering Guidelines:**
#     **Include:** Core educational material, relevant examples, important clarifications  
#     **Exclude:** 
#     - Social greetings/farewells (unless pedagogically relevant)
#     - Technical difficulties or administrative announcements
#     - Promotional content or marketing material
#     - Off-topic digressions

#     6. **Uncertainty Handling:**
#     - Mark unclear audio: `[unclear audio]`
#     - Flag ambiguous content: `[?uncertain interpretation]`
#     - Note missing context: `[context not provided in transcript]`
#     - Never fabricate missing information

#     ## Example Output Structure:
#     ## Introduction to Cell Biology
#     ### Key Concepts
#     • Cell theory states that...
#     - All living things composed of cells
#     - [visual: cell diagram shown]
    
#     ### Types of Cells
#     • Prokaryotic cells:
#     - No membrane-bound nucleus
#     - Example: bacteria [?exact species unclear]

#     ## Quality Validation Checklist:
#     Before finalizing, verify:
#     - [ ] All main topics from lecture captured
#     - [ ] Sequential flow maintained without premature summaries
#     - [ ] Examples and methods accurately reproduced
#     - [ ] Appropriate depth for academic audience
#     - [ ] No added interpretations beyond transcript
#     - [ ] Clear hierarchical structure throughout
#     - [ ] Uncertain content properly marked

#     ## Special Considerations:
#     - **Technical terminology:** Define as lecturer does; mark undefined terms
#     - **Multi-part lectures:** Note if this appears to be part of a series
#     - **Specialized content:** For medical/legal/technical content, maintain exact wording

#     **Final Output:** Deliver comprehensive lecture notes in **Markdown format** that serve as a reliable study resource, maintaining the lecturer's pedagogical approach while ensuring clarity and organization for effective learning.

#     ---
#     Transcript:
#     """
    
#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "Content-Type": "application/json"
#     }
    
#     payload = {
#         "model": model,
#         "messages": [
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": transcript}
#         ],
#         "max_tokens": 10000,
#         "temperature": 0.7
#     }
    
#     logger.debug(f"Payload for clean notes: {json.dumps(payload, indent=2)}")
    
#     response = requests.post(
#         "https://openrouter.ai/api/v1/chat/completions",
#         headers=headers,
#         json=payload,
#         timeout=30
#     )
#     response.raise_for_status()
#     notes = response.json()["choices"][0]["message"]["content"]
    
#     usage = response.json().get("usage", {})
#     logger.info(f"Generated clean notes with {model}, used {usage.get('total_tokens', 'unknown')} tokens")
    
#     return notes

# def insert_image_tags(clean_notes: str, api_key: str, model: str) -> str:
#     """Insert 3-4 [INSERT_IMAGE] tags in appropriate places."""
#     prompt = """
#     You are a medical educator tasked with enhancing lecture notes by adding visual aids.

#     You are given structured Markdown lecture notes from a medical lecture. Your job is to identify **3 to 4 points** where a diagram or image would enhance understanding (e.g., anatomical structures, flowcharts, charts) and insert `[INSERT_IMAGE: 'search query']` tags at those points.

#     Instructions:
#     1. Analyze the notes to find sections where visuals would clarify complex concepts (e.g., processes, anatomy, scoring systems).
#     2. Suggest **3 to 4** specific image search queries (e.g., 'Glasgow Coma Scale flowchart', 'neuromuscular junction diagram').
#     3. Insert `[INSERT_IMAGE: 'search query']` tags immediately after the relevant section or paragraph, typically after introductions, key processes, or clinical applications.
#     4. Ensure queries are **specific** and searchable (e.g., avoid vague terms like 'GCS'; use 'Glasgow Coma Scale chart' instead).
#     5. Return the **full Markdown notes** with the inserted tags, preserving all original content and formatting.
#     6. Do not modify the structure or text of the notes except to add the tags.
#     7. Ensure valid Markdown syntax.

#     Example input:
#     ```markdown
#     ## Introduction
#     The **Glasgow Coma Scale (GCS)** assesses consciousness in patients with head injuries.
#     - **Purpose**: Standardizes evaluation of eye-opening, verbal, and motor responses.
#     - **Score Range**: 3 (unresponsive) to 15 (fully conscious).

#     ## Components
#     The GCS evaluates three areas: **eye-opening**, **verbal response**, and **motor response**.
#     ```

#     Example output:
#     ```markdown
#     ## Introduction
#     The **Glasgow Coma Scale (GCS)** assesses consciousness in patients with head injuries.
#     - **Purpose**: Standardizes evaluation of eye-opening, verbal, and motor responses.
#     - **Score Range**: 3 (unresponsive) to 15 (fully conscious).

#     [INSERT_IMAGE: 'Glasgow Coma Scale chart']

#     ## Components
#     The GCS evaluates three areas: **eye-opening**, **verbal response**, and **motor response**.

#     [INSERT_IMAGE: 'GCS assessment flowchart']
#     ```

#     Insert image tags into the following Markdown notes:
#     Notes:
#     """
    
#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "Content-Type": "application/json"
#     }
    
#     payload = {
#         "model": model,
#         "messages": [
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": clean_notes}
#         ],
#         "max_tokens": 10000,
#         "temperature": 0.7
#     }
    
#     logger.debug(f"Payload for image tags: {json.dumps(payload, indent=2)}")
    
#     response = requests.post(
#         "https://openrouter.ai/api/v1/chat/completions",
#         headers=headers,
#         json=payload,
#         timeout=30
#     )
#     response.raise_for_status()
#     tagged_notes = response.json()["choices"][0]["message"]["content"]
    
#     usage = response.json().get("usage", {})
#     logger.info(f"Inserted image tags with {model}, used {usage.get('total_tokens', 'unknown')} tokens")
    
#     return tagged_notes

# def generate_lecture_notes(transcript_path: str) -> str:
#     """Convert transcript to lecture notes with image tags using OpenRouter."""
#     # Check if notes already exist
#     notes_path = get_notes_path(transcript_path)
#     mapping = load_mapping_file()
    
#     for input_path, data in mapping.items():
#         if data.get('transcript_path') == transcript_path and data.get('notes_path'):
#             if os.path.exists(data['notes_path']):
#                 logger.info(f"Notes already exist at {data['notes_path']}")
#                 with open(data['notes_path'], 'r', encoding='utf-8') as f:
#                     return f.read()

#     # Load API key and transcript
#     api_key = load_api_key()
#     transcript = load_transcript(transcript_path)
    
#     model = "google/gemini-2.5-pro-preview-05-06"
    
#     try:
#         # Step 1: Generate clean notes
#         clean_notes = generate_clean_notes(transcript, api_key, model)
        
#         # Step 2: Insert image tags
#         tagged_notes = insert_image_tags(clean_notes, api_key, model)
        
#         # Save notes and update mapping
#         save_notes(tagged_notes, notes_path)
#         input_path = next((k for k, v in mapping.items() if v.get('transcript_path') == transcript_path), transcript_path)
#         update_mapping_file(mapping, input_path, notes_path, True)
        
#         return tagged_notes
    
#     except Exception as e:
#         logger.error(f"Failed to generate notes: {str(e)}")
#         raise RuntimeError("OpenRouter API failed to generate notes")

# if __name__ == "__main__":
#     import sys
#     if len(sys.argv) != 2:
#         print("Usage: python notes_generator.py <transcript_path>")
#         sys.exit(1)
#     generate_lecture_notes(sys.argv[1])


import os
import json
import logging
import re
import requests
from pathlib import Path
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_api_key():
    """Load OpenRouter API key from .env file."""
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OpenRouter API key not found in .env file")
        raise ValueError("OpenRouter API key not found")
    return api_key

def load_transcript(transcript_path: str) -> str:
    """Load transcript from file."""
    try:
        if not os.path.exists(transcript_path):
            logger.error(f"Transcript file {transcript_path} does not exist")
            raise FileNotFoundError(f"Transcript file {transcript_path} does not exist")
        with open(transcript_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load transcript: {str(e)}")
        raise

def save_notes(notes: str, notes_path: str):
    """Save lecture notes to file."""
    try:
        Path(notes_path).parent.mkdir(parents=True, exist_ok=True)
        with open(notes_path, 'w', encoding='utf-8') as f:
            f.write(notes)
        logger.info(f"Saved lecture notes to {notes_path}")
    except Exception as e:
        logger.error(f"Failed to save lecture notes: {str(e)}")
        raise

def validate_markdown(notes: str) -> bool:
    """Validate Markdown for structure and image tags."""
    try:
        # Check for at least 2 sections (## headers)
        sections = len(re.findall(r'^##\s+', notes, re.MULTILINE))
        if sections < 2:
            logger.warning(f"Markdown has {sections} sections, expected at least 2")
            return False
        
        # Check for 2-3 image tags
        image_tags = len(re.findall(r'\[INSERT_IMAGE:\s*\'[^\']+\'\]', notes))
        if not 3 <= image_tags <= 6:
            logger.warning(f"Markdown has {image_tags} image tags, expected 3-6")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Failed to validate Markdown: {str(e)}")
        return False

def get_notes_path(index: int) -> str:
    """Generate notes file path using the index."""
    return f"data/notes/{index:03d}_notes.md"

def load_mapping_file() -> dict:
    """Load the JSON mapping file or initialize an empty one."""
    mapping_file = 'data/video_transcript_map.json'
    try:
        if os.path.exists(mapping_file):
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Failed to load mapping file: {str(e)}")
        raise

def update_mapping_file(mapping: dict, input_path: str, notes_path: str, validation_status: bool):
    """Update the JSON mapping file with notes path and validation status."""
    mapping_file = 'data/video_transcript_map.json'
    try:
        if input_path in mapping:
            mapping[input_path]['notes_path'] = notes_path
            mapping[input_path]['notes_validation_status'] = 'valid' if validation_status else 'invalid'
            Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2)
            logger.info(f"Updated mapping file with notes path: {notes_path}, validation_status: {'valid' if validation_status else 'invalid'}")
    except Exception as e:
        logger.error(f"Failed to update mapping file: {str(e)}")
        raise

def generate_lecture_notes(transcript_path: str, index: int) -> tuple[str, str]:
    """Convert transcript to lecture notes using OpenRouter's gemini-2.5-pro."""
    # Check if valid notes already exist
    notes_path = get_notes_path(index)
    mapping = load_mapping_file()
    
    for input_path, data in mapping.items():
        if data.get('transcript_path') == transcript_path and data.get('notes_path'):
            if os.path.exists(data['notes_path']) and data.get('notes_validation_status') == 'valid':
                logger.info(f"Valid notes already exist at {data['notes_path']}")
                start_time = time.time()
                with open(data['notes_path'], 'r', encoding='utf-8') as f:
                    notes = f.read()
                elapsed_time = time.time() - start_time
                logger.info(f"Notes generation (cached) took {elapsed_time:.2f} seconds")
                return notes, data['notes_path']

    # Load API key and transcript
    start_time = time.time()
    try:
        api_key = load_api_key()
        transcript = load_transcript(transcript_path)
        
        # Custom prompt for lecture notes
        prompt = """
        You are a skilled medical educator and expert academic note-taker specializing in medical lectures.

        You are given a rough transcript from a spoken medical lecture. The transcript may include grammatical errors, repetition, filler words (e.g., "um," "like"), and poor formatting.

        Your job is to convert it into structured, high-quality lecture notes in **Markdown format** suitable for medical students.

        Instructions:
        1. **Clean and rephrase** the transcript into concise, grammatically correct sentences, preserving all medical accuracy.
        2. **Organize** content into clear sections with appropriate headings (e.g., ## Introduction, ## Key Concepts, ## Clinical Applications).
        3. Use **bullet points** or numbered lists for definitions, processes, and key ideas.
        4. Highlight **key medical terms** in bold (e.g., **Glasgow Coma Scale**, **acetylcholinesterase**).
        5. Remove filler words, off-topic tangents, and excessive repetition while maintaining the speaker's intent.
        6. Do **not simplify** technical content—preserve all medical details, including mechanisms, terminology, and clinical relevance.
        7. Identify **4 points** where a diagram or image enhances understanding (e.g., anatomical structures, flowcharts). Insert `[INSERT_IMAGE: 'search query']` tags at these points, typically after the **introduction or key processes**. Ensure search queries are specific (e.g., 'Glasgow Coma Scale flowchart' instead of 'GCS').
        8. Ensure the output is valid Markdown with proper syntax and consistent formatting.
        9. Avoid deep nested lists or overly complex structures;

        Example output:
        ```markdown
        ## Introduction
        The **Glasgow Coma Scale (GCS)** assesses consciousness in patients with head injuries.
        - **Purpose**: Standardizes evaluation of eye-opening, verbal, and motor responses.
        - **Score Range**: 3 (unresponsive) to 15 (fully conscious).

        [INSERT_IMAGE: 'Glasgow Coma Scale chart']
        ```

        Convert the following transcript into cleaned and structured lecture notes:
        Transcript:
        """
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        models = ["google/gemini-2.5-pro-exp-03-25", "google/gemini-2.5-pro-preview-05-06"]
        
        for model in models:
            for attempt in range(4):
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": transcript}
                        ],
                        "max_tokens": 10000,
                        "temperature": 0.7
                    }
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    response.raise_for_status()
                    notes = response.json()["choices"][0]["message"]["content"]
                    
                    # Validate Markdown
                    validation_status = validate_markdown(notes)
                    if not validation_status and model == models[-1]:
                        logger.warning("Using invalid Markdown as fallback due to no valid output")
                    
                    # Log token usage
                    usage = response.json().get("usage", {})
                    logger.info(f"Generated notes with {model}, used {usage.get('total_tokens', 'unknown')} tokens")
                    
                    # Save notes and update mapping
                    save_notes(notes, notes_path)
                    input_path = next((k for k, v in mapping.items() if v.get('transcript_path') == transcript_path), transcript_path)
                    update_mapping_file(mapping, input_path, notes_path, validation_status)
                    
                    elapsed_time = time.time() - start_time
                    logger.info(f"*** Notes generation took {elapsed_time:.2f} seconds ***")
                    return notes, notes_path
                
                except requests.exceptions.HTTPError as e:
                    status_code = e.response.status_code
                    logger.error(f"Attempt {attempt+1} with {model} failed: {str(e)}")
                    if status_code in (429, 500, 503):
                        wait = 2 ** attempt * 5  # Exponential backoff: 5, 10, 20, 40 seconds
                        logger.info(f"HTTP {status_code}, waiting {wait} seconds before retry...")
                        time.sleep(wait)
                    else:
                        break
                except Exception as e:
                    logger.error(f"Attempt {attempt+1} with {model} failed: {str(e)}")
                    break
            logger.warning(f"Failed with {model}, trying next model...")
        
        logger.error("Failed to generate notes with all models after retries")
        raise RuntimeError("OpenRouter API failed to generate notes after retries")
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.info(f"Notes generation (failed) took {elapsed_time:.2f} seconds")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python notes_generator.py <transcript_path>")
        sys.exit(1)
    
    transcript_path = sys.argv[1]
    # Extract numeric prefix from file name like '010_transcript.txt'
    try:
        filename = Path(transcript_path).name
        index = int(filename.split('_')[0])
    except Exception as e:
        print(f"Error extracting index from file name '{filename}': {str(e)}")
        sys.exit(1)

    generate_lecture_notes(transcript_path, index)
