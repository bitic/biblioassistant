#!/bin/bash

# BiblioAssistant Daily Runner
# This script is intended to be run via anacron or cron.

# Use directory of the script as project dir
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="$PROJECT_DIR/data/cron.log"

# Ensure the data directory exists for logging
mkdir -p "$PROJECT_DIR/data"

echo "--- Pipeline Run Started: $(date) ---" >> "$LOG_FILE"

# 1. Navigate to project directory
cd "$PROJECT_DIR" || exit

# 2. Check if Ollama is needed
NEEDS_OLLAMA=$(uv run -q python -c "
import sys
try:
    from src.config import RELEVANCE_ENGINE, SYNTHESIS_ENGINE, GEMINI_API_KEY, MAX_MONTHLY_COST
    from src.db import db

    needs = False
    if RELEVANCE_ENGINE == 'ollama' or SYNTHESIS_ENGINE == 'ollama':
        needs = True
    if RELEVANCE_ENGINE == 'gemini' and not GEMINI_API_KEY:
        needs = True

    try:
        if db.get_monthly_cost() >= MAX_MONTHLY_COST:
            needs = True
    except Exception:
        pass

    print('yes' if needs else 'no')
except Exception as e:
    sys.stderr.write(str(e))
    print('no')
" 2>> "$LOG_FILE")

if [ "$NEEDS_OLLAMA" = "yes" ]; then
    if ! curl -s http://localhost:11434/api/tags > /dev/null; then
        echo "[$(date)] ERROR: Ollama is needed but not running. Skipping run." >> "$LOG_FILE"
        exit 1
    fi
fi

# 3. Run the pipeline
# The --deploy flag ensures the site is live after processing
uv run python -m src.main --deploy >> "$LOG_FILE" 2>&1

echo "--- Pipeline Run Finished: $(date) ---" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
