import logging
import os
import yaml
from pathlib import Path
from typing import List, Tuple
from src.pipeline import Pipeline, PipelineContext
from src.manager import DataManager, StateManager
from src.downloadStep import DownloadStep
from src.transcribeStep import TranscribeStep
from src.notesStep import NotesStep
from src.imageStep import ImageStep
from src.latexStep import LatexStep
from src.pdfStep import PdfStep
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def load_config() -> dict:
    """Load configuration from config.yaml."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clear_temp(data_manager: DataManager, id: int) -> None:
    """Clear data/temp/ for the given id before starting a run."""
    data_manager.clear_temp(id)

def prompt_cleanup(data_manager: DataManager, context: PipelineContext, input_data: str) -> None:
    """Prompt user to delete temp files for a specific id."""
    id = context.metadata["id"]
    response = input(f"Keep temp files for {input_data} (data/temp/{id:03d}_*)? [y/N]: ").strip().lower()
    if response != "y":
        data_manager.clear_temp(id)
        logger.info(f"Deleted temp files for id {id:03d}")

def prompt_batch_cleanup(data_manager: DataManager) -> None:
    """Prompt user to delete all temp files after batch processing, with safety checks and logging."""
    temp_dir = data_manager.temp_dir.resolve()
    assert "temp" in str(temp_dir), f"Refusing to delete non-temp directory: {temp_dir}!"
    files_to_delete = list(temp_dir.glob("*"))
    dirs_to_delete = [f for f in files_to_delete if f.is_dir()]
    files_to_delete = [f for f in files_to_delete if f.is_file()]
    if not files_to_delete and not dirs_to_delete:
        print(f"No temp files to delete in {temp_dir}.")
        return
    print("The following temp files and directories will be deleted if you confirm:")
    for d in dirs_to_delete:
        print(f"  DIR: {d}")
    for f in files_to_delete:
        print(f"  FILE: {f}")
    response = input(f"Clear all temp files in {temp_dir}? [y/N]: ").strip().lower()
    if response == "y":
        for d in dirs_to_delete:
            import shutil
            shutil.rmtree(d)
        for f in files_to_delete:
            f.unlink()
        logger.info(f"Cleared all temp files in {temp_dir}")

def process_youtube_url(url: str, config: dict, state_manager: StateManager, data_manager: DataManager) -> bool:
    """Process a single YouTube URL."""
    config["pipeline"]["input_type"] = "youtube_url"
    context = PipelineContext(url)
    context.metadata["id"] = state_manager.get_index(url, "youtube_url")  # Use global id
    pipeline = Pipeline([
        DownloadStep(),
        TranscribeStep(),
        NotesStep(),
        ImageStep(),
        LatexStep(),
        PdfStep()
    ], config=config, state_manager=state_manager)

    clear_temp(data_manager, context.metadata["id"])  # Clear temp with initialized id
    try:
        context = pipeline.run(url)
        pdf_path = context.get_result("PdfStep")
        state_manager.save_success(url, "youtube_url", context.metadata["id"], pdf_path)
        logger.info(f"Final PDF: {pdf_path}")
        if context.metadata.get("image_rate_limited"):
            print("\nWARNING: Google Custom Search API rate limit (429) was hit during image search. The generated PDF will contain only image placeholders instead of real images. You may try again later or use a different API key.\n")
        if (
            context.metadata.get("images_total", 0) > 0
            and context.metadata.get("images_present", 0) < context.metadata.get("images_total", 0)
        ):
            print(f"\nWARNING: Only {context.metadata.get('images_present', 0)} out of {context.metadata.get('images_total', 0)} images were included in the PDF. Some images could not be found and were omitted.\n")
        prompt_cleanup(data_manager, context, url)
        return True
    except Exception as e:
        logger.error(f"Pipeline failed for {url}: {str(e)}")
        state_manager.log_error(url, "youtube_url", context.metadata["id"], pipeline.get_failed_step() or "Pipeline", str(e))
        # Update Init task status to 'failed'
        state_manager.cursor.execute("""
            UPDATE tasks SET status = 'failed'
            WHERE input_data = ? AND input_type = ? AND step_name = 'Init'
        """, (url, "youtube_url"))
        state_manager.conn.commit()
        prompt_cleanup(data_manager, context, url)
        return False

def process_folder(folder_path: str, input_type: str, config: dict, state_manager: StateManager, data_manager: DataManager) -> None:
    """Process a folder of text or video files."""
    config["pipeline"]["input_type"] = "text_file" if input_type == "transcript_folder" else "video_file"
    folder = Path(folder_path)
    if not folder.exists():
        logger.error(f"Folder {folder_path} does not exist")
        return

    extensions = [".txt", ".md"] if input_type == "transcript_folder" else [".mp3", ".mp4"]
    files = sorted([f for f in folder.glob("*") if f.suffix.lower() in extensions])
    if not files:
        logger.error(f"No {input_type} files found in {folder_path}")
        return

    failures: List[Tuple[int, str, str, str]] = []
    # Clear all temp before batch, using a dummy id (will be overridden per file)
    clear_temp(data_manager, 0)  # 0 as placeholder, actual cleanup per file

    for file in files:
        input_data = str(file)
        context = PipelineContext(input_data)
        context.metadata["id"] = state_manager.get_index(input_data, config["pipeline"]["input_type"])
        # If this is a transcript file, set the transcript path for NotesStep
        if input_type == "transcript_folder":
            context.set_result("TranscribeStep", input_data)
        pipeline_steps = (
            [NotesStep(), ImageStep(), LatexStep(), PdfStep()] if input_type == "transcript_folder"
            else [TranscribeStep(), NotesStep(), ImageStep(), LatexStep(), PdfStep()]
        )
        pipeline = Pipeline(pipeline_steps, config=config, state_manager=state_manager)

        try:
            context = pipeline.run(input_data)
            pdf_path = context.get_result("PdfStep")
            state_manager.save_success(input_data, config["pipeline"]["input_type"], context.metadata["id"], pdf_path)
            logger.info(f"Final PDF: {pdf_path}")
            if context.metadata.get("image_rate_limited"):
                print("\nWARNING: Google Custom Search API rate limit (429) was hit during image search. The generated PDF will contain only image placeholders instead of real images. You may try again later or use a different API key.\n")
            if (
                context.metadata.get("images_total", 0) > 0
                and context.metadata.get("images_present", 0) < context.metadata.get("images_total", 0)
            ):
                print(f"\nWARNING: Only {context.metadata.get('images_present', 0)} out of {context.metadata.get('images_total', 0)} images were included in the PDF. Some images could not be found and were omitted.\n")
            prompt_cleanup(data_manager, context, file.name)
        except Exception as e:
            failed_step = pipeline.get_failed_step() or "Unknown"
            state_manager.log_error(input_data, config["pipeline"]["input_type"], context.metadata["id"], failed_step, str(e))
            failures.append((context.metadata["id"], input_data, failed_step, str(e)))
            prompt_cleanup(data_manager, context, file.name)

    if failures:
        logger.error(f"Pipeline failed for {len(failures)} files:")
        for id, input_data, failed_step, error in failures:
            logger.error(f"- {Path(input_data).name} (id {id:03d}): {failed_step} ({error})")
        while failures:
            response = input("Retry failed files? [y/N]: ").strip().lower()
            if response != "y":
                break
            new_failures = []
            for id, input_data, failed_step, _ in failures:
                context = PipelineContext(input_data)
                context.metadata["id"] = id
                # If this is a transcript file, set the transcript path for NotesStep
                if input_type == "transcript_folder":
                    context.set_result("TranscribeStep", input_data)
                pipeline_steps = (
                    [NotesStep(), ImageStep(), LatexStep(), PdfStep()] if input_type == "transcript_folder"
                    else [TranscribeStep(), NotesStep(), ImageStep(), LatexStep(), PdfStep()]
                )
                try:
                    start_idx = next(i for i, s in enumerate(pipeline_steps) if s.__class__.__name__ == failed_step)
                    pipeline = Pipeline(pipeline_steps[start_idx:], config=config, state_manager=state_manager)
                    if start_idx > 0:
                        prev_step = pipeline_steps[start_idx - 1]
                        try:
                            context.set_result(
                                prev_step.__class__.__name__,
                                data_manager.load_temp(context.metadata["id"], 
                                                    prev_step.__class__.__name__.lower().replace("step", ""),
                                                    "md" if prev_step.__class__.__name__ in ["NotesStep", "ImageStep"] else "txt")
                            )
                        except FileNotFoundError:
                            logger.warning(f"No temp file for {input_data} at {failed_step}, restarting from beginning")
                            pipeline = Pipeline(pipeline_steps, config=config, state_manager=state_manager)
                    context = pipeline.run(input_data)
                    pdf_path = context.get_result("PdfStep")
                    state_manager.save_success(input_data, config["pipeline"]["input_type"], id, pdf_path)
                    logger.info(f"Final PDF: {pdf_path}")
                    prompt_cleanup(data_manager, context, Path(input_data).name)
                except Exception as e:
                    new_failed_step = pipeline.get_failed_step() or "Unknown"
                    state_manager.log_error(input_data, config["pipeline"]["input_type"], id, new_failed_step, str(e))
                    new_failures.append((id, input_data, new_failed_step, str(e)))
            failures = new_failures
            if failures:
                logger.error(f"Retry failed for {len(failures)} files:")
                for id, input_data, failed_step, error in failures:
                    logger.error(f"- {Path(input_data).name} (id {id:03d}): {failed_step} ({error})")

    prompt_batch_cleanup(data_manager)

def process_mixed_folder(folder_path: str, config: dict, state_manager: StateManager, data_manager: DataManager) -> None:
    """Process a folder of mixed files (.txt, .md, .mp3, .mp4) and save PDFs in data/pdf/."""
    folder = Path(folder_path)
    output_dir = Path("data/pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not folder.exists():
        logger.error(f"Folder {folder_path} does not exist")
        return
    supported_exts = {".txt", ".md", ".mp3", ".mp4"}
    files = sorted([f for f in folder.glob("*") if f.suffix.lower() in supported_exts])
    if not files:
        logger.error(f"No supported files found in {folder_path}")
        return
    results = []
    failures = []
    for idx, file in enumerate(files, 1):
        print(f"###### PROCESSING INPUT {idx}/{len(files)}: {file.name.upper()} ######")
        print(f"======================================================================")
        ext = file.suffix.lower()
        input_data = str(file)
        context = PipelineContext(input_data)
        context.metadata["id"] = state_manager.get_index(input_data, ext)
        # Decide pipeline steps
        if ext in {".txt", ".md"}:
            context.set_result("TranscribeStep", input_data)
            steps = [NotesStep(), ImageStep(), LatexStep(), PdfStep()]
            config["pipeline"]["input_type"] = "text_file"
        elif ext == ".mp3":
            context.set_result("DownloadStep", input_data)  # Directly set audio file for TranscribeStep
            steps = [TranscribeStep(), NotesStep(), ImageStep(), LatexStep(), PdfStep()]
            config["pipeline"]["input_type"] = "video_file"
        elif ext == ".mp4":
            # Run DownloadStep to extract audio from video before transcription
            steps = [DownloadStep(), TranscribeStep(), NotesStep(), ImageStep(), LatexStep(), PdfStep()]
            config["pipeline"]["input_type"] = "video_file"
        else:
            logger.warning(f"Skipping unsupported file: {file.name}")
            continue
        pipeline = Pipeline(steps, config=config, state_manager=state_manager)
        try:
            context = pipeline.run(input_data, context=context)
            pdf_path = context.get_result("PdfStep")
            if pdf_path and os.path.exists(pdf_path):
                # Only add to results if PDF is in canonical output dir
                out_pdf = Path(pdf_path)
                results.append((file.name, str(out_pdf)))
                logger.info(f"Generated PDF for {file.name}: {out_pdf}")
            else:
                failures.append((file.name, "No PDF generated"))
                logger.error(f"Failed to generate PDF for {file.name}")
            if context.metadata.get("image_rate_limited"):
                print("\nWARNING: Google Custom Search API rate limit (429) was hit during image search. The generated PDF will contain only image placeholders instead of real images. You may try again later or use a different API key.\n")
            if (
                context.metadata.get("images_total", 0) > 0
                and context.metadata.get("images_present", 0) < context.metadata.get("images_total", 0)
            ):
                print(f"\nWARNING: Only {context.metadata.get('images_present', 0)} out of {context.metadata.get('images_total', 0)} images were included in the PDF. Some images could not be found and were omitted.\n")
        except Exception as e:
            failures.append((file.name, str(e)))
            logger.error(f"Pipeline failed for {file.name}: {str(e)}")
    # Print summary
    print("\n=== Processing Summary ===")
    for name, pdf in results:
        print(f"SUCCESS: {name} -> {pdf}")
    for name, err in failures:
        print(f"FAILED:  {name} -> {err}")
    # Prompt to rerun failed files
    if failures:
        response = input("\nRerun failed files? [y/N]: ").strip().lower()
        if response == "y":
            for name, _ in failures:
                file = folder / name
                ext = file.suffix.lower()
                input_data = str(file)
                context = PipelineContext(input_data)
                context.metadata["id"] = state_manager.get_index(input_data, ext)
                if ext in {".txt", ".md"}:
                    context.set_result("TranscribeStep", input_data)
                    steps = [NotesStep(), ImageStep(), LatexStep(), PdfStep()]
                    config["pipeline"]["input_type"] = "text_file"
                elif ext in {".mp3", ".mp4"}:
                    steps = [TranscribeStep(), NotesStep(), ImageStep(), LatexStep(), PdfStep()]
                    config["pipeline"]["input_type"] = "video_file"
                else:
                    continue
                pipeline = Pipeline(steps, config=config, state_manager=state_manager)
                try:
                    context = pipeline.run(input_data, context=context)
                    pdf_path = context.get_result("PdfStep")
                    if pdf_path and os.path.exists(pdf_path):
                        out_pdf = output_dir / (file.stem + ".pdf")
                        if Path(pdf_path).resolve() != out_pdf.resolve():
                            import shutil
                            shutil.copy2(pdf_path, out_pdf)
                        print(f"RETRY SUCCESS: {name} -> {out_pdf}")
                    else:
                        print(f"RETRY FAILED:  {name} -> No PDF generated")
                except Exception as e:
                    print(f"RETRY FAILED:  {name} -> {str(e)}")
    print(f"\nAll PDFs are saved in: {output_dir.resolve()}")
    prompt_batch_cleanup(data_manager)

def main():
    """Main CLI for video-to-pdf conversion."""
    config = load_config()
    data_manager = DataManager(config)
    state_manager = StateManager(config["pipeline"]["db_path"])

    while True:
        print("What do you want to do?")
        print("1. Convert YouTube URL to PDF")
        print("2. Convert a folder of files (.txt/.md/.mp3/.mp4) to PDFs")
        print("3. Exit")
        choice = input("Enter choice (1-3): ").strip()

        if choice == "1":
            url = input("Enter YouTube URL: ").strip()
            process_youtube_url(url, config, state_manager, data_manager)
        elif choice == "2":
            folder_path = input("Enter folder path: ").strip()
            process_mixed_folder(folder_path, config, state_manager, data_manager)
        elif choice == "3":
            print("Exiting. Goodbye!")
            break
        else:
            logger.error("Invalid choice. Please enter 1, 2, or 3.")

    state_manager.close()

if __name__ == "__main__":
    main()