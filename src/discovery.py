import requests
from datetime import datetime
from typing import List
from src.config import OPENALEX_EMAIL, DISCOVERY_TASKS
from src.models import Paper
from src.logger import logger
from src.db import db

class Discovery:
    def __init__(self, email: str = OPENALEX_EMAIL, from_date: str = None, to_date: str = None):
        self.base_url = "https://api.openalex.org/works"
        self.params = {"mailto": email} if email else {}
        
        # Determine Start Date: Priority override -> Last run from DB -> fallback to 90 days
        from datetime import timedelta
        if from_date:
            self.from_date = from_date
            logger.info(f"Discovery starting from override date: {self.from_date}")
        else:
            last_run = db.get_last_run_date()
            if last_run:
                self.from_date = last_run
                logger.info(f"Discovery starting from last run date: {self.from_date}")
            else:
                self.from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                logger.info(f"First run detected. Discovery starting from fallback date: {self.from_date}")
            
        # Determine End Date: Override -> Today + 7 days (safety margin)
        if to_date:
            self.to_date = to_date
            logger.info(f"Discovery ending at override date: {self.to_date}")
        else:
            self.to_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    def run_all_tasks(self, ignore_seen: bool = False) -> List[Paper]:
        """Executes all discovery tasks defined in config and DB."""
        all_new_papers = []
        
        # Merge config tasks with automatically promoted journals/authors from DB
        tasks = DISCOVERY_TASKS.copy()
        
        auto_journals = db.get_monitored_journals()
        if auto_journals:
            tasks.append({
                "name": "Auto-Promoted Journals",
                "type": "journal",
                "id": "|".join(auto_journals)
            })
            
        auto_authors = db.get_monitored_authors()
        if auto_authors:
            # We can use OR (|) operator for author IDs too
            tasks.append({
                "name": "Auto-Promoted Authors",
                "type": "author",
                "id": "|".join(auto_authors)
            })

        for task in tasks:
            logger.info(f"Running discovery task: {task['name']} ({task['type']})")
            papers = []
            
            if task['type'] == "search":
                papers = self.search_by_keywords(task['query'])
            elif task['type'] == "author":
                papers = self.search_by_author(task['id'])
            elif task['type'] == "citation":
                papers = self.search_by_doi_citation(task['doi'])
            elif task['type'] == "author_citations":
                papers = self.search_citations_for_author(task['id'])
            elif task['type'] == "journal":
                papers = self.search_by_journal(task['id'])
            elif task['type'] == "issn":
                papers = self.search_by_issn(task['issn'])
            
            # Filter duplicates and seen papers
            for paper in papers:
                if not ignore_seen and db.is_seen(paper.link, paper.doi):
                    continue
                all_new_papers.append(paper)
        
        logger.info(f"Discovery complete. Found {len(all_new_papers)} potential new papers.")
        return all_new_papers

    def search_citations_for_author(self, author_id: str) -> List[Paper]:
        """First gets all works by author, then finds works that cite them."""
        import time
        logger.info(f"Automatically finding citations for author ID: {author_id} (Range: {self.from_date} to {self.to_date})")
        
        # 1. Get all OpenAlex IDs for this author
        params = self.params.copy()
        params.update({
            "filter": f"author.id:{author_id}",
            "select": "id",
            "per_page": 100 
        })
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            ids = [work.get("id").split("/")[-1] for work in data.get("results", []) if work.get("id")]
            
            logger.info(f"Found {len(ids)} papers for author. Checking their recent citations in batches...")
            
            all_citing_papers = []
            # 2. Batch search for citations (OpenAlex supports up to 50 IDs per filter with |)
            batch_size = 50
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i + batch_size]
                logger.info(f"Checking citations for batch {i//batch_size + 1}/{(len(ids)-1)//batch_size + 1}...")
                
                batch_filter = "|".join(batch)
                citing = self.search_by_citing_id(batch_filter)
                all_citing_papers.extend(citing)
                
                # Polite delay
                time.sleep(0.5)
            
            return all_citing_papers
            
        except Exception as e:
            logger.error(f"Error in author citation discovery: {e}")
            return []

    def search_by_keywords(self, query: str) -> List[Paper]:
        params = self.params.copy()
        params.update({
            "filter": f"title_and_abstract.search:{query},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
            "sort": "publication_date:desc",
            "per_page": 20
        })
        return self._fetch_openalex(params)

    def search_by_author(self, author_id: str) -> List[Paper]:
        params = self.params.copy()
        params.update({
            "filter": f"author.id:{author_id},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
            "sort": "publication_date:desc",
            "per_page": 10
        })
        return self._fetch_openalex(params)

    def search_by_journal(self, source_id: str) -> List[Paper]:
        params = self.params.copy()
        params.update({
            "filter": f"primary_location.source.id:{source_id},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
            "sort": "publication_date:desc",
            "per_page": 50
        })
        return self._fetch_openalex(params)

    def search_by_issn(self, issn: str) -> List[Paper]:
        params = self.params.copy()
        params.update({
            "filter": f"primary_location.source.issn:{issn},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
            "sort": "publication_date:desc",
            "per_page": 50
        })
        return self._fetch_openalex(params)

    def search_by_doi_citation(self, doi: str) -> List[Paper]:
        """Search by DOI: first resolve DOI to OpenAlex ID."""
        logger.info(f"Searching works citing DOI: {doi}")
        params = self.params.copy()
        params.update({
            "filter": f"doi:{doi}",
            "select": "id"
        })
        try:
            response = requests.get(self.base_url, params=params, timeout=20)
            response.raise_for_status()
            results = response.json().get("results", [])
            if results:
                work_id = results[0].get("id").split("/")[-1]
                return self.search_by_citing_id(work_id)
            else:
                logger.warning(f"DOI {doi} not found in OpenAlex.")
                return []
        except Exception as e:
            msg = f"Error resolving DOI {doi}: {e}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return []

    def search_by_citing_id(self, work_id: str) -> List[Paper]:
        """Search for works that cite a specific OpenAlex ID (e.g. W12345)."""
        params = self.params.copy()
        params.update({
            "filter": f"cites:{work_id},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
            "sort": "publication_date:desc",
            "per_page": 50
        })
        return self._fetch_openalex(params)

    def fetch_by_doi(self, doi: str) -> List[Paper]:
        """Fetches metadata for a single specific DOI."""
        params = self.params.copy()
        # Clean DOI if it's a URL
        clean_doi = doi.replace("https://doi.org/", "").strip()
        params.update({
            "filter": f"doi:{clean_doi}"
        })
        return self._fetch_openalex(params)

    def _fetch_openalex(self, params: dict) -> List[Paper]:
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            papers = []
            for work in data.get("results", []):
                # Extract metadata from OpenAlex format
                title = work.get("title", "No Title")
                
                # DOI and Link handling
                raw_doi = work.get("doi")
                doi = raw_doi.replace("https://doi.org/", "") if raw_doi else None
                link = raw_doi or work.get("id")

                # QUICK CHECK: Skip if already in DB
                if db.is_seen(link, doi):
                    continue
                
                # Published date
                pub_date_str = work.get("publication_date")
                if pub_date_str:
                    published = datetime.strptime(pub_date_str, "%Y-%m-%d")
                else:
                    published = datetime.now()
                
                # Source and Source ID
                source = "Unknown Source"
                source_id = None
                location = work.get("primary_location")
                if location and location.get("source"):
                    source = location["source"].get("display_name", source)
                    full_source_id = location["source"].get("id")
                    if full_source_id:
                        source_id = full_source_id.split("/")[-1]
                
                # Abstract (OpenAlex uses an Inverted Index for abstracts)
                abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
                
                # Authors and Author IDs
                authors = []
                author_ids = []
                for authorship in work.get("authorships", []):
                    author_data = authorship.get("author", {})
                    name = author_data.get("display_name", "")
                    full_id = author_data.get("id", "")
                    if name:
                        authors.append(name)
                    if full_id:
                        author_ids.append(full_id.split("/")[-1])

                paper = Paper(
                    title=title,
                    link=link,
                    published=published,
                    source=source,
                    source_id=source_id,
                    abstract=abstract,
                    authors=authors,
                    author_ids=author_ids,
                    doi=doi
                )
                papers.append(paper)
            return papers
            
        except Exception as e:
            msg = f"OpenAlex fetch error: {e}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return []

    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        """OpenAlex provides abstracts in an inverted index to avoid copyright issues. We reconstruct it."""
        if not inverted_index:
            return ""
        
        # Inverted index is { word: [positions] }
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        
        # Sort by position
        word_positions.sort()
        return " ".join([wp[1] for wp in word_positions])
