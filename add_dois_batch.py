import sys
import os

# Add the current directory to sys.path to allow imports from src
sys.path.append(os.getcwd())

from src.discovery import Discovery
from src.extractor import Extractor
from src.synthesizer import Synthesizer
from src.generator import SiteGenerator
from src.db import db
from src.logger import logger
from src.config import MAX_MONTHLY_COST, SYNTHESIS_ENGINE

def main():
    if not os.path.exists("dois_to_add.txt"):
        print("Error: dois_to_add.txt not found.")
        return

    with open("dois_to_add.txt", "r") as f:
        dois = [line.strip() for line in f if line.strip()]

    discovery = Discovery()
    extractor = Extractor()
    synthesizer = Synthesizer()

    total = len(dois)
    success_count = 0
    skipped_count = 0
    error_count = 0

    logger.info(f"Starting batch processing of {total} DOIs...")

    for i, doi in enumerate(dois):
        logger.info(f"[{i+1}/{total}] Processing DOI: {doi}")
        
        # 1. Fetch Metadata
        try:
            # Clean DOI if it has extra characters
            clean_doi = doi.strip().rstrip('.')
            papers = discovery.fetch_by_doi(clean_doi, ignore_seen=True)
            if not papers:
                logger.error(f"Metadata not found for DOI: {clean_doi}")
                error_count += 1
                continue
            
            paper = papers[0]
            
            # Check if already in DB (seen)
            if db.is_seen(paper.link, paper.doi):
                logger.info(f"Paper already in DB: {paper.title}. Skipping.")
                skipped_count += 1
                continue
            
            # 2. Force Relevance
            paper.is_relevant = True
            paper.relevance_reason = "Manually added in batch."

            # 3. Extract Text
            logger.info(f"Extracting text for: {paper.title}")
            full_text, is_full_text = extractor.process(paper)
            if not full_text:
                logger.warning(f"No text extracted for {clean_doi}. Skipping synthesis.")
                error_count += 1
                continue

            # 4. Synthesize
            # Check budget
            active_engine = SYNTHESIS_ENGINE
            current_cost = db.get_monthly_cost()
            if current_cost >= MAX_MONTHLY_COST:
                logger.warning(f"Budget exceeded ({current_cost:.2f} >= {MAX_MONTHLY_COST}). Using local synthesis.")
                active_engine = "ollama"
            
            original_engine = synthesizer.engine
            synthesizer.engine = active_engine
            
            logger.info(f"Synthesizing summary using {active_engine}...")
            if synthesizer.synthesize(paper, full_text, is_full_text):
                success_count += 1
                
                # Use backfill logic: set processed_date to publication date 
                # to avoid showing these papers as 'new' in the RSS feed.
                p_date = paper.published.strftime("%Y-%m-%d %H:%M:%S")
                
                db.add_seen(
                    link=paper.link, 
                    title=paper.title, 
                    doi=paper.doi, 
                    source_id=paper.source_id, 
                    author_ids=paper.author_ids, 
                    processed_date=p_date,
                    is_relevant=True, 
                    relevance_reason=paper.relevance_reason,
                    authors_data=paper.authors_data,
                    h_index=paper.journal_h_index,
                    impact_factor=paper.journal_impact,
                    type=paper.type,
                    source_url=paper.source_url
                )
                logger.info(f"Successfully processed: {paper.title}")
            else:
                logger.error(f"Synthesis failed for: {clean_doi}")
                error_count += 1
            
            synthesizer.engine = original_engine

        except Exception as e:
            logger.error(f"Unexpected error processing DOI {doi}: {e}", exc_info=True)
            error_count += 1

    logger.info(f"Batch processing complete. Total: {total}, Success: {success_count}, Skipped: {skipped_count}, Errors: {error_count}")
    
    if success_count > 0:
        logger.info("Regenerating site...")
        generator = SiteGenerator()
        generator.build()
        logger.info("Site regeneration complete.")

if __name__ == "__main__":
    main()
