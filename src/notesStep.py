import logging
import os
import re
import time
from typing import Dict, Any
import requests
from dotenv import load_dotenv

from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager

logger = logging.getLogger(__name__)
load_dotenv()

class NotesStep(ProcessingStep):
    """Converts transcripts to structured Markdown lecture notes using OpenRouter's Gemini-2.5-pro."""

    def __init__(self):
        self.api_key = self._load_api_key()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "google/gemini-2.5-pro-preview-05-06"
        self.max_retries = 2
        self.max_tokens = 15000
        self.temperature = 0.7

    def _load_api_key(self) -> str:
        """Load OpenRouter API key from environment."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("OPENROUTER_API_KEY not found in environment variables")
            raise ValueError("OPENROUTER_API_KEY not found")
        return api_key

    def _validate_markdown(self, notes: str) -> bool:
        """Validate Markdown structure: at least 2 sections and 3-6 image tags."""
        try:
            # Check for at least two '##' style headers
            sections = len(re.findall(r'^##\s+', notes, re.MULTILINE))
            if sections < 2:
                logger.warning(f"Markdown validation failed: Found {sections} sections, expected at least 2.")
                return False

            # Check for the number of image insertion tags
            image_tags = len(re.findall(r'\[INSERT_IMAGE:\s*\'[^\']+\'\]', notes))
            if not 3 <= image_tags <= 6:
                logger.warning(f"Markdown validation failed: Found {image_tags} image tags, expected between 3 and 6.")
                return False

            logger.info("Markdown validation successful.")
            return True
        except Exception as e:
            logger.error(f"An error occurred during Markdown validation: {str(e)}")
            return False

    def _generate_notes(self, transcript: str) -> str:
        """Generate lecture notes from transcript using OpenRouter API."""
        prompt = """
        You are a skilled medical educator and expert academic note-taker specializing in medical lectures.

        You are given a rough transcript from a spoken medical lecture. The transcript may include grammatical errors, repetition, filler words (e.g., "um," "like"), and poor formatting.

        Your job is to convert it into structured, high-quality lecture notes in **Markdown format** suitable for medical students.

        Instructions:
        1.  **Structure**: Start with a `## Main Title` for the lecture. Organize the rest of the content into logical sections using `###` for sub-headings (e.g., ### Introduction, ### Key Concepts, ### Clinical Applications).
        2.  **Clean and Summarize**: Clean and rephrase the transcript into concise, grammatically correct sentences. Preserve all medical accuracy and details. Remove filler words, off-topic tangents, and excessive repetition while maintaining the speaker's intent.
        3.  **Formatting**: Use bullet points or numbered lists for definitions, processes, and key ideas. Highlight key medical terms in bold (e.g., **Glasgow Coma Scale**).
        4.  **Image Placeholders**: Identify exactly 4 distinct points where a diagram or image would significantly enhance understanding. At these points, insert a placeholder tag in the format `[INSERT_IMAGE: 'A search query for an image']`. Ensure 5 to 8 word search queries that are specific (e.g., 'Anatomical diagram of the brachial plexus' instead of 'nervous system').
        5.  **Output**: Ensure the final output is valid Markdown with proper syntax and consistent formatting. Avoid deeply nested lists.

        Example output:
        ```markdown
        ## Introduction to the Glasgow Coma Scale
        The **Glasgow Coma Scale (GCS)** is a clinical scale used to reliably measure a person's level of consciousness after a brain injury.
        - **Purpose**: Standardizes the evaluation of eye-opening, verbal, and motor responses.
        - **Score Range**: 3 (deep unconsciousness) to 15 (fully conscious).

        [INSERT_IMAGE: 'Chart of the Glasgow Coma Scale components']
        
        ### Eye Response (E)
        * 4 - Spontaneous
        * 3 - To speech
        
        Convert the following transcript into cleaned and structured lecture notes:
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                notes = response.json()["choices"][0]["message"]["content"]
                token_usage = response.json().get('usage', {}).get('total_tokens', 'unknown')
                logger.info(f"Generated notes with {self.model}, used {token_usage} tokens")
                return notes
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else "unknown"
                logger.error(f"Attempt {attempt+1}/{self.max_retries} failed: HTTP {status_code} - {str(e)}")
                if status_code in (429, 500, 503) and attempt < self.max_retries - 1:
                    wait = 2 ** (attempt + 1) * 5
                    logger.info(f"Retrying after {wait} seconds...")
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:
                logger.error(f"Attempt {attempt+1}/{self.max_retries} failed with an unexpected error: {str(e)}")
                if attempt < self.max_retries - 1:
                     time.sleep(5)
                else:
                    raise RuntimeError("Failed to generate notes after all retries") from e
        return "" # Should not be reached, but satisfies linters

    def process(self, context: PipelineContext, config: Dict[str, Any], state_manager: StateManager) -> PipelineContext:
        """Process transcript into Markdown lecture notes."""
        input_type = config["pipeline"]["input_type"]
        
        # FIX: Consistently use 'id' from context metadata
        id = context.metadata.get("id")
        if id is None:
            raise ValueError("Context is missing required metadata 'id'")

        # FIX: Correct arguments for get_step_output
        existing_output = state_manager.get_step_output(context.input_data, input_type, id, self.name)
        if existing_output and os.path.exists(existing_output) and not config["pipeline"].get("force_reprocess", False):
            logger.info(f"Skipping {self.name} (notes exist at {existing_output})")
            context.set_result(self.name, existing_output)
            return context

        try:
            # Load transcript from context, not temp file
            transcript = context.get_result("TranscribeStep")
            if not transcript:
                logger.error(f"No transcript available in context for {self.name}")
                context.set_result(self.name, None)
                raise ValueError("No transcript available for NotesStep")
            # If transcript is a file path, read it (for backward compatibility)
            if os.path.exists(str(transcript)):
                with open(transcript, 'r', encoding='utf-8') as f:
                    transcript = f.read()
            if not transcript.strip():
                logger.error(f"Transcript is empty for {self.name}")
                context.set_result(self.name, None)
                raise ValueError("Transcript is empty for NotesStep")
            # Generate and validate notes
            notes = self._generate_notes(transcript)
            if not self._validate_markdown(notes):
                logger.warning("Generated notes failed validation but will be saved for review.")
            # Save notes to context
            context.set_result(self.name, notes)
            # Optionally, save to temp file for caching/debugging
            data_manager = DataManager(config)
            output_path = data_manager.save_temp(id, "notes", "md", notes)
            state_manager.save_step_output(
                input_data=context.input_data,
                input_type=input_type,
                id=id,
                step_name=self.name,
                output_path=output_path
            )
            logger.info(f"Generated notes at {output_path}")
            return context

        except Exception as e:
            logger.error(f"Failed to generate notes for id {id:03d}: {str(e)}")
            # FIX: log_error already handles marking the step as failed in the database.
            # The direct database manipulation is removed to avoid redundancy and adhere to better design.
            state_manager.log_error(context.input_data, input_type, id, self.name, str(e))
            raise