import argparse
import subprocess
from src.config import REMOTE_HOST, REMOTE_USER, REMOTE_PATH, PUBLIC_DIR
from src.fetcher import Fetcher
from src.discovery import Discovery
from src.filter import LocalFilter
from src.extractor import Extractor
from src.synthesizer import Synthesizer
from src.generator import SiteGenerator
from src.db import db
from src.logger import logger

def deploy():
    """Rsync the public directory to the remote server."""
    if not all([REMOTE_HOST, REMOTE_USER, REMOTE_PATH]):
        logger.error("Remote configuration missing. Cannot deploy.")
        return

    # Ensure local path ends with slash to copy contents, not the directory itself
    local_path = str(PUBLIC_DIR) + "/"
    
    # Construct remote destination
    # rsync user@host:path
    remote_dest = f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"

    cmd = [
        "rsync", "-avz", "--delete",
        "-e", "ssh", # Explicitly use ssh
        local_path,
        remote_dest
    ]
    
    logger.info(f"Deploying to {remote_dest}...")
    try:
        subprocess.run(cmd, check=True)
        logger.info("Deployment successful!")
    except subprocess.CalledProcessError as e:
        logger.error(f"Deployment failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="BiblioAssistant Pipeline")
    parser.add_argument("--deploy", action="store_true", help="Deploy to remote server after generation")
    parser.add_argument("--force-all", action="store_true", help="Ignore 'seen' DB (use with caution)")
    parser.add_argument("--generate-only", action="store_true", help="Skip fetch/filter/synthesize and only generate the site")
    parser.add_argument("--rss", action="store_true", help="Enable legacy RSS feeds (default: False)")
    parser.add_argument("--add-doi", type=str, help="Manually add a single paper by DOI")
    parser.add_argument("--backfill", type=int, help="Number of days to go back for discovery (overrides last run date)")
    args = parser.parse_args()

    if args.generate_only:
        logger.info("Skipping fetch/filter/synthesis. Running generator only.")
        generator = SiteGenerator()
        generator.build()
        if args.deploy:
            deploy()
        return

    # Initialize components
    fetcher = Fetcher()
    
    # Calculate backfill date if requested
    from_date_override = None
    if args.backfill:
        from datetime import datetime, timedelta
        from_date_override = (datetime.now() - timedelta(days=args.backfill)).strftime("%Y-%m-%d")
        logger.info(f"Backfill requested: {args.backfill} days (Starting from {from_date_override})")

    discovery = Discovery(from_date=from_date_override)
    local_filter = LocalFilter()
    extractor = Extractor()
    synthesizer = Synthesizer()

    # 1. Fetch & Discover
    papers = []
    
    if args.add_doi:
        logger.info(f"Manual mode: Fetching metadata for DOI {args.add_doi}")
        manual_papers = discovery.fetch_by_doi(args.add_doi)
        if manual_papers:
            # For manual mode, we force relevance to True to skip filter
            p = manual_papers[0]
            p.is_relevant = True
            p.relevance_reason = "Manually added by user."
            papers = [p]
        else:
            msg = f"Could not find metadata for DOI {args.add_doi}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return
    else:
        rss_papers = []
        if args.rss:
            logger.info("RSS feeds enabled.")
            rss_papers = fetcher.fetch_all(ignore_seen=args.force_all)
        
        discovered_papers = discovery.run_all_tasks(ignore_seen=args.force_all)
        papers = rss_papers + discovered_papers
    
    if not papers:
        logger.info("No new papers found.")
    
    total_discovered = len(papers)
    relevant_count = 0
    processed_count = 0
    start_cost = db.get_monthly_cost()

    from src.config import MAX_MONTHLY_COST, SYNTHESIS_ENGINE
    current_monthly_cost = start_cost
    
    # Check budget before starting
    active_engine = SYNTHESIS_ENGINE
    if current_monthly_cost >= MAX_MONTHLY_COST:
        logger.warning(f"Monthly budget exceeded ({current_monthly_cost:.2f}€ >= {MAX_MONTHLY_COST:.2f}€). Switching to local Ollama synthesis.")
        active_engine = "ollama"

    for paper in papers:
        # 2. Filter
        # Check if already seen unless --force-all or --add-doi is used
        if not args.force_all and not args.add_doi and db.is_seen(paper.link, paper.doi):
            continue

        # Skip filter if manually added or if it passes relevance
        if args.add_doi or local_filter.check_relevance(paper):
            relevant_count += 1
            
            # Check budget during run (if using paid API)
            if active_engine == "gemini-api" and db.get_monthly_cost() >= MAX_MONTHLY_COST:
                msg = f"Monthly budget reached during run ({db.get_monthly_cost():.2f}€). Switching to local synthesis for remaining papers."
                logger.warning(msg)
                db.add_event("BUDGET_WARNING", msg)
                active_engine = "ollama"

            # 3. Extract
            full_text, is_full_text = extractor.process(paper)
            
            if full_text:
                # 4. Synthesize
                # Temporarily override engine if budget exceeded
                original_engine = synthesizer.engine
                synthesizer.engine = active_engine
                
                if synthesizer.synthesize(paper, full_text, is_full_text):
                    processed_count += 1
                    # Mark as seen in DB only after successful processing
                    db.add_seen(paper.link, paper.title, paper.doi, paper.source_id, paper.author_ids)
                
                synthesizer.engine = original_engine
            else:
                msg = f"Skipping synthesis for {paper.title} due to missing text."
                logger.warning(msg)
                db.add_event("WARNING", msg)
        else:
            # Mark irrelevant papers as seen too, so we don't re-check them
            db.add_seen(paper.link, paper.title, paper.doi, paper.source_id, paper.author_ids)

    end_cost = db.get_monthly_cost()
    run_cost = end_cost - start_cost
    
    msg = f"Pipeline finished. Found {total_discovered} papers, {relevant_count} were relevant, {processed_count} successfully synthesized. Run cost: {run_cost:.4f}€. Monthly total: {end_cost:.2f}€."
    logger.info(msg)
    db.add_event("SUMMARY", msg)

    # 5. Journal Promotion Logic
    promotable_journals = db.get_promotable_journals(threshold=3)
    if promotable_journals:
        # Get existing journal IDs from config to avoid double monitoring
        from src.config import DISCOVERY_TASKS
        existing_journal_ids = []
        for task in DISCOVERY_TASKS:
            if task['type'] == "journal":
                existing_journal_ids.extend(task['id'].split('|'))
        
        for source_id in promotable_journals:
            if source_id not in existing_journal_ids:
                db.add_monitored_journal(source_id)
                msg = f"Journal {source_id} reached relevance threshold and is now being automatically monitored."
                logger.info(msg)
                db.add_event("PROMOTION", msg)

    # 6. Author Promotion Logic
    promotable_authors = db.get_promotable_authors(threshold=3)
    if promotable_authors:
        # Get existing author IDs from config to avoid double monitoring
        from src.config import DISCOVERY_TASKS
        existing_author_ids = []
        for task in DISCOVERY_TASKS:
            if task['type'] in ["author", "author_citations"]:
                existing_author_ids.append(task['id'])
        
        for author_id in promotable_authors:
            if author_id not in existing_author_ids:
                db.add_monitored_author(author_id)
                msg = f"Author {author_id} reached relevance threshold and is now being automatically monitored."
                logger.info(msg)
                db.add_event("PROMOTION", msg)

    # 7. Generate Site
    generator = SiteGenerator()
    generator.build()

    # 8. Deploy (Optional)
    if args.deploy:
        deploy()

if __name__ == "__main__":
    main()
