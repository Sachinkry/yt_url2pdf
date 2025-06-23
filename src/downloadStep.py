import logging
import yt_dlp
import os
from urllib.parse import urlparse
import subprocess
from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager
from typing import Dict

logger = logging.getLogger(__name__)

def is_url(input_str):
    try:
        result = urlparse(input_str)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

class DownloadStep(ProcessingStep):
    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        data_manager = DataManager(config)
        id = context.metadata["id"]  # Use global id instead of index
        input_path = context.input_data

        # Check if video already downloaded
        output_path = data_manager.temp_dir / f"{id:03d}_video.mp3"
        if output_path.exists():
            logger.info(f"Video already downloaded at {output_path}")
            context.set_result(self.name, str(output_path))
            return context

        if os.path.isfile(input_path) and input_path.lower().endswith('.mp4'):
            # Local file: extract audio using ffmpeg
            try:
                cmd = [
                    'ffmpeg', '-y', '-i', input_path,
                    '-vn', '-acodec', 'mp3', str(output_path)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"Extracted audio from local video to {output_path}")
                state_manager.save_step_output(
                    context.input_data,
                    config["pipeline"]["input_type"],
                    id,
                    self.name,
                    str(output_path)
                )
                context.set_result(self.name, str(output_path))
                return context
            except Exception as e:
                logger.error(f"Failed to extract audio from {input_path}: {str(e)}")
                raise
        elif is_url(input_path):
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f"{data_manager.temp_dir}/{id:03d}_%(id)s.%(ext)s",
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(context.input_data, download=True)
                    video_id = info.get('id', 'video')
                    temp_path = data_manager.temp_dir / f"{id:03d}_{video_id}.mp3"
                    output_path = data_manager.temp_dir / f"{id:03d}_video.mp3"
                    os.rename(temp_path, output_path)

                state_manager.save_step_output(
                    context.input_data,
                    config["pipeline"]["input_type"],
                    id,
                    self.name,
                    str(output_path)
                )
                context.set_result(self.name, str(output_path))
                logger.info(f"Downloaded video to {output_path}")
            except Exception as e:
                logger.error(f"Failed to download {context.input_data}: {str(e)}")
                raise
            return context
        else:
            logger.error(f"Input {input_path} is not a valid URL or local .mp4 file")
            raise ValueError(f"Input {input_path} is not a valid URL or local .mp4 file")

        return context