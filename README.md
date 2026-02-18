# Book Reader

A Streamlit app that converts books to audio and plays them page by page.

## Supported Inputs
- Upload `.txt` or `.pdf` files (up to 50 MB)
- GitHub repo URL — browse and pick any `.md` or `.txt` file from the repo

## How It Works
- Each page's audio is generated on demand using text-to-speech
- The next page's audio is pre-generated in the background while you listen
- Played pages' audio files are deleted automatically to conserve memory

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optional Secrets

Create `.streamlit/secrets.toml` (this file is gitignored):

```toml
# Use OpenAI TTS for higher-quality audio (costs ~$0.015/1K characters)
OPENAI_API_KEY = "sk-..."

# Access private GitHub repositories
GITHUB_TOKEN = "ghp_..."
```

## Deploying to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → connect the repo → deploy
3. Optionally add secrets in the app's **Settings → Secrets** section
