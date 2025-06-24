import logging
import os
import subprocess
import time
from typing import Dict
from pathlib import Path

from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager

logger = logging.getLogger(__name__)

class PdfStep(ProcessingStep):
    """Compiles LaTeX notes to PDF using latexmk with pdflatex."""

    def __init__(self):
        self.max_retries = 3

    def _check_latex_distribution(self) -> bool:
        """Check if pdflatex and latexmk are available."""
        try:
            subprocess.run(["pdflatex", "--version"], check=True, capture_output=True, text=True)
            subprocess.run(["latexmk", "--version"], check=True, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("pdflatex or latexmk not found. Install BasicTeX with: brew install basictex")
            return False

    def _compile_latex(self, tex_path: str, output_dir: Path, pdf_path: Path) -> bytes:
        """Compile LaTeX file to PDF using latexmk with retries."""
        tex_dir = Path(tex_path).resolve().parent  # Resolve to absolute path
        logger.info(f"Compiling from resolved tex_dir: {tex_dir}")
        actual_pdf_name = f"{Path(tex_path).stem}.pdf"  # e.g., 002_latex.pdf
        actual_pdf_path = tex_dir / actual_pdf_name

        for attempt in range(1, self.max_retries + 1):
            try:
                if not os.path.exists(tex_path):
                    logger.error(f"TeX file not found at {tex_path} before compilation")
                    raise FileNotFoundError(f"TeX file not found at {tex_path}")
                
                text_filename = Path(tex_path).name
                latexmk_cmd = [
                    "latexmk",
                    "-pdf",
                    "-pdflatex=pdflatex",
                    "-interaction=nonstopmode",
                    f"-outdir={tex_dir}",
                    text_filename
                ]
                logger.info(f"Running latexmk with cmd: {latexmk_cmd}")
                result = subprocess.run(latexmk_cmd, check=True, capture_output=True, text=True, cwd=tex_dir)
                logger.info(f"Ran latexmk for {tex_path}")
                logger.debug(f"latexmk stdout: {result.stdout}")

                if not actual_pdf_path.exists():
                    logger.error(f"PDF {actual_pdf_path} was not created")
                    log_path = tex_dir / f"{Path(tex_path).stem}.log"
                    if log_path.exists():
                        with open(log_path, "r", encoding="utf-8") as f:
                            log_content = f.read()
                            logger.error(f"LaTeX compilation log:\n{log_content}")
                            if "Overfull \\hbox" in log_content:
                                logger.warning("Table or content may be too wide. Adjust table widths or margins.")
                    raise FileNotFoundError(f"PDF {actual_pdf_path} was not created")

                with open(actual_pdf_path, "rb") as f:
                    pdf_content = f.read()

                output_dir.mkdir(parents=True, exist_ok=True)
                os.rename(actual_pdf_path, pdf_path)
                logger.info(f"Renamed {actual_pdf_path} to {pdf_path}")

                clean_cmd = ["latexmk", "-c", f"-outdir={tex_dir}", text_filename]
                subprocess.run(clean_cmd, check=True, capture_output=True, text=True, cwd=tex_dir)
                logger.info(f"Cleaned auxiliary files for {tex_path}")

                if not pdf_path.exists():
                    logger.error(f"Renamed PDF {pdf_path} does not exist after renaming")
                    raise FileNotFoundError(f"Renamed PDF {pdf_path} does not exist")
                return pdf_content

            except subprocess.CalledProcessError as e:
                logger.error(f"Attempt {attempt} failed: latexmk error: {e.stderr}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying compilation (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(2)
                else:
                    raise
            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {str(e)}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying compilation (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(2)
                else:
                    raise

    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        """Compile LaTeX notes to PDF."""
        # Load LaTeX from context, not temp file
        latex_content = context.get_result("LatexStep")
        if not latex_content:
            logger.error(f"No LaTeX content available in context for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"No LaTeX content available for {self.name}")
        # If latex_content is a file path, read it (for backward compatibility)
        if os.path.exists(str(latex_content)):
            with open(latex_content, 'r', encoding='utf-8') as f:
                latex_content = f.read()
        if not latex_content.strip():
            logger.error(f"LaTeX content is empty for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"LaTeX content is empty for {self.name}")
        # Save LaTeX to a temp file for compilation
        data_manager = DataManager(config)
        tex_path = data_manager.save_temp(context.metadata["id"], "latex", "tex", latex_content)
        # Compile LaTeX to PDF as before
        output_dir = Path(config["pipeline"]["output_dir"]).resolve() / "doc"  # temp/intermediate only
        pdf_path = output_dir / f"{context.metadata['id']:03d}_notes.pdf"
        pdf_content = self._compile_latex(tex_path, output_dir, pdf_path)
        # Save final PDF only in canonical pdf_dir
        # saved_pdf_path = data_manager.save_pdf(context.metadata["id"], config["pipeline"]["input_type"], pdf_content)
        input_stem = Path(context.input_data).stem
        saved_pdf_path = data_manager.save_pdf(input_stem, pdf_content)
        state_manager.save_success(
            input_data=context.input_data,
            input_type=config["pipeline"]["input_type"],
            id=context.metadata["id"],
            pdf_path=saved_pdf_path
        )
        context.set_result(self.name, saved_pdf_path)
        logger.info(f"Generated PDF at {saved_pdf_path}")
        return context