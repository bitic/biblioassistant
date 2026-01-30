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

# 2. Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "[$(date)] ERROR: Ollama is not running. Skipping run." >> "$LOG_FILE"
    exit 1
fi

# 3. Run the pipeline
# The --deploy flag ensures the site is live after processing
uv run python -m src.main --deploy >> "$LOG_FILE" 2>&1

echo "--- Pipeline Run Finished: $(date) ---" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
