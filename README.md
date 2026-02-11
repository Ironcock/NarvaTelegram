# Job Scraper Bot for Telegram

This bot scrapes job listings from seti.ee, cvkeskus.ee, and tootukassa.ee, filters for Narva location (for tootukassa), translates the content to Russian using Google Gemini AI, and posts them to a Telegram channel.

## Setup Instructions

1.  **Dependencies**:
    Run `pip install -r requirements.txt` to install locally.
    You need `requests`, `beautifulsoup4`, and `google-generativeai`.

2.  **Configuration**:
    The Telegram Token and Chat ID are hardcoded in `scraper.py`.
    The Gemini API Key is loaded from environment variables.

3.  **GitHub Actions**:
    The workflow is defined in `.github/workflows/run_bot.yml`.
    It runs every 30 minutes.
    
    **Setting up the Secret**:
    - Go to your GitHub repository -> Settings -> Secrets and variables -> Actions.
    - Click "New repository secret".
    - **Name**: `GEMINI_API_KEY`
    - **Value**: Your Google Gemini API Key.

4.  **Running Locally**:
    To run locally, set the environment variable:
    ```powershell
    $env:GEMINI_API_KEY = "YOUR_API_KEY"
    python scraper.py
    ```

## Files
- `scraper.py`: Main script.
- `requirements.txt`: Python dependencies.
- `.github/workflows/run_bot.yml`: GitHub Actions workflow.
- `history.json`: Stores IDs of processed jobs to avoid duplicates (created automatically).
