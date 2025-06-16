import logging
import time
import shutil
import sys
import json
from pathlib import Path
from src.transcribe import transcribe_video
from src.notes_generator import generate_lecture_notes
from src.image_embedder import embed_images_in_markdown
from src.latex_generator import convert_md_to_latex
from src.pdf_generator import compile_latex_to_pdf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def prompt_cleanup(url: str, index: int, pdf_path: str) -> None:
    """Prompt the user to decide on keeping or deleting intermediate files and mapping entry."""
    intermediate_dirs = [
        f"data/transcripts/{index:03d}_transcript.txt",
        f"data/notes/{index:03d}_notes.md",
        f"data/notes_img/{index:03d}_notes_img.md",
        f"data/latex/{index:03d}_latex.tex",
        f"data/images/{index:03d}_notes_img",
        "data/temp"
    ]
    mapping_file = "data/video_transcript_map.json"

    print("\nPipeline completed successfully!")
    print(f"Generated PDF: {pdf_path}")
    print("\nIntermediate files generated during the process:")
    for path in intermediate_dirs:
        if Path(path).exists():
            print(f"- {path}")
    if Path(mapping_file).exists():
        print(f"- {mapping_file}")

    while True:
        response = input("\nDo you want to DELETE intermediate files?[Recommended: y] (y/n): ").strip().lower()
        if response in ['y', 'n']:
            break
        print("Please enter 'y' for yes or 'n' for no.")

    if response == 'y':
        # Load the mapping file
        mapping = {}
        if Path(mapping_file).exists():
            try:
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load mapping file {mapping_file}: {str(e)}")
                mapping = {}

        # Remove the entry for the URL
        if url in mapping:
            del mapping[url]
            logger.info(f"Removed mapping entry for URL: {url}")

        # Save the updated mapping file or delete it if empty
        try:
            if mapping:
                with open(mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, indent=2)
                logger.info(f"Updated mapping file: {mapping_file}")
            else:
                if Path(mapping_file).exists():
                    Path(mapping_file).unlink()
                    logger.info(f"Deleted mapping file {mapping_file} as it became empty")
        except Exception as e:
            logger.error(f"Failed to update/delete mapping file {mapping_file}: {str(e)}")

        # Delete intermediate files
        for path in intermediate_dirs:
            try:
                path_obj = Path(path)
                if path_obj.exists():
                    if path_obj.is_dir():
                        shutil.rmtree(path_obj)
                        logger.info(f"Deleted directory: {path}")
                    else:
                        path_obj.unlink()
                        logger.info(f"Deleted file: {path}")
            except Exception as e:
                logger.error(f"Failed to delete {path}: {str(e)}")



def main(url: str) -> None:
    """Main function to orchestrate the video-to-PDF pipeline."""
    total_start_time = time.time()
    try:
        # Step 1: Transcribe the video
        logger.info("### STARTING TRANSCRIPTION...")
        transcript, transcript_path, index = transcribe_video(url)

        # Step 2: Generate lecture notes
        logger.info("### GENERATING LECTURE NOTES...")
        notes, notes_path = generate_lecture_notes(transcript_path, index)

        # Step 3: Embed images in the Markdown file
        logger.info("### EMBEDDING IMAGES IN MARKDOWN FILE...")
        notes_img_path = embed_images_in_markdown(notes_path, index)

        # Step 4: Convert Markdown to LaTeX
        logger.info("### CONVERTING MARKDOWN TO LaTeX...")
        latex_path = convert_md_to_latex(notes_img_path, index)

        # Step 5: Compile LaTeX to PDF
        logger.info("### COMPILING LaTeX to PDF...")
        pdf_path = compile_latex_to_pdf(latex_path, index)

        # Step 6: Prompt for cleanup and remind to check PDF
        prompt_cleanup(url, index, pdf_path)
        print(f"\nPlease check your generated PDF at {pdf_path} to ensure its quality.")

        total_elapsed_time = time.time() - total_start_time
        logger.info(f"#### TOTAL TIME ####: {total_elapsed_time:.2f} seconds")

    except Exception as e:
        total_elapsed_time = time.time() - total_start_time
        logger.error(f"Pipeline failed: {str(e)}")
        logger.info(f"Total pipeline execution (failed) took {total_elapsed_time:.2f} seconds")
        raise

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <youtube_url>")
        sys.exit(1)
    main(sys.argv[1])