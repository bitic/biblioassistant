import requests
import time
from datetime import datetime
from typing import List
from src.config import OPENALEX_EMAIL, DISCOVERY_TASKS, MIN_JOURNAL_H_INDEX, MIN_JOURNAL_IMPACT_FACTOR
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
                papers = self.search_by_keywords(
                    task['query'], 
                    min_impact=task.get('min_impact'), 
                    min_h_index=task.get('min_h_index')
                )
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
        logger.info(f"Automatically finding citations for author ID: {author_id} (Range: {self.from_date} to {self.to_date})")
        
        # 1. Get all OpenAlex IDs for this author using cursor pagination
        params = self.params.copy()
        params.update({
            "filter": f"author.id:{author_id}",
            "select": "id",
            "per_page": 200,
            "cursor": "*"
        })
        
        ids = []
        try:
            while True:
                response = requests.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                if not results:
                    break
                    
                ids.extend([work.get("id").split("/")[-1] for work in results if work.get("id")])
                
                next_cursor = data.get("meta", {}).get("next_cursor")
                if not next_cursor:
                    break
                params["cursor"] = next_cursor
                time.sleep(0.2)
            
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

    def search_by_keywords(self, query: str, min_impact: float = None, min_h_index: int = None) -> List[Paper]:
        params = self.params.copy()
        
        # Use defaults from config if not provided
        impact = min_impact if min_impact is not None else MIN_JOURNAL_IMPACT_FACTOR
        h_index = min_h_index if min_h_index is not None else MIN_JOURNAL_H_INDEX
        
        filter_str = f"title_and_abstract.search:{query},from_publication_date:{self.from_date},to_publication_date:{self.to_date}"
        
        # Add quality filters
        if impact > 0:
            filter_str += f",primary_location.source.summary_stats.2yr_mean_citedness:>{impact}"
        if h_index > 0:
            filter_str += f",primary_location.source.summary_stats.h_index:>{h_index}"

        params.update({
            "filter": filter_str,
            "sort": "publication_date:desc",
            "per_page": 50
        })
        return self._fetch_openalex(params)

    def search_by_author(self, author_id: str) -> List[Paper]:
        """Fetch papers by author ID(s). Supports multiple IDs separated by | with batching."""
        ids = author_id.split("|")
        all_papers = []
        batch_size = 50
        
        for i in range(0, len(ids), batch_size):
            batch = ids[i:i + batch_size]
            batch_str = "|".join(batch)
            
            params = self.params.copy()
            params.update({
                "filter": f"author.id:{batch_str},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
                "sort": "publication_date:desc",
                "per_page": min(100, 10 * len(batch)) # Adjust per_page based on batch size
            })
            
            papers = self._fetch_openalex(params)
            all_papers.extend(papers)
            
            if len(ids) > batch_size:
                time.sleep(0.5) # Politeness delay for large batches
                
        return all_papers

    def search_by_journal(self, source_id: str) -> List[Paper]:
        """Fetch papers by journal ID(s). Supports multiple IDs separated by | with batching."""
        ids = source_id.split("|")
        all_papers = []
        batch_size = 50
        
        for i in range(0, len(ids), batch_size):
            batch = ids[i:i + batch_size]
            batch_str = "|".join(batch)
            
            params = self.params.copy()
            params.update({
                "filter": f"primary_location.source.id:{batch_str},from_publication_date:{self.from_date},to_publication_date:{self.to_date}",
                "sort": "publication_date:desc",
                "per_page": 50
            })
            
            papers = self._fetch_openalex(params)
            all_papers.extend(papers)
            
            if len(ids) > batch_size:
                time.sleep(0.5)
                
        return all_papers

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

    def fetch_by_doi(self, doi: str, ignore_seen: bool = False) -> List[Paper]:
        """Fetches metadata for a single specific DOI."""
        params = self.params.copy()
        # Clean DOI if it's a URL
        clean_doi = doi.replace("https://doi.org/", "").strip()
        params.update({
            "filter": f"doi:{clean_doi}"
        })
        return self._fetch_openalex(params, ignore_seen=ignore_seen)

    def _fetch_openalex(self, params: dict, ignore_seen: bool = False) -> List[Paper]:
        all_papers = []
        current_params = params.copy()
        current_params["cursor"] = "*"
        
        # Ensure per_page is set efficiently
        if "per_page" not in current_params:
            current_params["per_page"] = 100
            
        page_count = 0
        
        try:
            while True:
                page_count += 1
                logger.debug(f"Fetching OpenAlex page {page_count}...")
                
                response = requests.get(self.base_url, params=current_params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                if not results:
                    break
                
                for work in results:
                    # Extract metadata from OpenAlex format
                    title = work.get("title") or "No Title"
                    
                    # DOI and Link handling
                    raw_doi = work.get("doi")
                    doi = raw_doi.replace("https://doi.org/", "") if raw_doi else None
                    link = raw_doi or work.get("id")

                    # Type and Source filtering
                    work_type = work.get("type")
                    
                    source = "Unknown Source"
                    source_id = None
                    source_url = None
                    journal_h_index = None
                    journal_impact = None
                    location = work.get("primary_location")
                    if location and location.get("source"):
                        src_obj = location["source"]
                        source = src_obj.get("display_name", source)
                        source_url = src_obj.get("homepage_url")
                        full_source_id = src_obj.get("id")
                        if full_source_id:
                            source_id = full_source_id.split("/")[-1]
                        
                        # Extract quality stats
                        stats = src_obj.get("summary_stats", {})
                        journal_h_index = stats.get("h_index")
                        journal_impact = stats.get("2yr_mean_citedness")

                    # EXCLUSIONS: Zenodo, Figshare, Unknown Source, Preprints
                    excluded_sources = ["Zenodo", "Figshare", "Unknown Source"]
                    if any(excl in source for excl in excluded_sources):
                        logger.debug(f"Skipping {title[:30]}... due to excluded source: {source}")
                        continue
                    
                    if work_type == "preprint":
                        logger.debug(f"Skipping {title[:30]}... as it is a preprint.")
                        continue

                    # QUICK CHECK: Skip if already in DB
                    if not ignore_seen and db.is_seen(link, doi):
                        continue
                    
                    # Published date
                    pub_date_str = work.get("publication_date")
                    if pub_date_str:
                        published = datetime.strptime(pub_date_str, "%Y-%m-%d")
                    else:
                        published = datetime.now()
                    
                    # Abstract (OpenAlex uses an Inverted Index for abstracts)
                    abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
                    
                    # Authors and Author IDs
                    authors = []
                    author_ids = []
                    authors_data = {}
                    for authorship in work.get("authorships", []):
                        author_data = authorship.get("author", {})
                        name = author_data.get("display_name", "")
                        full_id = author_data.get("id", "")
                        if name:
                            authors.append(name)
                        if full_id:
                            aid = full_id.split("/")[-1]
                            author_ids.append(aid)
                            if name:
                                authors_data[aid] = name

                    # Extract Topics and Concepts
                    topics = []
                    for topic_data in work.get("topics", []):
                        name = topic_data.get("display_name")
                        if name:
                            topics.append(name)
                    
                    # Concepts (legacy but still useful)
                    for concept in work.get("concepts", []):
                        if concept.get("level", 5) <= 1: # Only top-level concepts
                            name = concept.get("display_name")
                            if name and name not in topics:
                                topics.append(name)

                    paper = Paper(
                        title=title,
                        link=link,
                        published=published,
                        source=source,
                        source_id=source_id,
                        source_url=source_url,
                        abstract=abstract,
                        authors=authors,
                        author_ids=author_ids,
                        authors_data=authors_data,
                        doi=doi,
                        type=work_type,
                        topics=topics,
                        journal_h_index=journal_h_index,
                        journal_impact=journal_impact
                    )
                    all_papers.append(paper)
                
                # Check for next page
                next_cursor = data.get("meta", {}).get("next_cursor")
                if not next_cursor:
                    break
                
                current_params["cursor"] = next_cursor
                time.sleep(0.2) # Polite delay
                
            return all_papers
            
        except Exception as e:
            msg = f"OpenAlex fetch error: {e}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return all_papers

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
