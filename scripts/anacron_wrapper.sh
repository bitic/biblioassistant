#!/bin/bash
# BiblioAssistant Daily Runner Wrapper for Anacron
# This script should be placed in /etc/cron.daily/

# Set the project directory
PROJECT_DIR="/hangar/pquintana/projectes/biblioassistant"
USER_NAME="pquintana"

# Ensure the PATH includes common locations for 'uv'
export PATH="/home/$USER_NAME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Execute the daily runner as the specific user
# This ensures file ownership and permissions remain correct
sudo -u "$USER_NAME" bash "$PROJECT_DIR/run_daily.sh"
