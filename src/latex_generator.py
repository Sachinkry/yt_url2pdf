import os
import json
import logging
import requests
import re
import time
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_api_key():
    """Load OpenRouter API key from .env file."""
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OpenRouter API key not found in .env file")
        raise ValueError("OpenRouter API key not found")
    return api_key

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

def save_latex_file(content: str, latex_path: str):
    """Save LaTeX file."""
    try:
        Path(latex_path).parent.mkdir(parents=True, exist_ok=True)
        with open(latex_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved LaTeX file to {latex_path}")
    except Exception as e:
        logger.error(f"Failed to save LaTeX file: {str(e)}")
        raise

def get_latex_path(index: int) -> str:
    """Generate LaTeX file path using the index."""
    return f"data/latex/{index:03d}_latex.tex"

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

def update_mapping_file(mapping: dict, input_path: str, latex_path: str):
    """Update the JSON mapping file with LaTeX path."""
    mapping_file = 'data/video_transcript_map.json'
    try:
        if input_path in mapping:
            mapping[input_path]['latex_path'] = latex_path
            Path(mapping_file).parent.mkdir(parents=True, exist_ok=True)
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2)
            logger.info(f"Updated mapping file with LaTeX path: {latex_path}")
    except Exception as e:
        logger.error(f"Failed to update mapping file: {str(e)}")
        raise

def extract_latex(raw: str) -> str:
    """Extract LaTeX content between \documentclass and \end{document}."""
    start = raw.find(r'\documentclass')
    end = raw.rfind(r'\end{document}')
    if start == -1 or end == -1:
        return ""
    return raw[start:end + len(r'\end{document}')]

def validate_latex(content: str) -> bool:
    """Validate LaTeX content for minimal structure."""
    try:
        # Check for \documentclass and \end{document}
        if not re.search(r'\\documentclass\{.*?\}', content, re.DOTALL):
            logger.warning("LaTeX missing \\documentclass")
            return False
        if not re.search(r'\\end\{document\}', content, re.DOTALL):
            logger.warning("LaTeX missing \\end{document}")
            return False
        # Check for \begin{document}
        if not re.search(r'\\begin\{document\}', content, re.DOTALL):
            logger.warning("LaTeX missing \\begin{document}")
            return False
        # Warn if graphicx is missing
        if not re.search(r'\\usepackage\{graphicx\}', content, re.DOTALL):
            logger.warning("LaTeX missing \\usepackage{graphicx}")
        return True
    except Exception as e:
        logger.error(f"Failed to validate LaTeX: {str(e)}")
        return False

def insert_logo_code(content: str) -> str:
    """Insert logo code before \begin{document} in LaTeX content."""
    logo_code = r"""
\usepackage{tikz}
\usepackage{eso-pic}
\AddToShipoutPictureBG{%
  \begin{tikzpicture}[remember picture,overlay]
    \node[anchor=north east,inner sep=15pt] at (current page.north east)
      {\includegraphics[width=2cm]{data/images/logo.png}};
  \end{tikzpicture}
}
""".strip()

    if r'\begin{document}' not in content:
        raise ValueError(r"\begin{document} not found in LaTeX content.")

    return content.replace(r'\begin{document}', logo_code + '\n' + r'\begin{document}', 1)

