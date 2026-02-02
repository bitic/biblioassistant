import requests
import fitz  # PyMuPDF
from pathlib import Path
from src.config import PAPERS_DIR, OPENALEX_EMAIL
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

    def _extract_from_html(self, paper: Paper, url: str = None) -> str:
        """
        Fetches the article's HTML and strips tags to get raw text.
        Handles meta-refreshes and basic JS redirects.
        """
        target_url = url if url else paper.link
        try:
            logger.info(f"Attempting HTML extraction from: {target_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }
            # Disable SSL verification to handle institutional repositories with cert issues
            response = requests.get(target_url, headers=headers, timeout=30, verify=False)
            
            if response.status_code == 200:
                html = response.text
                
                # Check for Meta Refresh Redirect
                # <meta http-equiv="refresh" content="0; url=http://example.com/" />
                meta_refresh = re.search(r'<meta[^>]*http-equiv=["\']?refresh["\']?[^>]*content=["\']?[^"\'>]*url=([^"\'>]+)["\']?', html, re.IGNORECASE)
                if meta_refresh:
                    redirect_url = meta_refresh.group(1).strip()
                    # Handle relative URLs
                    if not redirect_url.startswith(('http://', 'https://')):
                        from urllib.parse import urljoin
                        redirect_url = urljoin(target_url, redirect_url)
                        
                    logger.info(f"Following Meta Refresh to: {redirect_url}")
                    return self._extract_from_html(paper, url=redirect_url)

                # Check for basic JS Redirect (often used if meta refresh is absent)
                # window.location = "..." or window.location.href = "..."
                js_redirect = re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', html)
                if js_redirect:
                    redirect_url = js_redirect.group(1).strip()
                    if not redirect_url.startswith(('http://', 'https://')):
                        from urllib.parse import urljoin
                        redirect_url = urljoin(target_url, redirect_url)
                        
                    logger.info(f"Following JS Redirect to: {redirect_url}")
                    return self._extract_from_html(paper, url=redirect_url)

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
        1. Try direct link (with heuristics).
        2. If failed, try Unpaywall API to find OA PDF.
        """
        # Strategy 1: Direct Link (Existing Heuristics)
        if self._try_download_url(paper.link, save_path, paper):
            return True
            
        # Strategy 2: Unpaywall API
        if paper.doi:
            logger.info(f"Direct download failed. Checking Unpaywall for OA PDF (DOI: {paper.doi})")
            oa_url = self._get_unpaywall_url(paper.doi)
            if oa_url:
                logger.info(f"Unpaywall found PDF URL: {oa_url}")
                if self._try_download_url(oa_url, save_path, paper):
                    return True
        
        return False

    def _get_unpaywall_url(self, doi: str) -> str:
        """Queries Unpaywall API for a direct PDF link."""
        try:
            email = OPENALEX_EMAIL or "unpaywall@example.com"
            url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                best_oa = data.get("best_oa_location", {})
                if best_oa and best_oa.get("url_for_pdf"):
                    return best_oa.get("url_for_pdf")
            return ""
        except Exception as e:
            logger.warning(f"Unpaywall check failed: {e}")
            return ""

    def _try_download_url(self, target_url: str, save_path: Path, paper: Paper) -> bool:
        """Helper to attempt a download from a specific URL."""
        # Heuristics for specific publishers
        if "wiley.com" in target_url:
            if "/abs/" in target_url:
                target_url = target_url.replace("/abs/", "/pdfdirect/")
            elif "/doi/" in target_url and "/pdf/" not in target_url:
                doi_part = target_url.split("/doi/")[-1].split("?")[0]
                target_url = f"https://agupubs.onlinelibrary.wiley.com/doi/pdfdirect/{doi_part}"
        
        # Heuristic for ScienceDirect / Elsevier (PII)
        if "sciencedirect.com" in target_url or "linkinghub.elsevier.com" in target_url:
             try:
                if "/pii/" not in target_url:
                     r = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, stream=True)
                     target_url = r.url
             except:
                pass
             if "/pii/" in target_url:
                import re
                pii_match = re.search(r'/pii/([A-Z0-9]+)', target_url)
                if pii_match:
                    pii = pii_match.group(1)
                    target_url = f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?isDTM=0&download=true"

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
            
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(target_url, headers=headers, stream=True, timeout=45, verify=False)
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
