# Development Plan: BiblioAssistant (SCRC)

This document outlines the iterative development phases for the BiblioAssistant automated scientific curation system.

## Phase 1: Foundation & Project Structure
- [x] **Directory Layout:** Create `src/` directory for code and `data/` for persistence.
- [x] **Configuration:** Implement `src/config.py` to handle:
    - RSS feed URLs.
    - Ollama API settings (Local).
    - Gemini/Claude API keys (Remote).
    - SMTP credentials for Delta Chat.
- [x] **Logging:** Setup a centralized logger.
- [x] **Data Models:** Define a `Paper` dataclass to maintain consistency across the pipeline.

## Phase 2: Ingestion (Fetcher)
- [x] **RSS Module:** Implement `src/fetcher.py` using `feedparser`.
- [x] **Persistence:** Create a simple SQLite database or JSON file to track "seen" DOIs/links to avoid duplicates.
- [x] **Validation:** Ensure we capture Title, Abstract, DOI, and PDF links correctly.

## Phase 3: Local Relevance Filter (Ollama)
- [x] **Ollama Integration:** Implement `src/filter.py` using `requests` to talk to the local Ollama API.
- [x] **Prompt Engineering:** Develop a robust prompt for binary classification (Interesting: YES/NO).
- [x] **Batching:** Logic to process the daily feed results through the local model.

## Phase 4: Full-Text Extraction
- [x] **PDF Downloader:** Logic to fetch PDFs from DOI/Publisher links.
- [x] **Storage:** Save PDFs locally to `data/papers/YYYY/YYYYMMDD-Author.pdf`.
- [x] **Text Extraction:** Implement `src/extractor.py` using `PyMuPDF` (fitz).
- [ ] **Cleanup:** Strip headers/footers/references where possible to optimize token usage for the next phase.

## Phase 5: Synthesis (Gemini CLI)
- [x] **CLI Wrapper:** Implement `src/synthesizer.py` to call `gemini` CLI via `subprocess`.
- [x] **Token usage and cost tracking:** Record API consumption in the database.
- [x] **Structured Output:** Enforce the "Extended Card" format through the `--prompt` flag:
    - Language: English.
    - SI Units enforcement.
    - Funding identification.
    - Methodology & Results synthesis.
- [x] **Storage:** Save as `data/summaries/YYYY/YYYYMMDD-Author.md`.
- [x] **Formatting:** Ensure output is clean Markdown.

## Phase 6: Static Site Generation
- [x] **Generator:** Implement `src/generator.py` to build the static site.
- [x] **Templates:** Create Jinja2 templates for:
    - `index.html` (Recent summaries).
    - `archive.html` (List by Year/Month).
    - `paper.html` (Individual "Fitxa Estesa").
- [ ] **RSS Feed:** Generate a site-specific RSS feed (`feed.xml`) containing the new summaries.
- [x] **Deployment:** Implement `src/deploy.py` or a shell script to `rsync` the `public/` directory to the remote server.

## Phase 7: Orchestration & Automation
- [x] **Main Entrypoint:** Create `src/main.py` to tie all modules together.
- [ ] **Error Handling:** Robust retries for network-dependent tasks.
- [x] **CLI Interface:** Basic commands to trigger manual runs or status checks.