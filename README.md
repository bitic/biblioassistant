# [BiblioAssistant](https://github.com/bitic/biblioassistant/)

[BiblioAssistant](https://github.com/bitic/biblioassistant/) is an automated pipeline designed for keeping track of new scientific literature. It filters high volumes of daily publications and generates high-value summaries for researchers, with a focus on hydrology, climate, and meteorology. The selection is specifically tailored to the research interests of the [Hydrology and Climate Change](https://observatoriebre.gencat.cat) research group at the [Ebro Observatory](https://observatoriebre.gencat.cat).

## Features

- **Waterfall Filter Architecture:**
  - **Ingestion:** Monitors RSS feeds from major journals (AGU, EGU, AMS, Springer, etc.).
  - **Relevance Filtering:** Local processing using **Ollama** (e.g., Llama 3 or DeepSeek-R1) to maintain privacy and reduce costs.
  - **Synthesis:** Deep synthesis of relevant content using advanced LLMs (Ollama/DeepSeek or Gemini API).
- **Full-Text Extraction:** Automated PDF download and text extraction (with HTML fallback).
- **Static Site Generation:** Beautiful, bookish-style website for browsing summaries.
- **MathJax Support:** High-quality rendering of LaTeX equations.
- **RSS Feed:** Dedicated feed for the generated summaries.
- **Automated Deployment:** Easy `rsync`-based deployment to remote servers.

## Prerequisites

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** (Python package and project manager)
- **[Ollama](https://ollama.com/)** (for local LLM processing)
- **Optional:** [Gemini CLI](https://github.com/google/gemini-cli) (if using Gemini for synthesis)

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd biblioassistant
   ```

2. **Install dependencies:**
   Using `uv`:
   ```bash
   uv sync
   ```

3. **Configure Ollama:**
   Pull the required models (e.g., DeepSeek-R1 14B):
   ```bash
   ollama pull deepseek-r1:14b
   ```

4. **Environment Variables:**
   Create a `.env` file (or set variables in your shell) for sensitive or environment-specific configuration:
   ```bash
   # LLM Configuration
   SYNTHESIS_ENGINE=gemini-api           # 'ollama' or 'gemini-api'
   GEMINI_API_KEY=your_api_key_here
   GEMINI_MODEL=gemini-flash-latest      # Defaults to gemini-flash-latest
   
   # Local Ollama Settings (Optional)
   OLLAMA_HOST=http://localhost:11434
   OLLAMA_MODEL=deepseek-r1:14b          # Model used for synthesis
   OLLAMA_FILTER_MODEL=llama3.1:8b       # Model used for relevance filtering
   
   # Budget Control
   MAX_MONTHLY_COST=10.0                 # Maximum monthly spend in Euro
   
   # Deployment configuration
   REMOTE_HOST=your.server.com
   REMOTE_USER=your_username
   REMOTE_PATH=/var/www/biblio/
   
   # OpenAlex Polite Pool
   OPENALEX_EMAIL=your-email@example.com
   ```

## Usage

Run the full pipeline (Discovery -> Filter -> Synthesize -> Generate -> Deploy):
```bash
uv run python -m src.main --deploy
```

### Command Line Arguments

- `--deploy`: Sync the generated site to the remote server.
- `--force-all`: Ignore the "seen" database and re-process all entries.
- `--generate-only`: Skip fetching and processing; only rebuild the static site.
- `--rss`: Enable legacy RSS feeds (default: disabled).
- `--add-doi <DOI>`: Manually add a specific paper by DOI.
- `--backfill <days>`: Re-process the last N days.

## Scheduling

To run the pipeline automatically every day, you have two options on Linux:

### Option 1: Standard Cron (User-level)
Ideal for servers that are always on.

1. Open your crontab: `crontab -e`
2. Add the following line:
   ```bash
   0 6 * * * cd /path/to/biblioassistant && /usr/local/bin/uv run python -m src.main --deploy >> /path/to/biblioassistant/data/cron.log 2>&1
   ```

### Option 2: Cron Daily (System-level / Recommended for Laptops)
This uses `anacron` to ensure the job runs even if the computer was off at the scheduled time.

1. Create a launcher script: `sudo nano /etc/cron.daily/biblioassistant`
2. Paste the following:
   ```bash
   #!/bin/sh
   # Launcher for BiblioAssistant
   su your_username -c "/path/to/biblioassistant/run_daily.sh"
   ```
3. Make it executable: `sudo chmod +x /etc/cron.daily/biblioassistant`

The system uses the `run_daily.sh` script provided in the repository to manage the execution environment.

## Project Structure

- `src/`: Core Python modules.
- `templates/`: Jinja2 templates for the static site.
- `data/`: Local storage for the database, PDFs, and Markdown summaries (ignored by git).
- `public/`: The generated static website (ignored by git).

## Author

Developed by **[Pere Quintana Seguí](http://pere.quintanasegui.com)**.

This project was partially funded by **[Fundació Observatori de l'Ebre](https://observatoriebre.gencat.cat)**.

This project was developed with the assistance of AI tools, specifically **[Gemini CLI](https://geminicli.com)**.

## License

GPLv3
