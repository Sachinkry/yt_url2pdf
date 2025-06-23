import logging
import requests
import os
import time
from dotenv import load_dotenv
from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager
from typing import Dict

load_dotenv()
logger = logging.getLogger(__name__)

class TranscribeStep(ProcessingStep):
    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        data_manager = DataManager(config)
        # Load audio file path from context, not temp file
        audio_path = context.get_result("DownloadStep")
        if not audio_path:
            logger.error(f"No audio file available in context for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"No audio file available for {self.name}")
        # If audio_path is not a file, error
        if not os.path.exists(str(audio_path)):
            logger.error(f"Audio file does not exist for {self.name} at {audio_path}")
            context.set_result(self.name, None)
            raise FileNotFoundError(f"Audio file does not exist for {self.name} at {audio_path}")
        index = context.metadata["id"]

        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")

        headers = {"authorization": api_key}
        try:
            # Log upload start
            start_time = time.time()
            logger.info(f"Starting audio upload for {audio_path}")
            with open(audio_path, "rb") as f:
                response = requests.post(
                    "https://api.assemblyai.com/v2/upload",
                    headers=headers,
                    files={"file": f}
                )
            response.raise_for_status()
            upload_url = response.json()["upload_url"]
            logger.info(f"Audio upload completed in {time.time() - start_time:.2f} seconds")

            # Log transcription request
            logger.info(f"Submitting transcription job for {audio_path}")
            response = requests.post(
                "https://api.assemblyai.com/v2/transcript",
                headers=headers,
                json={"audio_url": upload_url}
            )
            response.raise_for_status()
            transcript_id = response.json()["id"]

            # Log polling start
            poll_start = time.time()
            poll_count = 0
            while True:
                poll_count += 1
                response = requests.get(
                    f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                    headers=headers
                )
                response.raise_for_status()
                transcript_data = response.json()
                if transcript_data["status"] == "completed":
                    logger.info(f"Transcription completed in {time.time() - poll_start:.2f} seconds after {poll_count} polls")
                    break
                elif transcript_data["status"] == "error":
                    raise RuntimeError(f"Transcription failed: {transcript_data['error']}")
                time.sleep(5)  # Avoid excessive polling

            transcript_text = transcript_data["text"]
            # Save transcript to context
            context.set_result(self.name, transcript_text)
            # Optionally, save to temp file for caching/debugging
            output_path = data_manager.save_temp(index, "transcript", "txt", transcript_text)
            state_manager.save_step_output(
                input_data=context.input_data,
                input_type=config["pipeline"]["input_type"],
                id=index,
                step_name=self.name,
                output_path=output_path
            )
            logger.info(f"Transcribed audio to {output_path}")
        except Exception as e:
            logger.error(f"Failed to transcribe {audio_path}: {str(e)}")
            state_manager.log_error(context.input_data, config["pipeline"]["input_type"], index, self.name, str(e))
            raise

        return context