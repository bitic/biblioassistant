# [BiblioAssistant](https://github.com/bitic/biblioassistant/)

## Project Overview
[BiblioAssistant](https://github.com/bitic/biblioassistant/) is a Python-based automated pipeline designed for keeping track of new scientific literature in the fields of **hydrology, climate, and meteorology**. Its primary goal is to filter high volumes of daily publications and generate high-value summaries for researchers.

The system prioritizes local processing for filtering to maintain privacy and reduce costs, utilizing remote powerful LLMs only for deep synthesis of relevant content.

## Architecture
The system implements a four-stage "Waterfall Filter" architecture:

1.  **Ingestion (Fetcher):**
    *   Monitors RSS feeds and APIs (AGU, EGU, AMS, Springer, etc.).
2.  **Relevance Filtering (Local):**
    *   **Engine:** Ollama (`llama3.1:8b`).
    *   **Input:** Title and Abstract.
    *   **Logic:** Binary classification (Interesting: YES/NO).
    *   **Characteristics:** High-throughput local processing (~6s/abstract, ~20 min/day for ~200 candidates), zero API cost, no external quota limits.
3.  **Processing & Synthesis (Remote):**
    *   **Engine:** Gemini API (`gemini-2.5-flash` via Google GenAI SDK).
    *   **Input:** Full PDF text or HTML extraction.
    *   **Output:** Structured "Extended Card" (Fitxa Estesa).
    *   **Characteristics:** Near-instant (5–10s/paper), 1M token context window (prevents CPU timeouts on large texts), 0€ cost within Google AI Studio's free tier (20 requests/day covers the 2–6 daily relevant papers). Automatic fallback to local Ollama if remote API is unavailable.
4.  **Presentation (Static Site):**
    *   **Output:** Static HTML website.
    *   **Structure:**
        *   Main page: Recent articles.
        *   Archive: Organized by Year/Month.
        *   Detail: Individual page per article (Fitxa).
        *   Feed: RSS feed of the generated summaries.
    *   **Deployment:** `rsync` to remote server.

## Technical Requirements

### Environment
*   **Language:** Python 3.x
*   **Package Manager:** `uv` (for environment and dependency management)
*   **Key Libraries:**
    *   `feedparser` (RSS handling)
    *   `PyMuPDF` or `pdfplumber` (PDF extraction)
    *   `requests` or official SDKs (LLM API interaction)
    *   `smtplib` (Email/Delta Chat delivery)

### Output Specifications
*   **Language:** English (All summaries and website content).
*   **Standards:** Adhere to the **International System of Units (SI)**.
*   **Storage:** 
    *   Summaries: `data/summaries/YYYY/YYYYMMDD-Author.md`
    *   Papers: `data/papers/YYYY/YYYYMMDD-Author.pdf`

**Required Fields:**
1.  **Identification:** Title, Authors, Lab/Group, Citation, DOI.
2.  **Funding:** Project names, programs, reference codes.
3.  **Objective:** Research question or hypothesis.
4.  **Study Configuration:** Spatial and temporal scales (SI units).
5.  **Methodology & Data:** Models, data sources (satellite, reanalysis, etc.).
6.  **Main Results:** Synthetic and quantitative key findings.
7.  **Contribution:** Original value vs. existing literature.

## Current Status
*   **Phase:** Design & Specification.
*   **Reference Document:** `2026-01-29-004443.md` (Technical Specs).

## Project Memories
- **Environment:** The project uses `uv` for environment and dependency management.
- **Commit Messages:** The user prefers verbose, well-written, and descriptive commit messages that clearly explain the motivation and nature of the changes.
- **Engine vs Content:** NEVER commit files located in the `data/` directory or any other "content" files (summaries, PDFs, news items, databases). The repository must only contain the "engine" (code, templates, config).

