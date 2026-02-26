import sqlite3
import requests
import time
from pathlib import Path

DB_PATH = Path("data/db.sqlite3")

def update_journal_urls():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get top journals by source_id
    cursor.execute("""
        SELECT source_id, COUNT(*) as count 
        FROM seen_papers 
        WHERE source_id IS NOT NULL 
        GROUP BY source_id 
        ORDER BY count DESC 
        LIMIT 20
    """)
    
    top_journals = cursor.fetchall()
    print(f"Updating URLs for top {len(top_journals)} journals...")
    
    for source_id, count in top_journals:
        if not source_id.startswith("S"): continue
        
        print(f"Fetching metadata for {source_id}...")
        try:
            url = f"https://api.openalex.org/sources/{source_id}"
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                data = response.json()
                homepage = data.get("homepage_url")
                if homepage:
                    print(f"  Setting URL for {source_id}: {homepage}")
                    cursor.execute("UPDATE seen_papers SET source_url = ? WHERE source_id = ?", (homepage, source_id))
                    conn.commit()
            time.sleep(0.5)
        except Exception as e:
            print(f"  Error: {e}")
            
    conn.close()

if __name__ == "__main__":
    update_journal_urls()
