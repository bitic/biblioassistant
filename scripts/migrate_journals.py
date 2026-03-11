import sqlite3
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH
from src.logger import logger

def migrate_journals():
    logger.info("Migrating journals from seen_papers to journals table...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get all unique journals from seen_papers
    cursor.execute('''
        SELECT DISTINCT source_id, title, source_url 
        FROM seen_papers 
        WHERE source_id IS NOT NULL AND is_relevant = 1
    ''')
    # Note: 'title' here refers to the source/journal name in the old schema if we didn't have it elsewhere
    # But wait, seen_papers actually has a 'source' column in some versions or we used the 'source' variable
    
    # Let's check columns again
    cursor.execute("PRAGMA table_info(seen_papers)")
    cols = [r[1] for r in cursor.fetchall()]
    
    source_col = 'source' if 'source' in cols else 'title' # Fallback
    
    cursor.execute(f'''
        SELECT DISTINCT source_id, {source_col}, source_url 
        FROM seen_papers 
        WHERE source_id IS NOT NULL AND is_relevant = 1
    ''')
    rows = cursor.fetchall()
    
    for sid, name, url in rows:
        clean_sid = sid.split("/")[-1]
        # Try to clean name if it's actually an article title (heuristic)
        if name and len(name) > 100: name = clean_sid 
        
        cursor.execute('''
            INSERT INTO journals (id, name, url) 
            VALUES (?, ?, ?) 
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, url=COALESCE(excluded.url, url)
        ''', (clean_sid, name, url))
    
    conn.commit()
    conn.close()
    logger.info("Journal migration complete.")

if __name__ == "__main__":
    migrate_journals()
