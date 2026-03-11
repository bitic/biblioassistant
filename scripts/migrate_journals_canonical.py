import sys
from pathlib import Path
import requests
import sqlite3
import time

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH
from src.logger import logger

def migrate_journals():
    logger.info("Starting canonical journal migration from OpenAlex...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all unique journal IDs that need a name
    cursor.execute('SELECT id FROM journals WHERE name IS NULL OR name = id')
    journal_ids = [row[0] for row in cursor.fetchall()]
    
    total = len(journal_ids)
    logger.info(f"Found {total} journals needing official names.")
    
    if total == 0:
        logger.info("No journals need migration.")
        return

    # Fetch names from OpenAlex in batches
    batch_size = 50
    count = 0
    for i in range(0, total, batch_size):
        batch = journal_ids[i:i + batch_size]
        # OpenAlex uses 'openalex' filter for sources (journals)
        ids_str = "|".join(batch)
        url = f"https://api.openalex.org/sources?filter=openalex:{ids_str}&per_page={batch_size}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Error {response.status_code} fetching batch: {response.text}")
                time.sleep(2)
                continue
                
            data = response.json()
            results = data.get("results", [])
            
            for source in results:
                jid = source.get("id").split("/")[-1]
                name = source.get("display_name")
                homepage = source.get("homepage_url")
                issn = source.get("issn_l")
                
                if jid and name:
                    cursor.execute(
                        'UPDATE journals SET name = ?, url = COALESCE(?, url), issn = COALESCE(?, issn) WHERE id = ?',
                        (name, homepage, issn, jid)
                    )
                    count += 1
            
            conn.commit()
            logger.info(f"Processed {min(i + batch_size, total)}/{total}... Updated {count} journals.")
            time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error fetching batch starting at {i}: {e}")
            time.sleep(1)
            
    conn.close()
    logger.info(f"Journal migration complete. Total names updated: {count}")

if __name__ == "__main__":
    migrate_journals()
