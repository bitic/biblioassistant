import sqlite3
import time
from pathlib import Path
from src.config import DB_PATH
from src.logger import logger
from typing import Optional, List, Dict
from contextlib import contextmanager

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections to ensure they are always closed."""
        conn = sqlite3.connect(self.db_path, timeout=60)
        try:
            conn.execute('PRAGMA busy_timeout=60000;')
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize the database schema and handle migrations."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # TRUNCATE is safer than WAL on NFS but faster than DELETE
            cursor.execute('PRAGMA journal_mode=TRUNCATE;')
            cursor.execute('PRAGMA busy_timeout=60000;')
            
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
            
            # 2. Migration: Add columns if they don't exist
            cursor.execute("PRAGMA table_info(seen_papers)")
            columns = [row[1] for row in cursor.fetchall()]
            for col, col_type in [
                ('source_id', 'TEXT'),
                ('type', 'TEXT'),
                ('source_url', 'TEXT'),
                ('is_relevant', 'INTEGER DEFAULT 0'),
                ('relevance_reason', 'TEXT')
            ]:
                if col not in columns:
                    logger.info(f"Migrating database: adding {col} column to seen_papers.")
                    cursor.execute(f'ALTER TABLE seen_papers ADD COLUMN {col} {col_type}')

            # Migration for journals table (checking existence first)
            cursor.execute("CREATE TABLE IF NOT EXISTS journals (id TEXT PRIMARY KEY, name TEXT)")
            cursor.execute("PRAGMA table_info(journals)")
            j_columns = [row[1] for row in cursor.fetchall()]
            for col, col_type in [
                ('url', 'TEXT'),
                ('issn', 'TEXT'),
                ('h_index', 'INTEGER'),
                ('impact_factor', 'REAL'),
                ('added_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            ]:
                if col not in j_columns:
                    logger.info(f"Migrating database: adding {col} column to journals.")
                    cursor.execute(f'ALTER TABLE journals ADD COLUMN {col} {col_type}')

            # 3. Create Supporting Tables
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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()

    def get_metadata(self, key: str, default: str = None) -> Optional[str]:
        """Fetch a value from the metadata table."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM metadata WHERE key = ?', (key,))
            result = cursor.fetchone()
            return result[0] if result else default

    def set_metadata(self, key: str, value: str):
        """Store a value in the metadata table."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP',
                    (key, str(value))
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error setting metadata {key}: {e}")

    def get_last_run_date(self) -> Optional[str]:
        """Returns the date of the last successful pipeline run."""
        return self.get_metadata("last_run_date")

    def update_last_run_date(self, date_str: str = None):
        """Updates the last run date to today or a specific date."""
        if not date_str:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
        self.set_metadata("last_run_date", date_str)

    def is_seen(self, link: str, doi: str = None) -> bool:
        """Check if a paper has already been processed."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if doi:
                cursor.execute('SELECT 1 FROM seen_papers WHERE link = ? OR doi = ?', (link, doi))
            else:
                cursor.execute('SELECT 1 FROM seen_papers WHERE link = ?', (link,))
            result = cursor.fetchone()
            return result is not None

    def get_all_processed_dates(self) -> dict:
        """Returns a dictionary mapping link -> processed_date (datetime object)."""
        from datetime import datetime
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT link, processed_date FROM seen_papers')
            rows = cursor.fetchall()
            
            results = {}
            for link, date_str in rows:
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                        results[link] = dt
                    except ValueError:
                        pass
            return results

    def get_journal_urls(self) -> dict:
        """Returns a mapping of paper_link -> (source_id, source_url)."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT link, source_id, source_url FROM seen_papers WHERE source_url IS NOT NULL')
            rows = cursor.fetchall()
            return {row[0]: (row[1], row[2]) for row in rows}

    def get_distinct_journal_urls(self) -> dict:
        """Returns a mapping of source_id -> source_url."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_id, source_url FROM seen_papers WHERE source_url IS NOT NULL")
            return {row[0]: row[1] for row in cursor.fetchall() if row[0]}

    def add_seen(self, link: str, title: str, doi: str = None, source_id: str = None, author_ids: list[str] = None, processed_date: str = None, type: str = None, source_url: str = None, is_relevant: bool = False, relevance_reason: str = None, authors_data: dict = None, h_index: int = None, impact_factor: float = None):
        """Mark a paper as seen and record its authors, journal and relevance status."""
        rel_int = 1 if is_relevant else 0
        retries = 5
        for i in range(retries):
            try:
                with self._get_conn() as conn:
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
                    
                    # Record journal metadata if available
                    if source_id:
                        clean_sid = source_id.split("/")[-1]
                        cursor.execute(
                            '''
                            INSERT INTO journals (id, url, h_index, impact_factor) VALUES (?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET 
                                url=COALESCE(excluded.url, journals.url),
                                h_index=COALESCE(excluded.h_index, journals.h_index),
                                impact_factor=COALESCE(excluded.impact_factor, journals.impact_factor)
                            ''',
                            (clean_sid, source_url, h_index, impact_factor)
                        )

                    # Record authors
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
                return # Success
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and i < retries - 1:
                    time.sleep(2**i) # Exponential backoff
                else:
                    logger.error(f"Database error in add_seen: {e}")
                    break

    def get_recent_papers_by_days(self, days: int = 7) -> list:
        """Returns list of papers processed in the last X days for filter audit."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT title, link, doi, processed_date, is_relevant, relevance_reason
                FROM seen_papers
                WHERE processed_date >= datetime('now', ?)
                ORDER BY processed_date DESC
            ''', (f'-{days} days',))
            rows = cursor.fetchall()
            return [{'title': r['title'], 'link': r['link'], 'doi': r['doi'], 'date': r['processed_date'], 'is_relevant': bool(r['is_relevant']), 'relevance_reason': r['relevance_reason']} for r in rows]

    def add_event(self, event_type: str, message: str):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO events (event_type, message) VALUES (?, ?)', (event_type, message))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding event: {e}")

    def get_recent_events(self, limit: int = 50) -> list:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT event_type, message, timestamp FROM events ORDER BY timestamp DESC LIMIT ?', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int, cost: float):
        """Record LLM API usage and cost."""
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO usage (model, prompt_tokens, completion_tokens, total_tokens, cost) VALUES (?, ?, ?, ?, ?)',
                    (model, prompt_tokens, completion_tokens, total_tokens, cost)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording usage: {e}")

    def get_monthly_cost(self) -> float:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(cost) FROM usage WHERE timestamp >= date('now', 'start of month')")
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0.0

    def get_promotable_journals(self, threshold: int = 5) -> list:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_id, COUNT(*) as count
                FROM seen_papers
                WHERE is_relevant = 1 AND source_id IS NOT NULL
                AND source_id NOT IN (SELECT source_id FROM monitored_journals)
                GROUP BY source_id HAVING count >= ?
                ORDER BY count DESC
            ''', (threshold,))
            return [row[0] for row in cursor.fetchall()]

    def add_monitored_journal(self, source_id: str):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO monitored_journals (source_id) VALUES (?)', (source_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding monitored journal: {e}")

    def get_monitored_journals(self) -> list[str]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT source_id FROM monitored_journals')
            return [row[0] for row in cursor.fetchall()]

    def get_promotable_authors(self, threshold: int = 5) -> list:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pa.author_id, COUNT(*) as count
                FROM paper_authors pa
                JOIN seen_papers p ON pa.paper_id = p.id
                WHERE p.is_relevant = 1
                AND pa.author_id NOT IN (SELECT author_id FROM monitored_authors)
                GROUP BY pa.author_id HAVING count >= ?
                ORDER BY count DESC
            ''', (threshold,))
            return [row[0] for row in cursor.fetchall()]

    def add_monitored_author(self, author_id: str):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO monitored_authors (author_id) VALUES (?)', (author_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding monitored author: {e}")

    def get_monitored_authors(self) -> list[str]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT author_id FROM monitored_authors')
            return [row[0] for row in cursor.fetchall()]

    def get_all_authors(self) -> list:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pa.author_id, COALESCE(a.name, pa.author_id) as name, COUNT(pa.paper_id) as count
                FROM paper_authors pa
                LEFT JOIN authors a ON pa.author_id = a.id
                GROUP BY pa.author_id
                ORDER BY name ASC
            ''')
            rows = cursor.fetchall()
            return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]

    def get_all_journals(self) -> list:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.source_id, COALESCE(j.name, p.source_id) as name, COUNT(p.id) as count, j.url
                FROM seen_papers p
                LEFT JOIN journals j ON p.source_id = j.id
                WHERE p.source_id IS NOT NULL AND p.is_relevant = 1
                GROUP BY p.source_id
                ORDER BY name ASC
            ''')
            rows = cursor.fetchall()
            return [{"id": r[0], "name": r[1], "count": r[2], "url": r[3]} for r in rows]

    def get_all_paper_authors(self) -> dict:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.link, pa.author_id, a.name
                FROM paper_authors pa
                JOIN seen_papers p ON pa.paper_id = p.id
                LEFT JOIN authors a ON pa.author_id = a.id
            ''')
            rows = cursor.fetchall()
            results = {}
            for link, aid, name in rows:
                if link not in results: results[link] = []
                results[link].append({"id": aid, "name": name or aid})
            return results

    def get_all_paper_journals(self) -> dict:
        """Returns mapping of link -> {id, name, url}."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.link, p.source_id, j.name, j.url
                FROM seen_papers p
                LEFT JOIN journals j ON p.source_id = j.id
                WHERE p.source_id IS NOT NULL
            ''')
            rows = cursor.fetchall()
            return {r[0]: {"id": r[1], "name": r[2] or r[1], "url": r[3]} for r in rows}

db = Database()
