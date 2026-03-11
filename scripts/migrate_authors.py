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
    logger.info("Starting robust author migration...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get all unique author IDs that don't have a name yet
    cursor.execute('''
        SELECT DISTINCT pa.author_id 
        FROM paper_authors pa
        LEFT JOIN authors a ON pa.author_id = a.id
        WHERE a.name IS NULL OR a.name = pa.author_id
    ''')
    author_ids = [row[0] for row in cursor.fetchall()]
    
    total = len(author_ids)
    logger.info(f"Found {total} unique authors needing names.")
    
    if total == 0:
        logger.info("No authors need name migration.")
        return

    # 2. Fetch names from OpenAlex in batches
    batch_size = 50
    count = 0
    for i in range(0, total, batch_size):
        batch = author_ids[i:i + batch_size]
        ids_str = "|".join(batch)
        # Using the filter format documented by OpenAlex
        url = f"https://api.openalex.org/authors?filter=openalex:{ids_str}&per_page={batch_size}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Error {response.status_code} fetching batch: {response.text}")
                time.sleep(2)
                continue
                
            data = response.json()
            results = data.get("results", [])
            
            for author in results:
                aid = author.get("id").split("/")[-1]
                name = author.get("display_name")
                if aid and name:
                    cursor.execute(
                        'INSERT INTO authors (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                        (aid, name)
                    )
                    count += 1
            
            conn.commit()
            logger.info(f"Processed {min(i + batch_size, total)}/{total}... Saved {count} names so far.")
            time.sleep(0.2) # OpenAlex allows 100k requests/day, we can be relatively fast
            
        except Exception as e:
            logger.error(f"Error fetching batch: {e}")
            time.sleep(1)
            
    conn.close()
    logger.info(f"Migration complete. Total names updated: {count}")

if __name__ == "__main__":
    migrate()
