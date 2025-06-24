import logging
import re
import os
import time
from typing import Dict, Optional
import requests
from pathlib import Path
from dotenv import load_dotenv

from src.pipeline import ProcessingStep, PipelineContext
from src.manager import DataManager, StateManager

logger = logging.getLogger(__name__)
load_dotenv()

class LatexStep(ProcessingStep):
    """Converts Markdown notes with images to a complete LaTeX document using OpenRouter API."""

    def __init__(self):
        self.api_key = self._load_api_key()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "google/gemini-2.5-pro-preview-05-06"
        self.max_retries = 2
        self.max_tokens = 10000
        self.logo_path = Path("data/logo.png")

    def _load_api_key(self) -> str:
        """Load OpenRouter API key from environment."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("OPENROUTER_API_KEY not found in environment variables")
            raise ValueError("OPENROUTER_API_KEY not found")
        return api_key

    def _validate_latex(self, content: str) -> bool:
        """Validate LaTeX for essential structure."""
        try:
            if not re.search(r'\\documentclass\{.*?\}', content, re.DOTALL):
                logger.warning("LaTeX missing \\documentclass")
                return False
            if not re.search(r'\\begin\{document\}', content, re.DOTALL):
                logger.warning("LaTeX missing \\begin{document}")
                return False
            if not re.search(r'\\end\{document\}', content, re.DOTALL):
                logger.warning("LaTeX missing \\end{document}")
                return False
            if not re.search(r'\\usepackage\{graphicx\}', content, re.DOTALL):
                logger.warning("LaTeX missing \\usepackage{graphicx}")
            return True
        except Exception as e:
            logger.error(f"Failed to validate LaTeX: {str(e)}")
            return False

    def _extract_latex(self, content: str) -> str:
        """Extract LaTeX content between \\documentclass and \\end{document}."""
        start = content.find(r'\documentclass')
        end = content.rfind(r'\end{document}')
        if start == -1 or end == -1:
            logger.warning("No valid LaTeX boundaries found")
            return ""
        return content[start:end + len(r'\end{document}')]

    def _insert_logo_code(self, content: str, tex_dir: Path) -> str:
        """Insert logo code before \\begin{document} using tikz and eso-pic."""
        if not self.logo_path.exists():
            logger.error(f"Logo file {self.logo_path} does not exist")
            raise FileNotFoundError(f"Logo file {self.logo_path} does not exist")

        relative_logo_path = os.path.relpath(self.logo_path, tex_dir)

        logo_code = rf"""
\usepackage{{tikz}}
\usepackage{{eso-pic}}
\AddToShipoutPictureBG{{%
  \begin{{tikzpicture}}[remember picture,overlay]
    \node[anchor=north east,inner sep=15pt] at (current page.north east)
      {{\includegraphics[width=2cm]{{{relative_logo_path}}}}};
  \end{{tikzpicture}}
}}
""".strip()

        if r'\begin{document}' not in content:
            logger.error(r"\begin{document} not found in LaTeX content")
            raise ValueError(r"\begin{document} not found in LaTeX content")

        return content.replace(r'\begin{document}', logo_code + '\n' + r'\begin{document}', 1)

    def escape_latex(self, s):
        """Escape LaTeX special characters in a string."""
        return (s.replace('\\', '\\textbackslash{}')
                 .replace('_', '\\_')
                 .replace('%', '\\%')
                 .replace('$', '\\$')
                 .replace('#', '\\#')
                 .replace('&', '\\&')
                 .replace('{', '\\{')
                 .replace('}', '\\}')
                 .replace('^', '\\^{}')
                 .replace('~', '\\~{}'))

    def sanitize_label(self, s):
        """Sanitize string for use in LaTeX labels (letters, numbers, underscores, hyphens only)."""
        return re.sub(r'[^a-zA-Z0-9_-]', '', s.replace(' ', '_'))

    def _convert_md_to_latex(self, md_content: str, image_dir: Path, index: int) -> str:
        """Convert Markdown to LaTeX using OpenRouter API, using absolute image paths."""
        prompt = rf"""
