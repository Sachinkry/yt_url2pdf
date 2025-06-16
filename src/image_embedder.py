import os
import json
import logging
import re
import requests
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
import io
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_api_keys():
    """Load Google API key and CSE ID from .env file."""
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        logger.error("Google API key or CSE ID not found in .env file")
        raise ValueError("Google API key or CSE ID not found")
    return api_key, cse_id

def load_markdown_file(md_path: str) -> str:
    """Load Markdown file content."""
    try:
        if not os.path.exists(md_path):
            logger.error(f"Markdown file {md_path} does not exist")
            raise FileNotFoundError(f"Markdown file {md_path} does not exist")
        with open(md_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load Markdown file: {str(e)}")
        raise

def save_markdown_file(content: str, index: int) -> str:
    """Save updated Markdown file to notes_img folder with index-based naming."""
    try:
        output_path = f"data/notes_img/{index:03d}_notes_img.md"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved updated Markdown to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to save Markdown file: {str(e)}")
        raise

def is_16_9_ratio(image_data: bytes) -> bool:
    """Check if image has ~16:9 aspect ratio (1.6 to 2.0)."""
    try:
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        ratio = width / height
        return 1.6 <= ratio <= 2.0
    except Exception as e:
        logger.warning(f"Failed to check image ratio: {str(e)}")
        return False

def validate_image(image_data: bytes, dest_path: str) -> bool:
    """Validate image as a JPEG and save if valid."""
    try:
        image = Image.open(io.BytesIO(image_data))
        if image.format != 'JPEG':
            logger.warning(f"Image at {dest_path} is not a JPEG (format: {image.format})")
            return False
        image.verify()  # Check for corruption
        with open(dest_path, 'wb') as f:
            f.write(image_data)
        logger.info(f"Validated and saved image to {dest_path}")
        return True
    except Exception as e:
        logger.warning(f"Image at {dest_path} is corrupted or invalid: {str(e)}")
        return False

def download_image(url: str, dest_path: str) -> bool:
    """Download image from URL and validate as JPEG."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        # if not is_16_9_ratio(response.content):
        #     logger.warning(f"Image at {url} does not have ~16:9 ratio")
        #     return False
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        return validate_image(response.content, dest_path)
    except Exception as e:
        logger.error(f"Failed to download image from {url}: {str(e)}")
        return False

def search_image(query: str, api_key: str, cse_id: str, max_attempts: int = 3) -> tuple:
    """Search for images and return URL and path of first valid JPEG."""
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "cx": cse_id,
            "key": api_key,
            "searchType": "image",
            "num": max_attempts,  # Try up to 3 images
            "imgSize": "large"
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        if "items" not in results or not results["items"]:
            logger.warning(f"No images found for query: {query}")
            return "", ""

        blocked_domains = ["researchgate.net"]
        for item in results["items"][:max_attempts]:
            image_url = item["link"]
            if any(domain in image_url for domain in blocked_domains):
                continue
            image_filename = f"{query.replace(' ', '_').lower()}.jpg"
            temp_path = f"data/temp/{image_filename}"
            if download_image(image_url, temp_path):
                return image_url, temp_path
        logger.warning(f"No valid JPEG images found for query: {query}")
        return "", ""
    except Exception as e:
        logger.error(f"Failed to search image for query '{query}': {str(e)}")
        return "", ""

def get_image_dir(index: int) -> str:
    """Generate image directory path using the index."""
    return f"data/images/{index:03d}_notes_img"

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

def update_mapping_file(mapping: dict, input_path: str, notes_img_path: str, image_paths: list):
    """Update the JSON mapping file with notes_img_path and image_paths."""
    mapping_file = 'data/video_transcript_map.json'
    try:
        if input_path in mapping:
            mapping[input_path]['notes_img_path'] = notes_img_path
            mapping[input_path]['image_paths'] = image_paths
            Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2)
            logger.info(f"Updated mapping file with notes_img_path: {notes_img_path}, image_paths: {image_paths}")
    except Exception as e:
        logger.error(f"Failed to update mapping file: {str(e)}")
        raise

def embed_images_in_markdown(md_path: str, index: int) -> str:
    """Embed images in Markdown file by replacing [INSERT_IMAGE: 'query'] tags."""
    start_time = time.time()
    try:
        api_key, cse_id = load_api_keys()
        md_content = load_markdown_file(md_path)
        mapping = load_mapping_file()
        
        input_path = next((k for k, v in mapping.items() if v.get('notes_path') == md_path), None)
        if not input_path:
            logger.error(f"No mapping found for Markdown file {md_path}")
            raise ValueError(f"No mapping found for Markdown file {md_path}")

        image_tags = re.findall(r'\[INSERT_IMAGE: \'([^\']+)\'\]', md_content)
        if not image_tags:
            logger.info(f"No image tags found in {md_path}")
            output_path = save_markdown_file(md_content, index)
            update_mapping_file(mapping, input_path, output_path, [])
            elapsed_time = time.time() - start_time
            logger.info(f"Image embedding took {elapsed_time:.2f} seconds")
            return output_path

        image_dir = get_image_dir(index)
        image_paths = []
        
        for query in image_tags:
            image_url, temp_path = search_image(query, api_key, cse_id)
            if not image_url:
                logger.warning(f"Skipping tag for query '{query}' due to no valid images")
                md_content = md_content.replace(f"[INSERT_IMAGE: '{query}']", f"<!-- No image found for '{query}' -->")
                continue
            
            image_filename = f"{query.replace(' ', '_').lower()}.jpg"
            final_path = f"{image_dir}/{image_filename}"
            
            try:
                Path(final_path).parent.mkdir(parents=True, exist_ok=True)
                os.rename(temp_path, final_path)
                image_paths.append(final_path)
                
                md_content = md_content.replace(
                    f"[INSERT_IMAGE: '{query}']",
                    f"![{query}]({final_path})"
                )
            except Exception as e:
                logger.warning(f"Failed to process image for query '{query}': {str(e)}")
                md_content = md_content.replace(
                    f"[INSERT_IMAGE: '{query}']",
                    f"<!-- Failed to load image for '{query}' -->"
                )

        output_path = save_markdown_file(md_content, index)
        update_mapping_file(mapping, input_path, output_path, image_paths)
        
        elapsed_time = time.time() - start_time
        logger.info(f"*** Image embedding took {elapsed_time:.2f} seconds ***")
        return output_path
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.info(f"Image embedding (failed) took {elapsed_time:.2f} seconds")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python image_embedder.py <markdown_path>")
        sys.exit(1)

    notes_path = sys.argv[1]
    # Extract numeric prefix from file name like '010_transcript.txt'
    try:
        filename = Path(notes_path).name
        index = int(filename.split('_')[0])
    except Exception as e:
        print(f"Error extracting index from file name '{filename}': {str(e)}")
        sys.exit(1)
    # Note: CLI usage doesn't provide an index, so this will fail in the streamlined pipeline
    # This is fine for standalone testing but will need to be handled in yt_to_pdf.py
    embed_images_in_markdown(notes_path, index)  # Temporary index for standalone testing
