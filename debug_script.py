import sqlite3
import sys
from pathlib import Path
from src.fetcher import Fetcher
from src.config import DB_PATH

def inspect_db():
    print("--- Step 4: Database Inspection ---")
    if not DB_PATH.exists():
        print(f"Database file not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables found: {[t[0] for t in tables]}")

        if ('seen_papers',) in tables:
            cursor.execute("SELECT count(*) FROM seen_papers")
            count = cursor.fetchone()[0]
            print(f"Total 'seen' papers: {count}")
            
            print("Last 5 entries:")
            cursor.execute("SELECT * FROM seen_papers ORDER BY ROWID DESC LIMIT 5")
            for row in cursor.fetchall():
                print(row)
        else:
            print("Table 'seen_papers' does not exist.")
            
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

def test_fetcher():
    print("\n--- Step 3: Fetcher Test (Simulated) ---")
    try:
        fetcher = Fetcher()
        # Fetching only one feed or limiting the scope would be ideal, 
        # but fetcher.fetch_all() goes through all configured feeds.
        # We'll run it and rely on the fact that we can kill it if it hangs, 
        # but since we are inside a tool call, I'll rely on it being relatively fast for metadata.
        papers = fetcher.fetch_all()
        
        print(f"\nFetcher returned {len(papers)} papers.")
        for p in papers[:3]:
            print(f"- {p.title} ({p.link})")
            
    except Exception as e:
        print(f"Fetcher failed: {e}")

if __name__ == "__main__":
    inspect_db()
    test_fetcher()
