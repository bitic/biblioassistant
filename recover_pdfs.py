
import sqlite3
from pathlib import Path
from datetime import datetime
from src.config import DB_PATH, PAPERS_DIR, SUMMARIES_DIR
from src.extractor import Extractor
from src.synthesizer import Synthesizer
from src.generator import SiteGenerator
from src.discovery import Discovery
from src.models import Paper
from src.logger import logger

def recover_missing_elsevier_pdfs():
    extractor = Extractor()
    synthesizer = Synthesizer()
    generator = SiteGenerator()
    discovery = Discovery()
    
    # 1. Connect to DB to find Elsevier papers
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Target Elsevier DOIs specifically
    query = "SELECT doi, link, title, processed_date FROM seen_papers WHERE doi LIKE '10.1016%'"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    logger.info(f"Found {len(rows)} Elsevier records in database. Checking for missing PDFs...")
    
    recovered_count = 0
    synthesized_count = 0
    
    for row in rows:
        doi = row['doi']
        link = row['link']
        title = row['title']
        
        # Parse date to find the correct directory
        try:
            p_date = datetime.strptime(row['processed_date'], "%Y-%m-%d %H:%M:%S")
        except:
            p_date = datetime.now()
            
        # Check if PDF exists
        year = p_date.strftime("%Y")
        # Temporary paper object for filename generation
        temp_paper = Paper(title=title, link=link, published=p_date, source="Recovery", doi=doi)
        filename_pdf = temp_paper.to_filename().replace(".md", ".pdf")
        pdf_path = PAPERS_DIR / year / filename_pdf
        
        filename_md = temp_paper.to_filename()
        summary_path = SUMMARIES_DIR / year / filename_md
        
        newly_downloaded = False
        if not pdf_path.exists():
            logger.info(f"PDF missing for: {title} ({doi}). Attempting recovery...")
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            if extractor._download_from_elsevier(doi, pdf_path):
                logger.info(f"Successfully recovered: {filename_pdf}")
                recovered_count += 1
                newly_downloaded = True
        
        needs_synthesis = newly_downloaded
        if not needs_synthesis and summary_path.exists():
            with open(summary_path, "r") as f:
                content = f.read()
                if "Warning:** This summary was generated from the **abstract only**" in content:
                    logger.info(f"Existing summary for {title} is abstract-only. Upgrading.")
                    needs_synthesis = True

        if needs_synthesis and pdf_path.exists():
            # FETCH FULL METADATA to avoid "Unknown" authors
            logger.info(f"Fetching full metadata for {doi} to ensure author names are correct...")
            meta_papers = discovery.fetch_by_doi(doi)
            if meta_papers:
                paper = meta_papers[0]
                # Ensure date matches what's in DB for directory consistency
                paper.published = p_date 
            else:
                logger.warning(f"Could not fetch metadata for {doi}. Using database fields.")
                paper = temp_paper

            logger.info(f"Synthesizing full-text summary for: {paper.title}")
            full_text = extractor._extract_text(pdf_path)
            if full_text:
                if synthesizer.synthesize(paper, full_text, is_full_text=True):
                    synthesized_count += 1
            else:
                logger.warning(f"Could not extract text from recovered PDF: {pdf_path}")

    logger.info(f"Recovery complete. Recovered {recovered_count} PDFs, regenerated {synthesized_count} summaries.")
    
    if synthesized_count > 0:
        logger.info("Building site to reflect changes...")
        generator.build()

if __name__ == "__main__":
    recover_missing_elsevier_pdfs()
