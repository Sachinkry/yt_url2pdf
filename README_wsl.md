# YouTube/Video/Audio/Text to PDF Lecture Notes Converter (WSL/Linux Setup)

This guide is for **Windows users running Ubuntu (or another Linux) via WSL (Windows Subsystem for Linux)**. It will help you set up and run the project in a Linux environment, which is often more reliable for LaTeX and scientific tools.

---

## Prerequisites

You need:

- **Windows 10 or 11** with WSL enabled (see [Microsoft's guide](https://docs.microsoft.com/en-us/windows/wsl/install)).
- **Ubuntu** (or another Linux) installed via WSL (recommended: Ubuntu 20.04 or 22.04).
- **Internet access** and basic familiarity with the Linux terminal.

---

## 1. Update and Install System Dependencies

Open your Ubuntu/WSL terminal and run:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip ffmpeg texlive-full git
```

- This installs Python, pip, venv, FFmpeg, TeX Live (LaTeX), and Git.
- **TeX Live** is the recommended LaTeX distribution for Linux/WSL. It includes all needed packages.

---

## 2. Clone the Project Repository

```bash
git clone https://github.com/sachinkry/yt_url2pdf.git
cd yt_url2pdf
```

---

## 3. Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

- You should see `(venv)` at the start of your prompt.

---

## 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

- If you see errors about missing packages, try upgrading pip:
  ```bash
  pip install --upgrade pip
  ```
- If a package fails, try installing it individually:
  ```bash
  pip install <package-name>
  ```

---

## 5. Configure API Keys

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and add your API keys:
   ```bash
   nano .env
   ```
   - Fill in your keys for:
     - `ASSEMBLYAI_API_KEY`
     - `OPENROUTER_API_KEY`
     - `GOOGLE_CSE_ID`
     - `GOOGLE_API_KEY`
   - Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

---

## 6. Run the Pipeline

```bash
python main.py
```

- Follow the prompts:
  - Option 1: Convert a YouTube URL to PDF
  - Option 2: Convert a folder of files (.txt/.md/.mp3/.mp4) to PDFs
- You can use any folder path accessible from WSL (e.g., `/mnt/c/Users/YourName/Documents/lectures`). Recommend to put files in the `data/inputs/` folder for convenience.
- PDFs are saved in `data/pdf/`.

---

## 7. Accessing Files Between Windows and WSL

- Your Windows drives are accessible under `/mnt/c/`, `/mnt/d/`, etc.
- You can open the generated PDFs from Windows Explorer by navigating to the project folder in your Windows filesystem.

---

## Troubleshooting

- **LaTeX errors:**
  - TeX Live includes most packages, but if you see errors, check the `errors.log` file in `data/pdf/`.
- **FFmpeg not found:**
  - Make sure you installed it with `sudo apt install ffmpeg`.
- **API errors:**
  - Double-check your `.env` file and API key quotas.
- **Permission errors:**
  - Make sure you have write access to the project folder.
- **Still stuck?**
  - Copy the error message and ask for help (include your WSL version, Python version, and what you tried).

---

## Tips for Success

- **Test with a short video first** to make sure everything works.
- **Keep your system updated:**
  ```bash
  sudo apt update && sudo apt upgrade -y
  ```
- **Monitor API usage** to avoid hitting free tier limits.
- **Use the same venv every time:**
  ```bash
  source venv/bin/activate
  ```
- **Deactivate venv when done:**
  ```bash
  deactivate
  ```

---

## Project Structure

- `main.py`: Orchestrates the pipeline.
- `src/`:
  - `transcribeStep.py`: Transcribes videos.
  - `notesStep.py`: Creates Markdown notes.
  - `imageStep.py`: Adds images to notes.
  - `latexStep.py`: Converts Markdown to LaTeX.
  - `pdfStep.py`: Compiles LaTeX to PDF.
- `data/`: Stores videos, transcripts, notes, images, LaTeX, and PDFs.
- `.env`: Contains API keys (never commit to Git).
- `requirements.txt`: Lists Python dependencies.

---

## Need Help?

- If you get stuck, provide this to chatGPT:
  - The error message
  - What you tried
  - Your WSL/Ubuntu version (`lsb_release -a`)
  - Your Python version (`python3 --version`)
