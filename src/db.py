import sqlite3
from pathlib import Path
from src.config import DB_PATH
from src.logger import logger
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema and handle migrations."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        
        # 1. Ensure seen_papers exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seen_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doi TEXT UNIQUE,
                link TEXT UNIQUE,
                title TEXT,
                processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Migration: Add source_id column if it doesn't exist
        cursor.execute("PRAGMA table_info(seen_papers)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'source_id' not in columns:
            logger.info("Migrating database: adding source_id column to seen_papers.")
            cursor.execute('ALTER TABLE seen_papers ADD COLUMN source_id TEXT')
        
        if 'type' not in columns:
            logger.info("Migrating database: adding type column to seen_papers.")
            cursor.execute('ALTER TABLE seen_papers ADD COLUMN type TEXT')
        
        if 'source_url' not in columns:
            logger.info("Migrating database: adding source_url column to seen_papers.")
            cursor.execute('ALTER TABLE seen_papers ADD COLUMN source_url TEXT')

        if 'is_relevant' not in columns:
            logger.info("Migrating database: adding is_relevant column to seen_papers.")
            cursor.execute('ALTER TABLE seen_papers ADD COLUMN is_relevant INTEGER DEFAULT 0')
        
        if 'relevance_reason' not in columns:
            logger.info("Migrating database: adding relevance_reason column to seen_papers.")
            cursor.execute('ALTER TABLE seen_papers ADD COLUMN relevance_reason TEXT')

        # 3. Create Promotion Tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitored_journals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitored_authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id TEXT UNIQUE,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authors (
                id TEXT PRIMARY KEY,
                name TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paper_authors (
                paper_id INTEGER,
                author_id TEXT,
                PRIMARY KEY (paper_id, author_id),
                FOREIGN KEY (paper_id) REFERENCES seen_papers(id),
                FOREIGN KEY (author_id) REFERENCES authors(id)
            )
        ''')

        # Events table for the hidden RSS feed
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Usage table for API cost tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()

    def is_seen(self, link: str, doi: str = None) -> bool:
        """Check if a paper has already been processed."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        if doi:
            cursor.execute('SELECT 1 FROM seen_papers WHERE link = ? OR doi = ?', (link, doi))
        else:
            cursor.execute('SELECT 1 FROM seen_papers WHERE link = ?', (link,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def get_processed_date(self, link: str) -> Optional[str]:
        """Returns the processed date for a given paper link."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT processed_date FROM seen_papers WHERE link = ?', (link,))
        result = cursor.fetchone()
        conn.close()
        if result and result[0]:
            # SQLite timestamp is YYYY-MM-DD HH:MM:SS
            return result[0].split(" ")[0]
        return None

    def get_all_processed_dates(self) -> dict:
        """Returns a dictionary mapping link -> processed_date (datetime object)."""
        from datetime import datetime
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT link, processed_date FROM seen_papers')
        rows = cursor.fetchall()
        conn.close()
        
        results = {}
        for link, date_str in rows:
            if date_str:
                try:
                    # SQLite timestamp is usually YYYY-MM-DD HH:MM:SS
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    results[link] = dt
                except ValueError:
                    pass
        return results

    def get_journal_urls(self) -> dict:
        """Returns a mapping of paper_link -> (source_id, source_url)."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT link, source_id, source_url FROM seen_papers WHERE source_url IS NOT NULL')
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: (row[1], row[2]) for row in rows}

    def add_seen(self, link: str, title: str, doi: str = None, source_id: str = None, author_ids: list[str] = None, processed_date: str = None, type: str = None, source_url: str = None, is_relevant: bool = False, relevance_reason: str = None, authors_data: dict = None):
        """Mark a paper as seen and record its authors and relevance status."""
        import time
        retries = 3
        rel_int = 1 if is_relevant else 0
        for i in range(retries):
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    cursor = conn.cursor()
                    if processed_date:
                        cursor.execute(
                            'INSERT INTO seen_papers (link, doi, title, source_id, processed_date, type, source_url, is_relevant, relevance_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                            (link, doi, title, source_id, processed_date, type, source_url, rel_int, relevance_reason)
                        )
                    else:
                        cursor.execute(
                            'INSERT INTO seen_papers (link, doi, title, source_id, type, source_url, is_relevant, relevance_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
                            (link, doi, title, source_id, type, source_url, rel_int, relevance_reason)
                        )
                    paper_id = cursor.lastrowid
                    
                    # Record authors for frequency tracking
                    to_process = []
                    if authors_data:
                        for auth_id, name in authors_data.items():
                            clean_id = auth_id.split("/")[-1]
                            cursor.execute(
                                'INSERT INTO authors (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                                (clean_id, name)
                            )
                            to_process.append(clean_id)
                    elif author_ids:
                        to_process = [aid.split("/")[-1] for aid in author_ids if aid]

                    if paper_id:
                        for clean_auth_id in to_process:
                            cursor.execute(
                                'INSERT OR IGNORE INTO paper_authors (paper_id, author_id) VALUES (?, ?)',
                                (paper_id, clean_auth_id)
                            )
                    conn.commit()
                break # Success
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and i < retries - 1:
                    logger.warning(f"Database locked. Retrying ({i+1}/{retries})...")
                    time.sleep(1)
                else:
                    logger.error(f"Database error in add_seen: {e}")
                    break

    def get_recent_papers_by_days(self, days: int = 7) -> list:
        """Returns list of papers processed in the last X days for filter audit."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT title, link, doi, processed_date, is_relevant, relevance_reason
            FROM seen_papers
            WHERE processed_date >= datetime('now', ?)
            ORDER BY processed_date DESC
        ''', (f'-{days} days',))
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append({
                'title': row['title'],
                'link': row['link'],
                'doi': row['doi'],
                'date': row['processed_date'],
                'is_relevant': bool(row['is_relevant']),
                'relevance_reason': row['relevance_reason']
            })
        return results

    def add_event(self, event_type: str, message: str):
        """Record an event for the internal activity feed."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO events (event_type, message) VALUES (?, ?)', (event_type, message))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding event: {e}")

    def get_recent_events(self, limit: int = 50) -> list:
        """Returns recent system events."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT event_type, message, timestamp FROM events ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int, cost: float):
        """Record LLM API usage and cost."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO usage (model, prompt_tokens, completion_tokens, total_tokens, cost) VALUES (?, ?, ?, ?, ?)',
                    (model, prompt_tokens, completion_tokens, total_tokens, cost)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording usage: {e}")

    def get_monthly_cost(self) -> float:
        """Calculate total LLM cost for the current month."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(cost) FROM usage WHERE timestamp >= date('now', 'start of month')")
        result = cursor.fetchone()
        conn.close()
        return result[0] if result[0] is not None else 0.0

    def get_promotable_journals(self, threshold: int = 5) -> list:
        """Find journals with many relevant papers that aren't monitored yet."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT source_id, COUNT(*) as count
            FROM seen_papers
            WHERE is_relevant = 1 AND source_id IS NOT NULL
            AND source_id NOT IN (SELECT source_id FROM monitored_journals)
            GROUP BY source_id
            HAVING count >= ?
            ORDER BY count DESC
        ''', (threshold,))
        results = cursor.fetchall()
        conn.close()
        return results

    def add_monitored_journal(self, source_id: str):
        """Add a journal to the monitored list (auto-promotion)."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO monitored_journals (source_id) VALUES (?)', (source_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding monitored journal: {e}")

    def get_monitored_journals(self) -> list[str]:
        """Returns list of source_ids that have been promoted."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT source_id FROM monitored_journals')
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def get_monitored_authors(self) -> list[str]:
        """Returns list of author_ids that have been promoted."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT author_id FROM monitored_authors')
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def get_all_authors(self) -> list:
        """Returns a list of all authors with their paper counts, sorted by name."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.id, a.name, COUNT(pa.paper_id) as count
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            GROUP BY a.id, a.name
            ORDER BY a.name ASC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]

    def get_paper_authors(self, paper_link: str) -> list:
        """Returns a list of authors (id, name) for a given paper link."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.id, a.name
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            JOIN seen_papers p ON p.id = pa.paper_id
            WHERE p.link = ?
        ''', (paper_link,))
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1]} for r in rows]

    def get_all_paper_authors(self) -> dict:
        """Returns a mapping of paper_link -> list of author dicts (id, name)."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.link, a.id, a.name
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            JOIN seen_papers p ON p.id = pa.paper_id
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        results = {}
        for link, aid, name in rows:
            if link not in results:
                results[link] = []
            results[link].append({"id": aid, "name": name})
        return results

db = Database()