You are a LaTeX expert tasked with converting a Markdown file into a complete LaTeX document, preserving 100% of the original content, including all explanatory text, paragraphs, labels, detailed information, whitespace, and special characters (e.g., %, $, #, _, &, ^, {{, }}). Do not summarize, skip, simplify, or alter any content—maintain exact fidelity.

Use the following transformation rules:
1. Convert `##` headers to `\section*{{}}` unless it's the first header, which becomes `\title{{}}`.
2. Convert `###` headers to `\subsection*{{}}`.
3. Preserve all paragraphs between headers and bullet points as full text in LaTeX, retaining exact whitespace and line breaks.
4. Convert bullet points (`*`) to `\item` within a single `\begin{{itemize}}` block per list.
   - Allow one level of nested `itemize` for sub-bullets; for deeper nesting (>1 level), flatten into a single `\item` with sub-bullets combined using commas.
5. Preserve all narrative, definitions, examples, and technical terms exactly as they appear, escaping special LaTeX characters.
6. For images (`![alt](images/filename.jpg)` or absolute paths like `![alt](/full/path/filename.jpg)`):
   - Use a `figure` environment with `[htbp]`.
   - Center with `\centering`.
   - Use `\includegraphics[width=0.8\textwidth,height=0.4\textheight,keepaspectratio]{{{image_dir}/filename.jpg}}` where `filename.jpg` is the basename (no path), converting absolute paths to relative paths under `image_dir`.
   - Add `\caption{{alt}}` and `\label{{fig:filename}}` (filename without extension).
   - If an image file is missing or path is invalid, include a placeholder: `\fbox{{Missing Image: filename.jpg}}` with the same caption and label.
7. Convert bold (`**`) to `\textbf{{}}` and inline code/technical terms to `\texttt{{}}`.
8. Convert numbered lists to `\begin{{enumerate}}` with `\item` per step.
9. Escape all special LaTeX characters (%, $, #, _, &, ^, {{, }}) in text automatically.
10. Output a complete LaTeX document:
    - Start with `\documentclass{{article}}`.
    - Include packages: `inputenc`, `graphicx`, `geometry`, `amsmath`, `hyperref`, `enumitem`, `parskip`.
    - Use `\title{{}}` and `\maketitle` for the title.
    - Ensure consistent 2-space indentation and proper nesting.

Ultimate rule: Preserve every character of the input Markdown without loss, handling edge cases (missing images, deep nesting) explicitly.

Example input:
```markdown
## Lecture Title
Introduction text.

## Key Concepts
- **Term**: Definition.
  - Sub-detail.
    - Deep sub-detail.

![Diagram](images/diagram.jpg)
![Missing](nonexistent.jpg)

## Applications
1. Step one.
   - Sub-step.
```

Example output:
```latex
\documentclass{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage{{graphicx}}
\usepackage[
  bottom=2cm,   
  footskip=0.8cm   
]{{geometry}}
\usepackage{{amsmath}}
\usepackage{{hyperref}}
\usepackage{{enumitem}}
\usepackage{{parskip}}
\title{{Lecture Title}}
\begin{{document}}
\maketitle
Introduction text.

\section*{{Key Concepts}}
\begin{{itemize}}
  \item \textbf{{Term}}: Definition.
  \begin{{itemize}}
    \item Sub-detail, Deep sub-detail.
  \end{{itemize}}
\end{{itemize}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.8\textwidth,height=0.4\textheight,keepaspectratio]{{data/temp/001_images/diagram.jpg}}
  \caption{{Diagram}}
  \label{{fig:diagram}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \fbox{{Missing Image: nonexistent.jpg}}
  \caption{{Missing}}
  \label{{fig:nonexistent}}
\end{{figure}}

\section*{{Applications}}
\begin{{enumerate}}
  \item Step one.
  \begin{{itemize}}
    \item Sub-step.
  \end{{itemize}}
\end{{enumerate}}
\end{{document}}
```

Convert the following Markdown content to LaTeX:
{md_content}
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": md_content}
            ],
            "max_tokens": self.max_tokens
        }

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
                api_time = time.time() - start_time
                logger.info(f"OpenRouter API call took {api_time:.2f} seconds for attempt {attempt+1}")
                response.raise_for_status()
                raw_content = response.json()["choices"][0]["message"]["content"]

                # Log the raw LLM response to a file for debugging
                log_dir = Path("data/temp")
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"latex_raw_response_{index}.log"
                with open(log_path, "a", encoding="utf-8") as logf:
                    logf.write("\n" + "="*40 + "\nRAW LLM RESPONSE\n" + "="*40 + "\n")
                    logf.write(raw_content)
                    logf.write("\n" + "="*40 + "\n")
                
                extract_start = time.time()
                latex_content = self._extract_latex(raw_content)
                extract_time = time.time() - extract_start
                logger.info(f"LaTeX extraction took {extract_time:.2f} seconds for attempt {attempt+1}")
                
                if latex_content and self._validate_latex(latex_content):
                    relative_image_dir_name = image_dir.name
                    latex_content = latex_content.replace(str(image_dir), relative_image_dir_name)

                    logo_start = time.time()
                    latex_content = self._insert_logo_code(latex_content, image_dir.parent)
                    logo_time = time.time() - logo_start
                    logger.info(f"Logo insertion took {logo_time:.2f} seconds for attempt {attempt+1}")
                    logger.info(f"Generated LaTeX with {self.model}, attempt {attempt+1}")

                    # After LLM or markdown-to-LaTeX conversion, escape all placeholders and captions, and sanitize labels
                    def escape_missing_image(match):
                        inner = match.group(1)
                        return f"\\fbox{{Missing Image: {self.escape_latex(inner)}}}"
                    def escape_caption(match):
                        inner = match.group(1)
                        return f"\\caption{{{self.escape_latex(inner)}}}"
                    def sanitize_label(match):
                        inner = match.group(1)
                        return f"\\label{{{self.sanitize_label(inner)}}}"
                    latex_content = re.sub(r'\\fbox\{Missing Image: ([^}]*)\}', escape_missing_image, latex_content)
                    latex_content = re.sub(r'\\caption\{([^}]*)\}', escape_caption, latex_content)
                    latex_content = re.sub(r'\\label\{([^}]*)\}', sanitize_label, latex_content)
                    return latex_content
                logger.warning(f"Attempt {attempt+1} failed: Invalid LaTeX structure")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except requests.RequestException as e:
                logger.error(f"Attempt {attempt+1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
        raise ValueError(f"Failed to generate valid LaTeX after {self.max_retries} attempts")

    def _remove_missing_figures(self, latex_content: str, image_dir: Path, context) -> str:
        """Remove figure blocks for images that do not exist in image_dir, or that contain \\fbox{Missing Image: ...}. Count present/missing."""
        # Regex to match LaTeX figure blocks
        figure_pattern = re.compile(
            r"(\\begin\{figure\}\[htbp\].*?\\end\{figure\})",
            re.DOTALL
        )
        present = 0
        missing = 0
        def check_and_keep(match):
            nonlocal present, missing
            figure_block = match.group(1)
            # Remove if it contains \\fbox{Missing Image:
            if '\\fbox{Missing Image:' in figure_block:
                missing += 1
                return ''
            # Otherwise, check for \\includegraphics
            m = re.search(r'\\includegraphics\\[.*?\\]\\{([^}]+)\\}', figure_block)
            if m:
                image_path = m.group(1)
                image_file = Path(image_path)
                if not image_file.is_absolute():
                    full_path = image_dir / image_file.name
                else:
                    full_path = image_file
                if full_path.exists():
                    present += 1
                    return figure_block
                else:
                    missing += 1
                    return ''
            # If no image, keep the block (conservative)
            return figure_block
        new_content = figure_pattern.sub(check_and_keep, latex_content)
        context.metadata["images_present"] = present
        context.metadata["images_missing"] = missing
        context.metadata["images_total"] = present + missing
        return new_content

    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        """Process Markdown notes with images to generate a LaTeX document."""
        data_manager = DataManager(config)
        notes_img_md = context.get_result("ImageStep")
        index = context.metadata["id"]
        pipeline_type = config["pipeline"]["input_type"]

        if not notes_img_md:
            logger.error(f"No notes with images available in context for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"No notes available for {self.name}")
        if os.path.exists(str(notes_img_md)):
            with open(notes_img_md, 'r', encoding='utf-8') as f:
                notes_img_md = f.read()
        if not notes_img_md.strip():
            logger.error(f"Notes with images are empty for {self.name}")
            context.set_result(self.name, None)
            raise ValueError(f"Notes with images are empty for {self.name}")

        # Check for cached output
        existing_output = state_manager.get_step_output(context.input_data, pipeline_type, index, self.name)
        if existing_output and os.path.exists(existing_output) and not config["pipeline"].get("force_reprocess", False):
            logger.info(f"Skipping {self.name} (output exists at {existing_output})")
            context.set_result(self.name, existing_output)
            return context

        try:
            # Load notes with images from context, not temp file
            notes_img_md = context.get_result("ImageStep")
            if not notes_img_md:
                logger.error(f"No notes with images available in context for {self.name}")
                context.set_result(self.name, None)
                raise ValueError(f"No notes available for {self.name}")
            # If notes_img_md is a file path, read it (for backward compatibility)
            if os.path.exists(str(notes_img_md)):
                with open(notes_img_md, 'r', encoding='utf-8') as f:
                    notes_img_md = f.read()
            if not notes_img_md.strip():
                logger.error(f"Notes with images are empty for {self.name}")
                context.set_result(self.name, None)
                raise ValueError(f"Notes with images are empty for {self.name}")
            # Convert Markdown to LaTeX
            image_dir = data_manager.temp_dir / f"{index:03d}_images"
            latex_content = self._convert_md_to_latex(notes_img_md, image_dir, index)
            # Remove figure blocks for missing images, count present/missing
            latex_content = self._remove_missing_figures(latex_content, image_dir, context)
            # Save LaTeX to context
            context.set_result(self.name, latex_content)
            # Optionally, save to temp file for caching/debugging
            output_path = data_manager.save_temp(index, "latex", "tex", latex_content)
            state_manager.save_step_output(
                input_data=context.input_data,
                input_type=pipeline_type,
                id=index,
                step_name=self.name,
                output_path=output_path
            )
            logger.info(f"Generated LaTeX at {output_path}")
            return context

        except Exception as e:
            logger.error(f"Failed to generate LaTeX: {str(e)}")
            state_manager.log_error(context.input_data, pipeline_type, index, self.name, str(e))
            raise