import logging
import os
import re
from typing import Dict, List, Tuple, Optional
import requests
from pathlib import Path
from PIL import Image
import io
from dotenv import load_dotenv

from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager

logger = logging.getLogger(__name__)
load_dotenv()

class ImageStep(ProcessingStep):
    """Embeds images in Markdown notes by replacing [INSERT_IMAGE: 'query'] tags."""

    rate_limited = False

    def __init__(self):
        self.api_key, self.cse_id = self._load_api_keys()
        self.search_url = "https://www.googleapis.com/customsearch/v1"
        self.max_attempts = 3
        self.blocked_domains = ["researchgate.net"]

    def _load_api_keys(self) -> Tuple[str, str]:
        """Load Google API key and CSE ID from environment."""
        api_key = os.getenv("GOOGLE_API_KEY")
        cse_id = os.getenv("GOOGLE_CSE_ID")
        if not api_key or not cse_id:
            logger.error("GOOGLE_API_KEY or GOOGLE_CSE_ID not found in environment variables")
            raise ValueError("GOOGLE_API_KEY or GOOGLE_CSE_ID not found")
        return api_key, cse_id

    def _validate_image(self, image_data: bytes, dest_path: Path) -> bool:
        """Validate image as a JPEG and save if valid."""
        try:
            image = Image.open(io.BytesIO(image_data))
            if image.format != "JPEG":
                logger.warning(f"Image at {dest_path} is not a JPEG (format: {image.format})")
                return False
            image.verify()  # Check for corruption
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(image_data)
            logger.info(f"Validated and saved image to {dest_path}")
            return True
        except Exception as e:
            logger.warning(f"Image at {dest_path} is corrupted or invalid: {str(e)}")
            return False

    def _download_image(self, url: str, dest_path: Path) -> bool:
        """Download image from URL and validate as JPEG."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=10)
            response.raise_for_status()
            return self._validate_image(response.content, dest_path)
        except requests.RequestException as e:
            logger.error(f"Failed to download image from {url}: {str(e)}")
            return False

    def _normalize_filename(self, query: str) -> str:
        """Normalize query to a safe, consistent filename for images."""
        # Lowercase, replace spaces and special chars with underscores, remove non-alphanum except underscores and commas
        name = query.lower().replace(' ', '_')
        name = re.sub(r'[^a-z0-9_,]', '', name)
        return f"{name}.jpg"

    def _search_image(self, query: str, index: int, data_manager: DataManager) -> Tuple[Optional[str], Optional[Path]]:
        """Search for images and return URL and path of first valid JPEG."""
        params = {
            "q": query,
            "cx": self.cse_id,
            "key": self.api_key,
            "searchType": "image",
            "num": self.max_attempts,
            "imgSize": "large"
        }
        try:
            response = requests.get(self.search_url, params=params, timeout=10)
            if response.status_code == 429:
                # Set a flag in the context (via global variable for now, will propagate to context in process)
                ImageStep.rate_limited = True
                logger.error(f"Google Custom Search API rate limit hit (429) for query: {query}")
                return None, None
            response.raise_for_status()
            results = response.json()
            if "items" not in results or not results["items"]:
                logger.warning(f"No images found for query: {query}")
                return None, None

            image_dir = data_manager.temp_dir / f"{index:03d}_images"
            for item in results["items"][:self.max_attempts]:
                image_url = item["link"]
                if any(domain in image_url for domain in self.blocked_domains):
                    logger.debug(f"Skipping image from blocked domain: {image_url}")
                    continue
                image_filename = self._normalize_filename(query)
                dest_path = image_dir / image_filename
                if self._download_image(image_url, dest_path):
                    return image_url, dest_path
            logger.warning(f"No valid JPEG images found for query: {query}")
            return None, None
        except requests.RequestException as e:
            logger.error(f"Failed to search image for query '{query}': {str(e)}")
            return None, None

    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        """Process Markdown notes to embed images for [INSERT_IMAGE: 'query'] tags."""
        data_manager = DataManager(config)
        notes_md = context.get_result("NotesStep")
        index = context.metadata["id"]
        pipeline_type = config["pipeline"]["input_type"]

        # Add a class-level flag to track rate limiting
        ImageStep.rate_limited = False

        if not notes_md:
            logger.error(f"No notes available in context for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"No notes available for {self.name}")
        if os.path.exists(str(notes_md)):
            with open(notes_md, 'r', encoding='utf-8') as f:
                notes_md = f.read()
        if not notes_md.strip():
            logger.error(f"Notes are empty for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"Notes are empty for {self.name}")

        # Check for cached output
        existing_output = state_manager.get_step_output(context.input_data, pipeline_type, index, self.name)
        if existing_output and os.path.exists(existing_output) and not config["pipeline"].get("force_reprocess", False):
            logger.info(f"Skipping {self.name} (output exists at {existing_output})")
            context.set_result(self.name, existing_output)
            return context

        try:
            # Load Markdown notes from context, not temp file
            notes_md = context.get_result("NotesStep")
            if not notes_md:
                logger.error(f"No notes available in context for {self.name}")
                context.set_result(self.name, None)
                raise ValueError(f"No notes available for {self.name}")
            # If notes_md is a file path, read it (for backward compatibility)
            if os.path.exists(str(notes_md)):
                with open(notes_md, 'r', encoding='utf-8') as f:
                    notes_md = f.read()
            if not notes_md.strip():
                logger.error(f"Notes are empty for {self.name}")
                context.set_result(self.name, None)
                raise ValueError(f"Notes are empty for {self.name}")
            # Find image tags and process as before
            image_tags = re.findall(r'\[INSERT_IMAGE:\s*\'([^\']+)\'\]', notes_md)
            if not image_tags:
                logger.info(f"No image tags found in notes for {self.name}")
                context.set_result(self.name, notes_md)
                # Optionally, save to temp file for caching/debugging
                output_path = data_manager.save_temp(index, "notes_img", "md", notes_md)
                state_manager.save_step_output(
                    input_data=context.input_data,
                    input_type=pipeline_type,
                    id=index,
                    step_name=self.name,
                    output_path=output_path
                )
                return context

            # Process image tags
            image_paths: List[str] = []
            image_dir = data_manager.temp_dir / f"{index:03d}_images"
            for query in image_tags:
                filename = self._normalize_filename(query)
                dest_path = image_dir / filename
                image_url, temp_path = self._search_image(query, index, data_manager)
                if ImageStep.rate_limited:
                    context.metadata["image_rate_limited"] = True
                if not image_url or not temp_path:
                    logger.warning(f"No valid image for query '{query}', adding placeholder")
                    notes_md = notes_md.replace(
                        f"[INSERT_IMAGE: '{query}']",
                        f"<!-- No image found for '{query}' -->"
                    )
                    continue

                # Always use normalized filename for markdown reference
                relative_path = f"images/{filename}"
                notes_md = notes_md.replace(
                    f"[INSERT_IMAGE: '{query}']",
                    f"![{query}]({relative_path})"
                )
                image_paths.append(str(dest_path))

            # Save updated Markdown to context
            context.set_result(self.name, notes_md)
            # Optionally, save to temp file for caching/debugging
            output_path = data_manager.save_temp(index, "notes_img", "md", notes_md)
            state_manager.save_step_output(
                input_data=context.input_data,
                input_type=pipeline_type,
                id=index,
                step_name=self.name,
                output_path=output_path
            )
            logger.info(f"Generated image-enhanced notes at {output_path}")
            return context

        except Exception as e:
            logger.error(f"Failed to process images: {str(e)}")
            state_manager.log_error(context.input_data, pipeline_type, index, self.name, str(e))
            raise