#!/usr/bin/env python3
import sys
import subprocess
from datetime import datetime, timedelta
from src.db import db
from src.logger import logger

def run_backfill():
    # 1. Get current backfill cursor
    cursor_str = db.get_metadata("backfill_cursor")
    
    if not cursor_str:
        # First time running: start from 7 days ago
        cursor = datetime.now() - timedelta(days=7)
        logger.info(f"No backfill cursor found. Starting from 7 days ago: {cursor.strftime('%Y-%m-%d')}")
    else:
        cursor = datetime.strptime(cursor_str, "%Y-%m-%d")
        logger.info(f"Backfill cursor found: {cursor.strftime('%Y-%m-%d')}")

    # 2. Define the window (one week)
    end_date = cursor
    start_date = cursor - timedelta(days=7)
    
    # 3. Check if we reached the limit (Jan 1, 2000)
    limit = datetime(2000, 1, 1)
    if start_date < limit:
        if end_date <= limit:
            logger.info("Backfill reached the limit (2000-01-01). Stopping.")
            return
        else:
            start_date = limit
            logger.info("Adjusting start_date to limit (2000-01-01).")

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    msg = f"BACKFILL STEP: Processing from {start_str} to {end_str}"
    logger.info(f">>> {msg}")
    db.add_event("BACKFILL_START", msg)

    # 4. Calculate 'days back' for --backfill argument
    # main.py uses (datetime.now() - timedelta(days=args.backfill)) as from_date
    now = datetime.now()
    days_back = (now - start_date).days
    
    # 5. Run the pipeline
    # We use python -m src.main to run the actual pipeline code
    cmd = [
        sys.executable, "-m", "src.main",
        "--backfill", str(days_back),
        "--to-date", end_str,
        "--backfill-mode"
    ]
    
    # Pass --deploy if it was passed to this script
    if "--deploy" in sys.argv:
        cmd.append("--deploy")

    logger.info(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        
        # 6. Update cursor for tomorrow
        db.set_metadata("backfill_cursor", start_str)
        success_msg = f"Backfill step successful. New cursor: {start_str}"
        logger.info(success_msg)
        db.add_event("BACKFILL_END", success_msg)
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Backfill step failed for period {start_str} to {end_str}: {e}"
        logger.error(error_msg)
        db.add_event("ERROR", error_msg)
        sys.exit(1)

if __name__ == "__main__":
    run_backfill()
