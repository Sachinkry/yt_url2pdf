import os
import json
import re
import requests
import logging
import yt_dlp
import time
from pathlib import Path
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_api_keys():
    """Load API keys from .env file."""
    load_dotenv()
    assemblyai_key = os.getenv("ASSEMBLYAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if not assemblyai_key:
        logger.error("AssemblyAI API key not found in .env file")
        raise ValueError("AssemblyAI API key not found")
    if not google_key:
        logger.error("Google API key not found in .env file")
        raise ValueError("Google API key not found")
    if not openrouter_key:
        logger.error("OpenRouter API key not found in .env file")
        raise ValueError("OpenRouter API key not found")
    
    return assemblyai_key, google_key, openrouter_key

def load_mapping_file():
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

def save_mapping_file(mapping):
    """Save the JSON mapping file."""
    mapping_file = 'data/video_transcript_map.json'
    try:
        Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        logger.info(f"Updated mapping file: {mapping_file}")
    except Exception as e:
        logger.error(f"Failed to save mapping file: {str(e)}")
        raise

def get_next_index(videos_dir):
    """Get the next available index for files like 001_video.mp3."""
    pattern = re.compile(r'^(\d+)_video\.mp3$')
    indices = []
    for f in os.listdir(videos_dir):
        match = pattern.match(f)
        if match:
            indices.append(int(match.group(1)))
    return max(indices, default=0) + 1

def download_youtube_audio(url, videos_dir, index):
    """Download audio from YouTube video using yt-dlp."""
    output_path = f"{videos_dir}/{index:03d}_video.mp3"
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path.rsplit('.', 1)[0],  # Remove extension to avoid double .mp3
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
            'merge_output_format': 'mp3',
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if not os.path.exists(output_path):
            logger.error(f"Audio file not found at {output_path}")
            raise FileNotFoundError(f"Audio file not found at {output_path}")
        
        logger.info(f"Downloaded audio to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to download YouTube audio: {str(e)}")
        raise

def get_youtube_video_id(url):
    """Extract YouTube video ID from URL."""
    try:
        if 'youtube.com' in url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            return parse_qs(parsed.query).get('v', [None])[0]
        elif 'youtu.be' in url:
            return url.split('/')[-1].split('?')[0]
        logger.error(f"Invalid YouTube URL: {url}")
        raise ValueError(f"Invalid YouTube URL: {url}")
    except Exception as e:
        logger.error(f"Failed to extract video ID: {str(e)}")
        raise

def fetch_youtube_transcript(video_id, google_api_key):
    """Fetch auto-generated transcript from YouTube v3 API."""
    try:
        youtube = build('youtube', 'v3', developerKey=google_api_key)
        captions = youtube.captions().list(part='snippet', videoId=video_id).execute()
        caption_items = captions.get('items', [])
        
        # Look for auto-generated captions
        for caption in caption_items:
            if caption['snippet']['trackKind'] == 'ASR':  # Auto-generated
                lang = caption['snippet']['language']
                caption_id = caption['id']
                
                # Download caption
                caption_data = youtube.captions().download(id=caption_id).execute()
                transcript = caption_data.decode('utf-8')
                
                # Parse VTT or SRT format
                lines = transcript.split('\n')
                text_lines = [line.strip() for line in lines if not line.startswith(('WEBVTT', '00:', '-->')) and line.strip()]
                transcript_text = ' '.join(text_lines)
                
                logger.info(f"Fetched YouTube auto-generated transcript in {lang}")
                return transcript_text, lang
        
        logger.info("No auto-generated transcripts found on YouTube")
        return None, None
    except HttpError as e:
        logger.error(f"YouTube API error: {str(e)}")
        return None, None
    except Exception as e:
        logger.error(f"Failed to fetch YouTube transcript: {str(e)}")
        return None, None

def translate_to_english_openrouter(transcript, source_lang, openrouter_key, model="meta-ai/llama-3.1-8b-instruct:free"):
    """Translate transcript to English using OpenRouter API."""
    if source_lang == 'en':
        logger.info("Transcript already in English, no translation needed")
        return transcript
    
    try:
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        You are a professional translator. Translate the following transcript to English with 100% fidelity, preserving all technical terms (e.g., nAChRs, acetylcholinesterase) and context. Do not summarize or omit any content. If the source language is unknown, auto-detect it.

        Transcript:
        {transcript}
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Translate to English"}
            ],
            "max_tokens": 10000
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        translated_text = response.json()["choices"][0]["message"]["content"]
        
        # Log token usage for cost tracking
        usage = response.json().get("usage", {})
        logger.info(f"Translation used {usage.get('total_tokens', 'unknown')} tokens with model {model}")
        
        logger.info(f"Translated transcript from {source_lang or 'auto-detected'} to English")
        return translated_text
    except Exception as e:
        logger.error(f"Failed to translate transcript with OpenRouter: {str(e)}")
        return transcript  # Return original if translation fails

def upload_file_to_assemblyai(file_path, api_key):
    """Upload audio file to AssemblyAI."""
    headers = {'authorization': api_key}
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://api.assemblyai.com/v2/upload',
                headers=headers,
                files={'file': f}
            )
        response.raise_for_status()
        audio_url = response.json()['upload_url']
        logger.info(f"Uploaded file to AssemblyAI: {audio_url}")
        return audio_url
    except Exception as e:
        logger.error(f"Failed to upload file to AssemblyAI: {str(e)}")
        raise

