# YouTube to PDF Lecture Notes Converter (Conda Setup)

This project converts YouTube lecture videos into professionally formatted PDF notes. It transcribes the video, generates structured Markdown notes, embeds relevant images, converts notes to LaTeX, and compiles them into a PDF. This guide is for **Windows** users using **Conda** to manage the Python environment. Follow every step precisely to avoid errors. If you’re new to Conda or programming, this guide is designed to get you up and running without excuses.

---

## Prerequisites

You need a Windows 10 or 11 system with internet access and administrative privileges. Below are the required tools, their purpose, and how to verify they’re installed.

### 1. Git

- **Purpose**: Clones the project repository from GitHub.
- **Check**: Open Command Prompt (`cmd`) and run:

  ```
  git --version
  ```

  If not installed, download from [git-scm.com](https://git-scm.com/downloads). During installation:

  - Accept default settings.
  - Choose “Use Git from the Windows Command Prompt.”

- **Pitfall**: Without Git, you can’t clone the repo. Verify it’s in PATH with `git --version`.

### 2. Miniconda or Anaconda

- **Purpose**: Manages Python environments and dependencies.
- **Check**: Run:

  ```
  conda --version
  ```

  If not installed, download **Miniconda** (lighter) from [conda.io](https://conda.io) or Anaconda from [anaconda.com](https://www.anaconda.com). During installation:

  - Check “Add Miniconda to PATH” (optional, but simplifies usage).
  - Choose “Install for all users” to avoid permission issues.

- **Pitfall**: Conda can conflict with existing Python installations. Ensure `conda` commands work in Command Prompt.

### 3. FFmpeg

- **Purpose**: Extracts audio from YouTube videos for transcription.
- **Check**: Run:

  ```
  ffmpeg -version
  ```

  If not installed:

  - Download a Windows build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (e.g., `ffmpeg-release-essentials.zip`).
  - Extract to a folder (e.g., `C:\ffmpeg`).
  - Add the `bin` folder to PATH:
    1. Right-click “This PC” > Properties > Advanced system settings > Environment Variables.
    2. Under “System variables,” edit “Path” > New > Add `C:\ffmpeg\bin`.
  - Verify: Reopen Command Prompt and run `ffmpeg -version`.

- **Pitfall**: If FFmpeg isn’t in PATH, transcription fails silently.

### 4. MiKTeX (LaTeX Distribution)

- **Purpose**: Compiles LaTeX files into PDFs.
- **Check**: Run:

  ```
  pdflatex --version
  latexmk --version
  ```

  If not installed:

  - Download MiKTeX from [miktex.org](https://miktex.org/download).
  - Install for “Anyone who uses this computer.”
  - Open MiKTeX Console (search in Start menu) and click “Updates” > “Update now.”
  - In MiKTeX Console, go to Packages tab and install:

    ```
    geometry graphicx amsmath enumitem hyperref parskip tikz eso-pic
    ```

  - Add MiKTeX’s `bin` folder to PATH (e.g., `C:\Program Files\MiKTeX 2.9\miktex\bin\x64`).
  - Verify: Run `pdflatex --version` and `latexmk --version`.

- **Pitfall**: MiKTeX may prompt to install missing packages on first run—allow it. Admin rights are required.

### 5. API Keys

- **Purpose**: Enables transcription, note generation, and image search.
- **Required Keys**:
  - **AssemblyAI**: For video transcription. Sign up at [assembly.ai](https://www.assembly.ai/) and get an API key.
  - **OpenRouter**: For note and LaTeX generation. Sign up at [openrouter.ai](https://openrouter.ai/) and get an API key.
  - **Google API & CSE ID**: For image search. In [Google Cloud Console](https://console.cloud.google.com/):
    - Create a project.
    - Enable “Custom Search API.”
    - Generate an API key.
    - Create a Programmable Search Engine at [cse.google.com](https://cse.google.com/) to get a CSE ID.
- **Pitfall**: Incorrect keys cause pipeline failures. Monitor API quotas (e.g., Google CSE has a 100-query daily free limit).

## Setup Instructions

Follow these steps in Command Prompt (`cmd`). Run as Administrator if you hit permission issues. Commands assume you’re using Conda.

### 1. Clone the Repository

1. Open Command Prompt.
2. Navigate to your desired project folder:

   ```
   cd C:\Users\YourUsername\Documents
   ```

3. Clone the repo:

   ```
   git clone https://github.com/sachinkry/yt_url2pdf.git
   ```

4. Enter the project directory:

   ```
   cd yt_url2pdf
   ```

### 2. Set Up Conda Environment

1. Create a Conda environment with Python 3.10:

   ```
   conda create -n yt2pdf python=3.10
   ```

2. Activate the environment:

   ```
   conda activate yt2pdf
   ```

   You’ll see `(yt2pdf)` in your prompt.

3. Install pip in the Conda environment (needed for some packages):

   ```
   conda install pip
   ```

### 3. Install Python Dependencies

1. Install most dependencies via Conda for better compatibility:

   ```
   conda install annotated-types anyio cachetools certifi charset-normalizer distro google-auth httpx idna openai pydantic python-dotenv requests tqdm urllib3
   ```

2. Install remaining dependencies via pip (not all are available in Conda):

   ```
   pip install jiter==0.10.0 pyasn1==0.6.1 pyasn1_modules==0.4.2 pydantic_core==2.33.2 typing-inspection==0.4.1 typing_extensions==4.14.0 websockets==15.0.1 yt-dlp
   ```

   - **Note**: `yt-dlp==2025.6.9` may not exist (future version). If it fails, edit `requirements.txt` to:

     ```
     yt-dlp
     ```

     Then run:

     ```
     pip install yt-dlp
     ```

3. Install `Pillow` (for image processing):

   ```
   conda install pillow
   ```

4. If any package fails, try:
   - `pip install <package>` for specific packages.
   - Install Visual Studio Build Tools if C++ errors occur (rare with Conda).

### 4. Install FFmpeg

1. Download and extract FFmpeg as described in Prerequisites.
2. Add `C:\ffmpeg\bin` to PATH.
3. Verify:

   ```
   ffmpeg -version
   ```

### 5. Install MiKTeX

1. Install MiKTeX as described in Prerequisites.
2. Update MiKTeX and install required packages via MiKTeX Console.
3. Verify:

   ```
   pdflatex --version
   latexmk --version
   ```

### 6. Configure API Keys

1. Copy the example environment file:

   ```
   copy .env.example .env
   ```

2. Create `.env` in the root folder of this project and add your API keys:

   ```
   ASSEMBLYAI_API_KEY=your_assemblyai_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   GOOGLE_CSE_ID=your_google_cse_id
   GOOGLE_API_KEY=your_google_api_key
   ```

3. Save and close `.env`.

---

## Running the Project

1. **Activate Conda Environment**:

   ```
   conda activate yt2pdf
   ```

2. **Run the Pipeline**:

   - Provide a YouTube URL. Example:

     ```
     python main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
     ```

   - The pipeline will:
     - Transcribe the video (YouTube captions or AssemblyAI).
     - Generate Markdown notes with image tags.
     - Embed images via Google CSE.
     - Convert notes to LaTeX.
     - Compile LaTeX to PDF.
     - Prompt to delete intermediate files (type `y` to clean up).

3. **Check Output**:

   - Find the PDF in `data/pdf/` (e.g., `001_video.pdf`).
   - Open it to verify content quality.

---

## Troubleshooting

If errors occur, check these common issues:

- **Conda Environment Issues**:
  - Ensure you’re in the `yt2pdf` environment: `conda activate yt2pdf`.
  - If packages fail, try `pip install <package>` or update Conda: `conda update conda`.
- **Transcription Fails**:
  - Verify AssemblyAI API key in `.env`.
  - Ensure FFmpeg is in PATH (`ffmpeg -version`).
  - Check `data/videos/` for downloaded audio.
- **Image Embedding Fails**:
  - Confirm Google API/CSE keys and quotas.
  - Check `data/images/` for images.
- **LaTeX Compilation Fails**:
  - Open `data/pdf/*.log` for errors (e.g., missing packages).
  - Install missing MiKTeX packages via MiKTeX Console.
  - Check for table overflows or wide content.
- **General Errors**:
  - Read Command Prompt logs.
  - Ensure all prerequisites are installed.
  - Test with a short video (5 minutes) first.
- **Still Stuck?**:
  - Copy the exact error message and ask ChatGPT:
    - Error log.
    - Steps followed.
    - Setup details (Conda version, Python version, MiKTeX version).

---

## Tips for Success

- **Test First**: Use a short YouTube video to validate the pipeline before processing long lectures.
- **Monitor API Costs**: AssemblyAI, OpenRouter, and Google APIs may incur charges. Check usage dashboards.
- **Keep PATH Clean**: Ensure FFmpeg and MiKTeX are accessible via PATH.
- **Backup** `.env`: Store API keys securely; don’t share `.env`.
- **Clean Up**: Delete intermediate files (type `y` at the prompt) to save disk space.
- **Conda Tips**:
  - Update Conda regularly: `conda update -n base conda`.
  - If dependency conflicts arise, recreate the environment: `conda env remove -n yt2pdf`, then repeat setup.

---

## Project Structure

- `main.py`: Orchestrates the pipeline.
- `src/`:
  - `transcribe.py`: Transcribes videos.
  - `notes_generator.py`: Creates Markdown notes.
  - `image_embedder.py`: Adds images to notes.
  - `latex_generator.py`: Converts Markdown to LaTeX.
  - `pdf_generator.py`: Compiles LaTeX to PDF.
- `data/`: Stores videos, transcripts, notes, images, LaTeX, and PDFs.
- `.env`: Contains API keys (never commit to Git).
- `requirements.txt`: Lists Python dependencies (used as reference).

---
