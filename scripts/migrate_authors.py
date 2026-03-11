import sys
from pathlib import Path
import requests
import sqlite3
import time

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH
from src.logger import logger

def migrate():
    logger.info("Starting author migration...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get unique author IDs from papers that have a summary
    cursor.execute('''
        SELECT DISTINCT author_id 
        FROM paper_authors
    ''')
    author_ids = [row[0] for row in cursor.fetchall()]
    
    logger.info(f"Found {len(author_ids)} unique authors to migrate.")
    
    # 2. Fetch names from OpenAlex in batches
    batch_size = 20
    for i in range(0, len(author_ids), batch_size):
        batch = author_ids[i:i + batch_size]
        ids_str = "|".join(batch)
        url = f"https://api.openalex.org/authors?filter=openalex:{ids_str}&per_page={batch_size}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Error {response.status_code} fetching batch: {response.text}")
                continue
            data = response.json()
            
            results = data.get("results", [])
            if not results:
                logger.warning(f"No results found for batch starting at {i}")
            
            for author in results:
                aid = author.get("id").split("/")[-1]
                name = author.get("display_name")
                if aid and name:
                    cursor.execute(
                        'INSERT INTO authors (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                        (aid, name)
                    )
            
            conn.commit()
            logger.info(f"Processed batch {i//batch_size + 1}")
            time.sleep(0.5) # Be nice to API
            
        except Exception as e:
            logger.error(f"Error fetching batch: {e}")
            
    conn.close()
    logger.info("Migration complete.")

if __name__ == "__main__":
    migrate()
