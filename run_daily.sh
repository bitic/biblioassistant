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

# Find uv absolute path
UV_PATH=$(which uv)
if [ -z "$UV_PATH" ]; then
    # Fallback to common location if not in PATH
    if [ -f "/home/pquintana/.local/bin/uv" ]; then
        UV_PATH="/home/pquintana/.local/bin/uv"
    else
        echo "[$(date)] ERROR: 'uv' command not found." >> "$LOG_FILE"
        exit 1
    fi
fi

# 2. Check if Ollama is needed
NEEDS_OLLAMA=$($UV_PATH run -q python -c "
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
# Default to --deploy if no arguments are provided, otherwise use provided arguments
if [ $# -eq 0 ]; then
    $UV_PATH run python -m src.main --deploy >> "$LOG_FILE" 2>&1
    
    # 4. Run the backfill (historical papers)
    echo "[$(date)] INFO: Starting backfill step..." >> "$LOG_FILE"
    $UV_PATH run python backfill.py --deploy >> "$LOG_FILE" 2>&1
else
    $UV_PATH run python -m src.main "$@" >> "$LOG_FILE" 2>&1
fi

echo "--- Pipeline Run Finished: $(date) ---" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