def convert_md_to_latex(md_path: str, index: int, model: str = "anthropic/claude-opus-4", max_retries: int = 2) -> str:
    """Convert Markdown to LaTeX using OpenRouter API with retries."""
    start_time = time.time()
    try:
        # Load API key and Markdown content
        api_key = load_api_key()
        md_content = load_markdown_file(md_path)
        mapping = load_mapping_file()
        
        # Find input_path for this Markdown file
        input_path = next((k for k, v in mapping.items() if v.get('notes_img_path') == md_path), None)
        if not input_path:
            logger.error(f"No mapping found for Markdown file {md_path}")
            raise ValueError(f"No mapping found for Markdown file {md_path}")

        # Custom prompt for LaTeX conversion
        prompt = r"""
        You are a LaTeX expert. Convert the following Markdown file into a complete LaTeX document while preserving 100% of the original content — not just structure, but also all explanatory text, paragraph descriptions, labels, and detailed information. DO NOT summarize, skip, or simplify.

        Use the following transformation rules:

        1. `##` headers → `\section*{}` unless it’s the title (use `\title{}`).
        2. `###` headers → `\subsection*{}`.
        3. Convert paragraphs between headers and bullet points into full text paragraphs in LaTeX.
        4. Convert bullet points (`*`) into `\item` within a single `\begin{itemize}` block per list.
        - Sub-bullets are allowed **only one level deep** using a nested `itemize`.
        - Flatten if more than one level is attempted.
        5. DO NOT OMIT ANY PARAGRAPH TEXT. Preserve the full narrative, definitions, and examples exactly as they appear. This includes any explanation under headings, in bullets, or between elements.
        6. Render images using the LaTeX `figure` environment:
        - Center using `\centering`.
        - Use `\includegraphics[width=0.8\textwidth]{relative/path/to/image}`.
        - Add a `\caption{...}` and `\label{fig:...}` using the filename (minus extension) as the label ID.
        7. Emphasize:
        - Bold markdown (`**`) → `\textbf{}`.
        - Inline code or technical terms → `\texttt{}`.
        8. Convert numbered steps into `enumerate` environment, using `\item` per step.
        9. Escape all special LaTeX characters like `%`, `$`, `#`, `_`, `&`, `^`, `{`, and `}`.
        10. Output a full LaTeX document:
        - Start with `\documentclass{article}`, include `inputenc`, `graphicx`, `geometry`, `amsmath`, `hyperref`, `enumitem`, and `parskip`.
        - Use `\title{}` and `\maketitle` for the title.
        - Maintain consistent indentation and structure.
        - **Nesting level should be equal to 2.**

        Ultimate rule: **Do not drop a single piece of information or explanation — ever.** Your goal is fidelity.

        ---

        Now convert the following markdown content to LaTeX starting with `\documentclass{article}` and ending with `\end{document}`:

        """

        latex_content = None
        for attempt in range(1, max_retries + 1):
            try:
                # Call OpenRouter API
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": md_content}
                    ],
                    "max_tokens": 10000  # Increased to handle long outputs
                }
                response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                raw_content = response.json()["choices"][0]["message"]["content"]
                
                # Extract LaTeX content
                latex_content = extract_latex(raw_content)
                if not latex_content:
                    logger.warning(f"Attempt {attempt} failed: No valid LaTeX extracted")
                    if attempt < max_retries:
                        time.sleep(2)
                    continue
                
                # Validate LaTeX
                if validate_latex(latex_content):
                    break
                else:
                    logger.warning(f"Attempt {attempt} failed: Invalid LaTeX structure")
                    if attempt < max_retries:
                        time.sleep(2)
            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {str(e)}")
                if attempt < max_retries:
                    time.sleep(2)
            
            if attempt == max_retries:
                logger.error(f"Failed to convert Markdown to LaTeX after {max_retries} attempts")
                raise ValueError(f"Failed to generate valid LaTeX after {max_retries} attempts")
        
        # Insert logo before saving
        # TODO: uncomment this later
        latex_content = insert_logo_code(latex_content)

        # Save LaTeX file
        latex_path = get_latex_path(index)
        save_latex_file(latex_content, latex_path)
        
        # Update JSON mapping
        update_mapping_file(mapping, input_path, latex_path)
        
        elapsed_time = time.time() - start_time
        logger.info(f"*** LaTeX conversion took {elapsed_time:.2f} seconds ***")
        return latex_path
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.info(f"LaTeX conversion (failed) took {elapsed_time:.2f} seconds ***")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python latex_generator.py <markdown_path>")
        sys.exit(1)

    notes_img_path = sys.argv[1]
    # Extract numeric prefix from file name like '010_transcript.txt'
    try:
        filename = Path(notes_img_path).name
        index = int(filename.split('_')[0])
    except Exception as e:
        print(f"Error extracting index from file name '{filename}': {str(e)}")
        sys.exit(1)

    # Note: CLI usage doesn't provide an index, so this will fail in the streamlined pipeline
    # This is fine for standalone testing but will need to be handled in yt_to_pdf.py
    convert_md_to_latex(notes_img_path, index)  # Temporary index for standalone testing