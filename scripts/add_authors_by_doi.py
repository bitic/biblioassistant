import sys
from pathlib import Path

# Add project root to sys.path to allow imports from src
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from src.discovery import Discovery
from src.db import db
from src.logger import logger

def add_authors_from_doi(doi):
    discovery = Discovery()
    logger.info(f"Fetching metadata for DOI: {doi}")
    
    # Clean DOI if it's a full URL
    clean_doi = doi.replace("https://doi.org/", "").strip()
    
    papers = discovery.fetch_by_doi(clean_doi, ignore_seen=True)
    
    if not papers:
        logger.error(f"No papers found for DOI: {doi}")
        return

    paper = papers[0]
    print(f"
Found paper: {paper.title}")
    print(f"Authors: {', '.join(paper.authors)}")
    
    if not paper.author_ids:
        print("No author IDs found for this paper.")
        return

    print(f"
Adding {len(paper.author_ids)} authors to monitored list...")
    count = 0
    for auth_id in paper.author_ids:
        # Check if already monitored to avoid redundant logs
        monitored = db.get_monitored_authors()
        if auth_id not in monitored:
            db.add_monitored_author(auth_id)
            count += 1
    
    print(f"Successfully added {count} new authors to the database.")
    print(f"Total authors now monitored in DB: {len(db.get_monitored_authors())}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run scripts/add_authors_by_doi.py <DOI>")
        sys.exit(1)
    
    for doi in sys.argv[1:]:
        add_authors_from_doi(doi)
