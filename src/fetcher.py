import feedparser
from datetime import datetime
from dateutil import parser as date_parser
from typing import List
from src.config import RSS_FEEDS
from src.models import Paper
from src.logger import logger
from src.db import db

class Fetcher:
    def __init__(self, feeds: List[str] = RSS_FEEDS):
        self.feeds = feeds

    def fetch_all(self, ignore_seen: bool = False) -> List[Paper]:
        new_papers = []
        for feed_url in self.feeds:
            try:
                logger.info(f"Fetching feed: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                if feed.bozo:
                    logger.warning(f"Feed error for {feed_url}: {feed.bozo_exception}")
                    continue

                for entry in feed.entries:
                    link = entry.get('link', '')
                    if not link:
                        continue
                    
                    doi = self._extract_doi(entry)
                    if not ignore_seen and db.is_seen(link, doi):
                        continue

                    # Parse Date
                    published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
                    if published_parsed:
                        published_date = datetime(*published_parsed[:6])
                    else:
                        published_date = datetime.now() # Fallback

                    # Extract Authors
                    authors = []
                    summary_text = entry.get('summary', '') or entry.get('description', '')
                    
                    source = feed.feed.get('title', 'Unknown Journal')

                    # EXCLUSIONS: Zenodo, Figshare, Unknown Source
                    excluded_sources = ["Zenodo", "Figshare", "Unknown Source", "Unknown Journal"]
                    if any(excl in source for excl in excluded_sources):
                        logger.debug(f"Skipping RSS entry {entry.get('title', '')[:30]}... due to excluded source: {source}")
                        continue

                    if 'authors' in entry:
                        authors = [a.get('name', '') for a in entry.authors]
                    elif 'author' in entry:
                        author_str = entry.author
                        if ',' in author_str:
                            authors = [a.strip() for a in author_str.split(',')]
                        elif ';' in author_str:
                            authors = [a.strip() for a in author_str.split(';')]
                        else:
                            authors = [author_str.strip()]
                    elif 'author_detail' in entry:
                        authors = [entry.author_detail.get('name', '')]
                    
                    # Heuristic for Copernicus and others where authors are in the summary HTML
                    if not authors and summary_text:
                        # Often: <b>Title</b><br /> Authors <br /> Abstract
                        parts = summary_text.split('<br />')
                        if len(parts) >= 2:
                            # Second part might be authors
                            potential_authors = parts[1].strip()
                            # Basic check to see if it's not too long and doesn't look like abstract
                            if 0 < len(potential_authors) < 300:
                                if ',' in potential_authors:
                                    authors = [a.strip() for a in potential_authors.split(',')]
                                elif ';' in potential_authors:
                                    authors = [a.strip() for a in potential_authors.split(';')]
                                else:
                                    authors = [potential_authors]

                    # Clean abstract: remove Title and Authors if they are at the beginning
                    clean_abstract = summary_text
                    if '<br />' in clean_abstract:
                        parts = clean_abstract.split('<br />')
                        # If we have Title <br /> Authors <br /> Abstract, take everything from the 3rd part
                        if len(parts) >= 3:
                            clean_abstract = '<br />'.join(parts[2:]).strip()
                        elif len(parts) == 2:
                            clean_abstract = parts[1].strip()

                    paper = Paper(
                        title=entry.get('title', 'No Title'),
                        link=link,
                        published=published_date,
                        source=source,
                        abstract=clean_abstract,
                        authors=authors,
                        doi=self._extract_doi(entry),
                        type="article" # Default for RSS as most are journals
                    )
                    
                    new_papers.append(paper)
                    # Note: We don't mark as seen here yet. 
                    # We should mark as seen only after processing or explicitly.
                    # For now, to prevent refetching immediately if the script crashes, 
                    # we might want to separate "seen" from "processed", 
                    # but for simplicity let's rely on the main loop to save them.
                    
            except Exception as e:
                logger.error(f"Error processing feed {feed_url}: {e}")

        logger.info(f"Found {len(new_papers)} new papers.")
        return new_papers[:5] # Limit for testing

    def _extract_doi(self, entry) -> str:
        # Basic heuristic to find DOI in id or links
        if 'prism_doi' in entry:
            return entry.prism_doi
        if 'dc_identifier' in entry and 'doi' in entry.dc_identifier:
            return entry.dc_identifier.replace('doi:', '')
        
        # Check 'id' if it looks like a DOI URL or starts with doi:
        id_field = entry.get('id', '')
        if 'doi.org/' in id_field:
            return id_field.split('doi.org/')[-1]
        if id_field.startswith('doi:'):
            return id_field.replace('doi:', '')
            
        return None