def request_transcription(audio_url, api_key):
    """Request transcription from AssemblyAI."""
    headers = {'authorization': api_key, 'content-type': 'application/json'}
    payload = {'audio_url': audio_url}
    try:
        response = requests.post(
            'https://api.assemblyai.com/v2/transcript',
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        transcript_id = response.json()['id']
        logger.info(f"Transcription requested, ID: {transcript_id}")
        return transcript_id
    except Exception as e:
        logger.error(f"Failed to request transcription: {str(e)}")
        raise

def poll_transcription(transcript_id, api_key):
    """Poll AssemblyAI for transcription status."""
    headers = {'authorization': api_key}
    endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    try:
        while True:
            response = requests.get(endpoint, headers=headers)
            response.raise_for_status()
            status = response.json()['status']
            if status == 'completed':
                logger.info("Transcription completed")
                return response.json()['text'], status
            elif status == 'failed':
                logger.error("Transcription failed")
                raise Exception("Transcription failed")
            logger.info("Transcription in progress, waiting...")
            time.sleep(10)
    except Exception as e:
        logger.error(f"Failed to poll transcription: {str(e)}")
        raise

def save_transcript(transcript, transcript_path):
    """Save transcript to file."""
    try:
        Path(transcript_path).parent.mkdir(parents=True, exist_ok=True)
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(transcript)
        logger.info(f"Saved transcript to {transcript_path}")
    except Exception as e:
        logger.error(f"Failed to save transcript: {str(e)}")
        raise

def transcribe_video(input_path):
    """Main function to transcribe video or YouTube URL."""
    assemblyai_key, google_key, openrouter_key = load_api_keys()
    videos_dir = 'data/videos'
    transcripts_dir = 'data/transcripts'
    mapping = load_mapping_file()

    # Check if input has already been transcribed
    if input_path in mapping and mapping[input_path].get('transcription_status') == 'completed':
        logger.info(f"Input {input_path} already transcribed at {mapping[input_path]['transcript_path']}")
        start_time = time.time()
        with open(mapping[input_path]['transcript_path'], 'r', encoding='utf-8') as f:
            transcript = f.read()
        # Extract index from transcript_path for consistency
        index = int(Path(mapping[input_path]['transcript_path']).stem.split('_')[0])
        elapsed_time = time.time() - start_time
        logger.info(f"Transcription (cached) took {elapsed_time:.2f} seconds")
        return transcript, mapping[input_path]['transcript_path'], index

    # Validate local file path
    if not input_path.startswith(('https://www.youtube.com', 'https://youtu.be')):
        if not os.path.exists(input_path):
            logger.error(f"File {input_path} does not exist")
            raise FileNotFoundError(f"File {input_path} does not exist")
        if not input_path.startswith('data/videos/'):
            logger.error(f"File {input_path} must be in data/videos folder")
            raise ValueError(f"File {input_path} must be in data/videos folder")

    start_time = time.time()
    try:
        index = get_next_index(videos_dir)
        transcript_path = f"{transcripts_dir}/{index:03d}_transcript.txt"
        audio_path = input_path
        transcript_source = 'youtube'  # Default source

        # Try YouTube transcripts for URLs
        transcript = None
        if input_path.startswith(('https://www.youtube.com', 'https://youtu.be')):
            video_id = get_youtube_video_id(input_path)
            transcript, lang = fetch_youtube_transcript(video_id, google_key)
            if transcript:
                transcript = translate_to_english_openrouter(transcript, lang, openrouter_key)
                save_transcript(transcript, transcript_path)

        # Fall back to AssemblyAI
        if not transcript:
            transcript_source = 'assemblyai'
            if input_path.startswith(('https://www.youtube.com', 'https://youtu.be')):
                audio_path = download_youtube_audio(input_path, videos_dir, index)
            audio_url = upload_file_to_assemblyai(audio_path, assemblyai_key)
            transcript_id = request_transcription(audio_url, assemblyai_key)
            transcript, status = poll_transcription(transcript_id, assemblyai_key)
            save_transcript(transcript, transcript_path)

        # Update mapping file
        mapping[input_path] = mapping.get(input_path, {})
        mapping[input_path].update({
            'audio_path': audio_path,
            'transcript_path': transcript_path,
            'transcription_status': 'completed',
            'transcript_source': transcript_source,
            'assemblyai_upload_url': mapping[input_path].get('assemblyai_upload_url', audio_url if transcript_source == 'assemblyai' else None),
            'index': index  # Store index for reference
        })
        save_mapping_file(mapping)

        elapsed_time = time.time() - start_time
        logger.info(f"*** Transcription took {elapsed_time:.2f} seconds ***")
        return transcript, transcript_path, index
    except Exception as e:
        mapping[input_path] = mapping.get(input_path, {})
        mapping[input_path]['transcription_status'] = 'failed'
        save_mapping_file(mapping)
        logger.error(f"Transcription failed for {input_path}: {str(e)}")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python transcribe.py <transcript_path>")
        sys.exit(1)
    # Note: CLI usage doesn't provide an index, so this will fail in the streamlined pipeline
    # This is fine for standalone testing but will need to be handled in yt_to_pdf.py
    transcribe_video(sys.argv[1]) 