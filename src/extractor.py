import requests
import fitz  # PyMuPDF
from pathlib import Path
from src.config import PAPERS_DIR
from src.models import Paper
from src.logger import logger

import re

class Extractor:
    def process(self, paper: Paper) -> tuple[str, bool]:
        """
        Downloads the PDF (if possible) and extracts text.
        Returns (full_text_content, is_full_text_boolean).
        """
        # Determine paths
        year = paper.published.strftime("%Y")
        save_dir = PAPERS_DIR / year
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filename = paper.to_filename().replace(".md", ".pdf")
        pdf_path = save_dir / filename
        
        # 1. Download PDF if not exists
        if not pdf_path.exists():
            self._download_pdf(paper, pdf_path)

        text = ""
        is_full_text = False

        # 2. Extract text (PDF > HTML > Abstract)
        if pdf_path.exists():
            logger.info(f"Processing PDF: {pdf_path}")
            paper.pdf_link = str(pdf_path) # Store local path
            text = self._extract_text(pdf_path)
            if text:
                is_full_text = True
        
        if not text:
            logger.warning(f"PDF text extraction failed or PDF missing for {paper.title}. Trying HTML fallback.")
            text = self._extract_from_html(paper)
            if text:
                is_full_text = True

        if not text:
             # If both fail, fallback to abstract
             logger.warning(f"No text extracted for {paper.title}. Using Abstract.")
             return paper.abstract, False
             
        return text, is_full_text

    def _extract_from_html(self, paper: Paper) -> str:
        """
        Fetches the article's HTML and strips tags to get raw text.
        """
        try:
            logger.info(f"Attempting HTML extraction from: {paper.link}")
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = requests.get(paper.link, headers=headers, timeout=30)
            
            if response.status_code == 200:
                html = response.text
                
                # Basic cleaning
                # 1. Remove scripts and styles
                html = re.sub(r'<(script|style).*?</\1>', ' ', html, flags=re.DOTALL)
                # 2. Remove comments
                html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
                # 3. Remove HTML tags
                text = re.sub(r'<[^>]+>', ' ', html)
                # 4. Collapse whitespace
                text = re.sub(r'\s+', ' ', text).strip()
                
                if len(text) < 500:
                    logger.warning(f"HTML extraction too short ({len(text)} chars). Likely a block or redirect.")
                    return ""

                logger.info(f"Extracted {len(text)} chars from HTML.")
                return text
            else:
                logger.warning(f"HTML fetch failed: {response.status_code}")
                return ""
        except Exception as e:
            logger.error(f"HTML extraction error: {e}")
            return ""

    def _download_pdf(self, paper: Paper, save_path: Path) -> bool:
        """
        Attempts to download the PDF.
        This is a 'best effort' implementation. 
        """
        target_url = paper.link
        
        # Heuristics for specific publishers
        if "wiley.com" in target_url:
            if "/abs/" in target_url:
                target_url = target_url.replace("/abs/", "/pdfdirect/")
            elif "/doi/" in target_url and "/pdf/" not in target_url:
                # Try to construct direct PDF link
                doi_part = target_url.split("/doi/")[-1].split("?")[0]
                target_url = f"https://agupubs.onlinelibrary.wiley.com/doi/pdfdirect/{doi_part}"
        
        try:
            logger.info(f"Attempting to download PDF from: {target_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": paper.link,
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            response = requests.get(target_url, headers=headers, stream=True, timeout=45)
            
            # Some publishers return 200 but it's a cookie wall page
            content_type = response.headers.get("Content-Type", "").lower()
            
            if response.status_code == 200 and "application/pdf" in content_type:
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded PDF to {save_path}")
                return True
            else:
                logger.warning(f"Failed to download PDF (Status: {response.status_code}, Type: {content_type})")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False

    def _extract_text(self, pdf_path: Path) -> str:
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            
            # Basic cleanup (remove too much whitespace)
            return " ".join(text.split())
            
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return ""
