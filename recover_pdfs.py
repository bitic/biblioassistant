
import sqlite3
from pathlib import Path
from datetime import datetime
from src.config import DB_PATH, PAPERS_DIR, SUMMARIES_DIR
from src.extractor import Extractor
from src.synthesizer import Synthesizer
from src.generator import SiteGenerator
from src.models import Paper
from src.logger import logger

def recover_missing_elsevier_pdfs():
    extractor = Extractor()
    synthesizer = Synthesizer()
    generator = SiteGenerator()
    
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
            
        # Create a temporary Paper object for path generation
        paper = Paper(
            title=title,
            link=link,
            published=p_date,
            source="Recovery",
            abstract="",
            authors=[],
            doi=doi
        )
        
        year = p_date.strftime("%Y")
        filename_pdf = paper.to_filename().replace(".md", ".pdf")
        pdf_path = PAPERS_DIR / year / filename_pdf
        
        newly_downloaded = False
        if not pdf_path.exists():
            logger.info(f"PDF missing for: {title} ({doi}). Attempting recovery...")
            
            # Ensure directory exists
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            
            if extractor._download_from_elsevier(doi, pdf_path):
                logger.info(f"Successfully recovered: {filename_pdf}")
                recovered_count += 1
                newly_downloaded = True
            else:
                logger.warning(f"Failed to recover PDF for {doi}")
        
        # If we just downloaded it, or if it already existed but summary might be partial
        # We check if the summary exists and if it contains the "abstract only" warning
        filename_md = paper.to_filename()
        summary_path = SUMMARIES_DIR / year / filename_md
        
        needs_synthesis = newly_downloaded
        
        if not needs_synthesis and summary_path.exists():
            # Check if it was an abstract-only summary
            with open(summary_path, "r") as f:
                content = f.read()
                if "Warning:** This summary was generated from the **abstract only**" in content:
                    logger.info(f"Existing summary for {title} is abstract-only. Upgrading with full text.")
                    needs_synthesis = True

        if needs_synthesis and pdf_path.exists():
            logger.info(f"Synthesizing full-text summary for: {title}")
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
