import sqlite3
from pathlib import Path
from src.config import DB_PATH
from src.logger import logger

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
            CREATE TABLE IF NOT EXISTS paper_authors (
                paper_id INTEGER,
                author_id TEXT,
                PRIMARY KEY (paper_id, author_id),
                FOREIGN KEY (paper_id) REFERENCES seen_papers(id)
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
        conn.close()

    def add_event(self, event_type: str, message: str):
        """Records an event for the system log/RSS."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO events (event_type, message) VALUES (?, ?)', (event_type, message))
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording event: {e}")

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int, cost: float = 0.0):
        """Records API usage and costs."""
        try:
            total_tokens = prompt_tokens + completion_tokens
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO usage (model, prompt_tokens, completion_tokens, total_tokens, cost) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (model, prompt_tokens, completion_tokens, total_tokens, cost))
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording usage: {e}")

    def get_monthly_cost(self) -> float:
        """Calculates total cost for the current month."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                # Use strftime to get current Year-Month
                cursor.execute('''
                    SELECT SUM(cost) FROM usage 
                    WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
                ''')
                result = cursor.fetchone()
                return result[0] if result and result[0] else 0.0
        except Exception as e:
            logger.error(f"Error calculating monthly cost: {e}")
            return 0.0

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Returns the most recent events."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT event_type, message, timestamp FROM events ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def is_seen(self, link: str, doi: str = None) -> bool:
        """Check if a paper (by link or DOI) has already been processed."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        if doi:
            cursor.execute('SELECT 1 FROM seen_papers WHERE link = ? OR doi = ?', (link, doi))
        else:
            cursor.execute('SELECT 1 FROM seen_papers WHERE link = ?', (link,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def get_last_run_date(self) -> str:
        """Returns the most recent processed_date in YYYY-MM-DD format, or None."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(processed_date) FROM seen_papers')
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
                    # It might be in ISO format or others depending on insertion
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    results[link] = dt
                except ValueError:
                    # Fallback or ignore
                    pass
        return results

    def add_seen(self, link: str, title: str, doi: str = None, source_id: str = None, author_ids: list[str] = None):
        """Mark a paper as seen and record its authors."""
        import time
        retries = 3
        for i in range(retries):
            try:
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'INSERT INTO seen_papers (link, doi, title, source_id) VALUES (?, ?, ?, ?)', 
                        (link, doi, title, source_id)
                    )
                    paper_id = cursor.lastrowid
                    
                    # Record authors for frequency tracking
                    if author_ids and paper_id:
                        for auth_id in author_ids:
                            if auth_id:
                                # Clean OpenAlex ID if full URL
                                clean_auth_id = auth_id.split("/")[-1]
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
                    logger.error(f"Database error after retries: {e}")
            except sqlite3.IntegrityError:
                # Normal if already exists
                break

    def get_promotable_journals(self, threshold: int = 3) -> list[str]:
        """Finds source_ids that have at least 'threshold' papers but aren't monitored yet."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        # Count papers per source_id that are NOT already in monitored_journals
        query = '''
            SELECT source_id, COUNT(*) as count 
            FROM seen_papers 
            WHERE source_id IS NOT NULL 
            AND source_id NOT IN (SELECT source_id FROM monitored_journals)
            GROUP BY source_id 
            HAVING count >= ?
        '''
        cursor.execute(query, (threshold,))
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def add_monitored_journal(self, source_id: str):
        """Promote a journal to monitored status."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO monitored_journals (source_id) VALUES (?)', (source_id,))
                conn.commit()
                logger.info(f"Journal {source_id} promoted to monitored list.")
        except Exception as e:
            logger.error(f"Error promoting journal {source_id}: {e}")

    def get_monitored_journals(self) -> list[str]:
        """Returns list of source_ids that have been promoted."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT source_id FROM monitored_journals')
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def get_promotable_authors(self, threshold: int = 3) -> list[str]:
        """Finds author_ids that appear in at least 'threshold' papers but aren't monitored yet."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        query = '''
            SELECT author_id, COUNT(*) as count 
            FROM paper_authors 
            WHERE author_id NOT IN (SELECT author_id FROM monitored_authors)
            GROUP BY author_id 
            HAVING count >= ?
        '''
        cursor.execute(query, (threshold,))
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    def add_monitored_author(self, author_id: str):
        """Promote an author to monitored status."""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO monitored_authors (author_id) VALUES (?)', (author_id,))
                conn.commit()
                logger.info(f"Author {author_id} promoted to monitored list.")
        except Exception as e:
            logger.error(f"Error promoting author {author_id}: {e}")

    def get_monitored_authors(self) -> list[str]:
        """Returns list of author_ids that have been promoted."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT author_id FROM monitored_authors')
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

db = Database()