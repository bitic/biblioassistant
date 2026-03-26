import shutil
import markdown2
import html
import json
import sqlite3
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Dict
from src.config import TEMPLATES_DIR, PUBLIC_DIR, SUMMARIES_DIR, PAPERS_DIR, SITE_URL, SITE_TITLE, AUTHOR_NORMALIZATION
from src.db import db
from src.logger import logger

class SiteGenerator:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        self.env.filters['slugify'] = self._slugify
        self.journal_url_map = {} # Name -> URL
        self.urls = [] # List of relative paths for the sitemap

    def _write_if_changed(self, file_path: Path, content: str):
        """Writes content to file_path only if it differs from existing content."""
        if file_path.exists():
            existing_content = file_path.read_text()
            if existing_content == content:
                # No change, skip write to preserve timestamp
                return
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)

    def build(self):
        logger.info("Starting static site generation...")
        
        # Ensure public directory exists
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        
        # Copy assets (only if changed or missing)
        assets_src = Path("assets")
        if assets_src.exists():
            # Use a more efficient copy that only updates if needed
            # For simplicity here, we'll keep it but we could use a similar logic for assets
            # but usually assets change less frequently than HTML.
            # shutil.copytree with dirs_exist_ok=True (Python 3.8+)
            shutil.copytree(assets_src, PUBLIC_DIR / "assets", dirs_exist_ok=True)

        # Copy static files (that go to the root, like robots.txt or verification files)
        static_src = Path("static")
        if static_src.exists():
            for static_file in static_src.iterdir():
                if static_file.is_file():
                    shutil.copy2(static_file, PUBLIC_DIR / static_file.name)

        # Fetch added dates and journal URLs from DB
        try:
            added_dates_map = db.get_all_processed_dates()
            self.paper_journal_links = db.get_journal_urls()
            self.paper_authors_map = db.get_all_paper_authors() # Link -> list of {id, name}
            self.paper_journals_map = db.get_all_paper_journals() # Link -> {id, name, url}
        except Exception as e:
            logger.warning(f"Could not fetch metadata from DB: {e}")
            added_dates_map = {}
            self.paper_journal_links = {}
            self.paper_authors_map = {}
            self.paper_journals_map = {}

        # Collect all summaries
        all_papers = self._collect_papers(added_dates_map)
        
        # Deduplicate papers by normalized title
        seen_titles = {} # normalized_title -> paper
        import re
        
        for p in all_papers:
            # Normalize title for comparison: lowercase, alphanumeric only
            norm_title = re.sub(r'[^a-z0-9]', '', p['title'].lower())
            
            if norm_title in seen_titles:
                existing = seen_titles[norm_title]
                
                # Preference logic:
                # 1. Prefer ones with a real DOI (not an OpenAlex URL placeholder)
                p_has_real_doi = p.get('doi') and not str(p['doi']).startswith('https://openalex.org/')
                ex_has_real_doi = existing.get('doi') and not str(existing['doi']).startswith('https://openalex.org/')
                
                if p_has_real_doi and not ex_has_real_doi:
                    seen_titles[norm_title] = p
                elif not (ex_has_real_doi and not p_has_real_doi):
                    # If DOI status is equal, keep the most recently processed one
                    if p['added_date_obj'] > existing['added_date_obj']:
                        seen_titles[norm_title] = p
                continue
            
            seen_titles[norm_title] = p
            
        papers = list(seen_titles.values())
        
        # Sort by publication date (descending), then by added date as fallback
        papers.sort(key=lambda x: (x['date_obj'], x['added_date_obj']), reverse=True)
        
        # Generate individual pages
        for paper in papers:
            self._render_paper(paper)
            
        # Generate Index (Recent 20)
        self._render_index(papers[:20])
        
        # Generate Archive
        self._render_archive(papers)
        
        # Generate News Page
        self._render_news()
        
        # Generate About Page
        self._render_about()
        
        # Generate Stats Page
        self._render_stats(papers)
        
        # Generate Filter Page
        self._render_filter_page()
        
        # Generate RSS
        self._generate_rss(papers[:20]) # Feed for last 20 items
        
        # Generate Hidden Events RSS
        self._generate_events_rss()
        
        # Generate News RSS
        self._generate_news_rss()
        
        # Generate Author Pages
        self._render_author_pages(papers)

        # Generate Authors List Page
        self._render_authors_list_page(papers)

        # Generate Journal Pages
        self._render_journal_pages(papers)

        # Generate Journals List Page
        self._render_journals_list_page(papers)

        # Generate Sitemap
        self._generate_sitemap()
        
        logger.info("Site generation complete.")

    def _generate_sitemap(self):
        """Generates a sitemap.xml file with all collected URLs."""
        logger.info(f"Generating sitemap for {len(self.urls)} pages...")
        
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        ]
        
        # Add a unique list of URLs
        seen = set()
        # Add root index manually if not already added
        if "/" not in self.urls:
            self.urls.append("/")

        for path in sorted(set(self.urls)):
            if path in seen: continue
            seen.add(path)
            
            # Ensure path starts with / but not duplicated
            if not path.startswith("/"):
                path = "/" + path
            
            # Avoid double slashes if SITE_URL ends with one
            base_url = SITE_URL.rstrip("/")
            full_url = f"{base_url}{path}"
            
            xml_lines.append("  <url>")
            xml_lines.append(f"    <loc>{full_url}</loc>")
            # Priority logic: home is 1.0, papers 0.8, archive/authors 0.5
            priority = "0.5"
            if path == "/": priority = "1.0"
            elif "/summaries/" in path: priority = "0.8"
            elif path in ["/news.html", "/about.html"]: priority = "0.7"
            
            xml_lines.append(f"    <priority>{priority}</priority>")
            xml_lines.append("  </url>")
            
        xml_lines.append("</urlset>")
        
        self._write_if_changed(PUBLIC_DIR / "sitemap.xml", "\n".join(xml_lines))
        
        # Also ensure robots.txt points to it
        robots_txt = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL.rstrip('/')}/sitemap.xml\n"
        self._write_if_changed(PUBLIC_DIR / "robots.txt", robots_txt)

    def _extract_authors(self, paper):
        """Extracts a list of clean author names from a paper's raw content."""
        import re
        match = re.search(r"-\s+\*\*Authors:\*\*\s+(.*)", paper['raw_content'])
        authors_to_index = []
        if match:
            authors_str = match.group(1).strip()
            # 1. Prefer semicolon as primary separator if present
            if ';' in authors_str:
                authors_to_index = [a.strip() for a in re.split(r";| and ", authors_str) if a.strip()]
            # 2. Otherwise use comma but avoid the even-parts-swap trap
            else:
                # Common pattern: Name Surname, Name Surname
                authors_to_index = [a.strip() for a in re.split(r",| and ", authors_str) if a.strip()]
        else:
            # Fallback to the main author field if no authors block found
            authors_to_index = [paper['author']]

        # Final cleanup: remove short strings or institutional names
        clean_authors = [name for name in authors_to_index if len(name) >= 4 and "Geological Survey" not in name]
        
        # Apply normalization
        normalized_authors = []
        for name in clean_authors:
            # Check for direct mapping or surname mapping
            canonical_name = AUTHOR_NORMALIZATION.get(name, name)
            normalized_authors.append(canonical_name)
            
        return list(dict.fromkeys(normalized_authors)) # Deduplicate preserved order

    def _render_author_pages(self, papers):
        """Generates a separate page for each author with their list of papers, using ID for mapping."""
        # author_id -> {name: str, papers: list}
        author_map = {}
        
        for paper in papers:
            # Use authors from DB
            authors_data = paper.get('db_authors', [])
            
            if authors_data:
                for auth in authors_data:
                    aid = auth['id']
                    name = auth['name']
                    
                    # If the name is just the ID (fallback in DB), try to get it from Markdown
                    if name == aid:
                        extracted_names = self._extract_authors(paper)
                        if extracted_names:
                            # This is a bit of a guess but better than showing the ID
                            name = extracted_names[0]

                    if aid not in author_map:
                        author_map[aid] = {'name': name, 'papers': []}

                    author_map[aid]['papers'].append({
                        'title': paper['title'],
                        'year': paper['date_obj'].year,
                        'rel_path': paper['rel_path'],
                        'other_authors_count': len(authors_data) - 1
                    })

        template = self.env.get_template("author.html")
        out_dir = PUBLIC_DIR / "authors"
        out_dir.mkdir(exist_ok=True)

        for aid, data in author_map.items():
            author_papers = data['papers']
            author_papers.sort(key=lambda x: x['year'], reverse=True)
            
            # Final safety check: never show raw ID as name to user
            display_name = data['name']
            if display_name.startswith('A') and display_name[1:].isdigit():
                # If we still have an ID, skip generating this page or use fallback
                continue

            output = template.render(
                author_name=display_name,
                papers=author_papers
            )
            self.urls.append(f"/authors/{aid}.html")
            self._write_if_changed(out_dir / f"{aid}.html", output)

    def _render_authors_list_page(self, papers):
        """Generates a master list of all authors, sorted alphabetically (Surname, Name)."""
        logger.info("Generating Authors list page...")
        
        # author_id -> {name: str, count: int}
        author_data_map = {}
        for paper in papers:
            authors_data = paper.get('db_authors', [])
            
            if authors_data:
                for auth in authors_data:
                    aid = auth['id']
                    name = auth['name']
                    
                    # If the name is just the ID (fallback in DB), try to get it from Markdown
                    if name == aid:
                        extracted_names = self._extract_authors(paper)
                        if extracted_names:
                            name = extracted_names[0]

                    if aid not in author_data_map:
                        author_data_map[aid] = {'name': name, 'count': 0}
                    author_data_map[aid]['count'] += 1

        # Prepare list for sorting
        authors_list = []
        for aid, data in author_data_map.items():
            # Safety check: skip if name is still an ID
            if data['name'].startswith('A') and data['name'][1:].isdigit():
                continue

            authors_list.append({
                'name': data['name'],
                'count': data['count'],
                'id': aid
            })

        # Sort by Surname, Name using the canonical name
        authors_list.sort(key=lambda x: self._author_sort_key(x['name']))

        template = self.env.get_template("authors.html")
        output = template.render(
            authors=authors_list
        )
        self.urls.append("/authors.html")
        self._write_if_changed(PUBLIC_DIR / "authors.html", output)

    def _render_journal_pages(self, papers):
        """Generates a separate page for each journal with its list of papers."""
        # journal_id -> {name: str, url: str, papers: list}
        journal_map = {}
        
        for paper in papers:
            journal_data = paper.get('db_journal')
            if journal_data:
                jid = journal_data['id']
                if jid not in journal_map:
                    journal_map[jid] = {
                        'name': journal_data['name'], 
                        'url': journal_data['url'], 
                        'papers': []
                    }
                
                journal_map[jid]['papers'].append({
                    'title': paper['title'],
                    'year': paper['date_obj'].year,
                    'rel_path': paper['rel_path']
                })

        template = self.env.get_template("journal.html")
        out_dir = PUBLIC_DIR / "journals"
        out_dir.mkdir(exist_ok=True)

        for jid, data in journal_map.items():
            data['papers'].sort(key=lambda x: x['year'], reverse=True)
            output = template.render(
                journal_name=data['name'],
                journal_url=data['url'],
                papers=data['papers']
            )
            self.urls.append(f"/journals/{jid}.html")
            self._write_if_changed(out_dir / f"{jid}.html", output)

    def _render_journals_list_page(self, papers):
        """Generates a master list of all journals, sorted by name."""
        logger.info("Generating Journals list page...")
        
        journal_stats = {}
        for paper in papers:
            journal_data = paper.get('db_journal')
            if journal_data:
                jid = journal_data['id']
                if jid not in journal_stats:
                    journal_stats[jid] = {'name': journal_data['name'], 'count': 0}
                journal_stats[jid]['count'] += 1

        journals_list = []
        for jid, data in journal_stats.items():
            journals_list.append({
                'id': jid,
                'name': data['name'],
                'count': data['count']
            })

        journals_list.sort(key=lambda x: x['name'].lower())

        template = self.env.get_template("journals.html")
        output = template.render(journals=journals_list)
        self.urls.append("/journals.html")
        self._write_if_changed(PUBLIC_DIR / "journals.html", output)
    def _author_sort_key(self, name):
        """Returns a sort key for (Surname, Name) sorting."""
        parts = name.strip().split()
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0].lower()
        # Last word as surname, rest as name
        return f"{parts[-1]}, {' '.join(parts[:-1])}".lower()

    def _slugify(self, text):
        import re
        import unicodedata
        text = str(unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii'))
        text = text.lower()
        return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '-')

    def _generate_news_rss(self):
        """Generates an RSS feed for the news section."""
        news_file = Path("data/news.json")
        if not news_file.exists():
            return

        try:
            with open(news_file, "r") as f:
                news_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading news data for RSS: {e}")
            return

        rss_items = []
        base_url = SITE_URL
        for item in news_data:
            # Parse date (YYYY.MM.DD)
            try:
                dt = datetime.strptime(item['date'], "%Y.%m.%d")
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except:
                pub_date = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

            # Clean content
            clean_text = html.escape(item['text'])
            title = html.escape(f"{item.get('emoji', '📢')} News Update - {item['date']}")

            rss_item = f"""
            <item>
                <title>{title}</title>
                <link>{base_url}/news.html</link>
                <description><![CDATA[{item['text']}]]></description>
                <pubDate>{pub_date}</pubDate>
                <guid>{item['date']}-{hash(item['text'])}</guid>
            </item>
            """
            rss_items.append(rss_item)

        rss_feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>{SITE_TITLE} - News</title>
    <link>{base_url}/news.html</link>
    <description>Latest updates about the BiblioAssistant project</description>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(rss_items)}
</channel>
</rss>
'''
        self._write_if_changed(PUBLIC_DIR / "news.xml", rss_feed)

    def _collect_papers(self, added_dates_map: dict) -> List[Dict]:
        papers = []
        # Fetch added dates and journal URLs from DB
        try:
            added_dates_map = db.get_all_processed_dates()
            # Use improved db helper
            journal_db_urls = db.get_distinct_journal_urls()
        except Exception as e:
            logger.warning(f"Could not fetch metadata from DB: {e}")
            added_dates_map = {}
            journal_db_urls = {}

        # Walk through YYYY directories
        for year_dir in SUMMARIES_DIR.glob("*"):
            if not year_dir.is_dir(): continue
            
            for md_file in year_dir.glob("*.md"):
                # 1. Parse metadata from content/file
                with open(md_file, "r") as f:
                    raw_content = f.read()
                
                # Default values
                title = "Untitled"
                paper_date_obj = None
                author = "Unknown"
                
                # Parse Title (Assume first line is # Title)
                lines = raw_content.split('\n')
                if lines and lines[0].startswith('# '):
                    title = lines[0][2:].strip()

                # DETERMINISTIC EXTRACTION (Identification Section)
                import re
                
                # Extract original link from metadata comment (needed for DB lookups)
                original_link = "#"
                if "<!-- metadata:original_link:" in raw_content:
                    try:
                        part = raw_content.split("<!-- metadata:original_link:")[1]
                        original_link = part.split(" -->")[0].strip()
                    except IndexError:
                        pass

                # 1. Journal and Source URL (Now from DB if available)
                db_journal = self.paper_journals_map.get(original_link)
                if db_journal:
                    journal = db_journal['name']
                    source_url = db_journal['url']
                else:
                    journal = "Unknown"
                    source_url = None
                    match = re.search(r"-\s+\*\*Journal:\*\*\s+(.*)", raw_content)
                    if match:
                        val = match.group(1).strip()
                        if val.startswith("[") and "](" in val:
                            inner_match = re.search(r"\[(.*?)\]\((.*?)\)", val)
                            if inner_match:
                                journal = inner_match.group(1)
                                source_url = inner_match.group(2)
                        else:
                            journal = val

                # If source_url not in MD, check legacy DB mapping
                if not source_url and original_link in self.paper_journal_links:
                    _, source_url = self.paper_journal_links[original_link]

                if journal != "Unknown" and source_url:
                    self.journal_url_map[journal] = source_url

                # 2. Paper Date
                match = re.search(r"-\s+\*\*Date:\*\*\s+(\d{4}-\d{2}-\d{2})", raw_content)
                if match:
                    try:
                        paper_date_obj = datetime.strptime(match.group(1), "%Y-%m-%d")
                    except ValueError:
                        pass
                
                # 3. Filename Fallback for Date/Author
                if not paper_date_obj and len(md_file.name) > 8 and md_file.name[:8].isdigit():
                    try:
                        date_str = md_file.name[:8]
                        paper_date_obj = datetime.strptime(date_str, "%Y%m%d")
                        author = md_file.name[9:-3]
                    except ValueError:
                        pass

                # 4. Authors (Now from DB if available)
                db_authors = self.paper_authors_map.get(original_link, [])
                
                # Fallback to DOI lookup if link fails
                if not db_authors and "https://doi.org/" in original_link:
                    doi = original_link.replace("https://doi.org/", "")
                
                author = "Unknown"
                # Check if we have a valid name in DB (not just an ID)
                if db_authors and not (db_authors[0]['name'].startswith('A') and db_authors[0]['name'][1:].isdigit()):
                    author = db_authors[0]['name']
                else:
                    # Legacy fallback to Regex (used if DB is empty or only has the ID)
                    match = re.search(r"-\s+\*\*Authors:\*\*\s+(.*)", raw_content)
                    if match:
                        authors_str = match.group(1).strip()
                        # Use same splitting logic as _extract_authors
                        if ';' in authors_str:
                            parts = [a.strip() for a in re.split(r";| and ", authors_str) if a.strip()]
                        else:
                            parts = [p.strip() for p in re.split(r",| and ", authors_str) if p.strip()]
                        author = parts[0] if parts else "Unknown"

                # Determine Added Date (for Sorting/RSS)
                added_date_obj = added_dates_map.get(original_link)
                if not added_date_obj:
                    added_date_obj = datetime.fromtimestamp(md_file.stat().st_mtime)

                # Fallback to Year from Identification (using Year-01-01)
                if not paper_date_obj:
                    match = re.search(r"-\s+\*\*Year:\*\*\s+(\d{4})", raw_content)
                    if match:
                        try:
                            paper_date_obj = datetime.strptime(f"{match.group(1)}0101", "%Y%m%d")
                        except ValueError:
                            pass

                # FINAL FALLBACK: Use DB added_date
                if not paper_date_obj:
                    paper_date_obj = added_date_obj

                # Parse Short Summary
                preview = ""
                clean_for_preview = raw_content
                if "<!-- warning_start -->" in clean_for_preview:
                    parts = clean_for_preview.split("<!-- warning_start -->")
                    after_warning = parts[1].split("<!-- warning_end -->")
                    if len(after_warning) > 1:
                        clean_for_preview = parts[0] + after_warning[1]

                if "## Short Summary" in clean_for_preview:
                    try:
                        excerpt_part = clean_for_preview.split("## Short Summary")[1].split("##")[0].strip()
                        preview = excerpt_part
                    except IndexError:
                        pass
                
                if not preview:
                    preview = ' '.join(lines[2:5]) + '...'

                # Convert to HTML
                html_content = markdown2.markdown(
                    raw_content.replace("<!-- warning_start -->", "").replace("<!-- warning_end -->", ""),
                    extras=["fenced-code-blocks"]
                )
                
                rel_path = f"summaries/{year_dir.name}/{md_file.stem}.html"
                
                papers.append({
                    'title': title,
                    'author': author,
                    'journal': journal,
                    'source_url': source_url,
                    'date': paper_date_obj.strftime("%Y-%m-%d"),
                    'date_obj': paper_date_obj,
                    'added_date_obj': added_date_obj,
                    'preview': preview,
                    'db_authors': db_authors,
                    'db_journal': db_journal,
                    'first_author_id': db_authors[0]['id'] if db_authors else self._slugify(author),
                    'content': html_content,
                    'raw_content': raw_content,
                    'rel_path': rel_path,
                    'original_link': original_link,
                    'year': year_dir.name,
                    'month': paper_date_obj.strftime("%B"),
                    'filename': md_file.stem
                })
        return papers

    def _render_paper(self, paper):
        template = self.env.get_template("paper.html")
        summary_link = f"{SITE_URL}/{paper['rel_path']}"

        # Post-process content to make authors clickable
        content_html = paper['content']
        import re
        authors_match = re.search(r"<li><strong>Authors:</strong>\s*(.*?)</li>", content_html)
        if authors_match:
            original_authors_html = authors_match.group(1)

            # Use the robust extraction method from DB if available
            authors_data = paper.get('db_authors', [])
            
            if authors_data:
                linked_authors_list = []
                extracted_names = self._extract_authors(paper)
                
                for idx, auth in enumerate(authors_data):
                    aid = auth['id']
                    name = auth['name']
                    
                    # If the name is just the ID (fallback in DB), try to get it from Markdown by position
                    if name == aid:
                        if extracted_names and idx < len(extracted_names):
                            name = extracted_names[idx]
                    
                    # Last resort: if it's still an ID, just use the ID as name without ID link
                    if name.startswith('A') and name[1:].isdigit():
                        linked_authors_list.append(name)
                    else:
                        linked_authors_list.append(f'<a href="/authors/{aid}.html">{name}</a>')

                linked_authors_html = ", ".join(linked_authors_list)

                # Replace in HTML (only the metadata line to avoid linking names in title/text)
                new_authors_line = authors_match.group(0).replace(original_authors_html, linked_authors_html)
                content_html = content_html.replace(authors_match.group(0), new_authors_line)

        # Post-process journal name to be clickable
        journal_match = re.search(r"<li><strong>Journal:</strong>\s*(.*?)</li>", content_html)
        if journal_match:
            original_journal_html = journal_match.group(1).strip()
            db_journal = paper.get('db_journal')
            
            # Decide on the display name for the journal
            journal_display_name = original_journal_html
            if db_journal and db_journal['name'] and not (db_journal['name'].startswith('S') and db_journal['name'][1:].isdigit()):
                journal_display_name = db_journal['name']

            if db_journal:
                jid = db_journal['id']
                linked_journal_html = f'<a href="/journals/{jid}.html">{journal_display_name}</a>'
                # Replace only the metadata line
                new_journal_line = journal_match.group(0).replace(original_journal_html, linked_journal_html)
                content_html = content_html.replace(journal_match.group(0), new_journal_line)
            elif not original_journal_html.startswith("<a"):
                url = self.journal_url_map.get(original_journal_html)
                if url:
                    linked_journal_html = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{original_journal_html}</a>'
                    # Replace only the metadata line
                    new_journal_line = journal_match.group(0).replace(original_journal_html, linked_journal_html)
                    content_html = content_html.replace(journal_match.group(0), new_journal_line)

        output = template.render(
            title=paper['title'],
            content=content_html,
            original_link=paper['original_link'],
            summary_link=summary_link
        )
        
        out_dir = PUBLIC_DIR / "summaries" / paper['year']
        out_dir.mkdir(parents=True, exist_ok=True)
        
        out_path = out_dir / f"{paper['filename']}.html"
        self.urls.append(f"/{paper['rel_path']}")
        self._write_if_changed(out_path, output)

    def _render_index(self, papers):
        template = self.env.get_template("index.html")
        output = template.render(
            papers=papers
        )
        self.urls.append("/")
        self._write_if_changed(PUBLIC_DIR / "index.html", output)

    def _render_archive(self, papers):
        # Group by Year -> Month
        archive = {}
        for paper in papers:
            y = paper['year']
            m = paper['month']
            month_num = paper['date_obj'].strftime("%m")
            
            if y not in archive: archive[y] = {}
            if m not in archive[y]: 
                archive[y][m] = {
                    'month_num': month_num,
                    'papers': []
                }
            archive[y][m]['papers'].append(paper)
            
        # Render main archive page
        template = self.env.get_template("archive.html")
        output = template.render(
            archive=archive
        )
        self.urls.append("/archive.html")
        self._write_if_changed(PUBLIC_DIR / "archive.html", output)
            
        # Render individual monthly pages
        month_template = self.env.get_template("month.html")
        for year, months in archive.items():
            year_dir = PUBLIC_DIR / "archive" / year
            year_dir.mkdir(parents=True, exist_ok=True)
            
            for month_name, data in months.items():
                # Sort papers in the month by date descending
                data['papers'].sort(key=lambda x: x['date_obj'], reverse=True)
                
                output = month_template.render(
                    year=year,
                    month=month_name,
                    papers=data['papers']
                )
                month_path = year_dir / f"{data['month_num']}.html"
                self.urls.append(f"/archive/{year}/{data['month_num']}.html")
                self._write_if_changed(month_path, output)

    def _render_about(self):
        template = self.env.get_template("about.html")
        output = template.render()
        self.urls.append("/about.html")
        self._write_if_changed(PUBLIC_DIR / "about.html", output)

    def _render_news(self):
        news_file = Path("data/news.json")
        news_data = []
        if news_file.exists():
            try:
                with open(news_file, "r") as f:
                    news_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading news data: {e}")
        
        template = self.env.get_template("news.html")
        output = template.render(
            news=news_data
        )
        self.urls.append("/news.html")
        self._write_if_changed(PUBLIC_DIR / "news.html", output)

    def _render_filter_page(self):
        """Generates a page showing recent filtering results for audit (last 7 days)."""
        logger.info("Generating Filter audit page (last 7 days)...")
        from src.filter import load_system_prompt
        system_prompt = load_system_prompt()
        recent_papers = db.get_recent_papers_by_days(days=7)
        
        # Process papers for the template
        processed_entries = []
        for p in recent_papers:
            # Format: Title (DOI)
            title_doi = f"{p['title']} ({p['doi'] or 'No DOI'})"
            
            processed_entries.append({
                'title_doi': title_doi,
                'pass': "YES" if p['is_relevant'] else "NO",
                'comment': p['relevance_reason'] or "No reason provided.",
                'date': p['date']
            })

        template = self.env.get_template("filter.html")
        output = template.render(
            papers=processed_entries,
            system_prompt=system_prompt
        )
        self.urls.append("/filter.html")
        self._write_if_changed(PUBLIC_DIR / "filter.html", output)

    def _render_stats(self, papers: List[Dict]):
        from collections import Counter
        
        # 1. Top 10 Journals (Now by ID)
        journal_stats = {}
        for paper in papers:
            journal_data = paper.get('db_journal')
            if journal_data:
                jid = journal_data['id']
                if jid not in journal_stats:
                    journal_stats[jid] = {'name': journal_data['name'], 'count': 0}
                journal_stats[jid]['count'] += 1
        
        top_journals_list = []
        for jid, data in journal_stats.items():
            top_journals_list.append({
                'id': jid, 
                'name': data['name'], 
                'count': data['count']
            })
        
        top_journals = sorted(top_journals_list, key=lambda x: x['count'], reverse=True)[:10]
        
        # 2. Top 10 Authors
        author_stats = {} # id -> {name, count}
        for paper in papers:
            authors_data = paper.get('db_authors', [])
            
            if authors_data:
                for auth in authors_data:
                    aid = auth['id']
                    name = auth['name']
                    
                    # If the name is just the ID (fallback in DB), try to get it from Markdown
                    if name == aid:
                        extracted_names = self._extract_authors(paper)
                        if extracted_names:
                            name = extracted_names[0]

                    if aid not in author_stats:
                        author_stats[aid] = {'name': name, 'count': 0}
                    author_stats[aid]['count'] += 1

        # Prepare list for sorting and filter out raw IDs
        authors_list = []
        for aid, data in author_stats.items():
            if data['name'].startswith('A') and data['name'][1:].isdigit():
                continue
            authors_list.append({
                'id': aid,
                'name': data['name'],
                'count': data['count']
            })
        
        # Sort by count and take top 10
        top_authors = sorted(authors_list, key=lambda x: x['count'], reverse=True)[:10]
        
        # 3. Articles per Year
        years = [paper['date_obj'].year for paper in papers]
        articles_per_year = sorted(Counter(years).items(), reverse=True)
        
        template = self.env.get_template("stats.html")
        output = template.render(
            top_journals=top_journals,
            top_authors=top_authors,
            articles_per_year=articles_per_year
        )
        self.urls.append("/stats.html")
        self._write_if_changed(PUBLIC_DIR / "stats.html", output)

    def _generate_rss(self, papers):
        # Basic RSS 2.0 generation
        rss_items = []
        base_url = SITE_URL
        for paper in papers:
            # Clean title for XML: unescape HTML entities (like &ndash;) then escape for XML
            clean_title = html.escape(html.unescape(paper['title']))
            
            item = f"""
            <item>
                <title>{clean_title}</title>
                <link>{base_url}/summaries/{paper['year']}/{paper['filename']}.html</link>
                <description><![CDATA[{paper['preview']}]]></description>
                <pubDate>{paper['added_date_obj'].strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
                <guid>{paper['filename']}</guid>
            </item>
            """
            rss_items.append(item)
            
        rss_feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>{SITE_TITLE}</title>
    <link>{base_url}</link>
    <description>Latest scientific summaries</description>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(rss_items)}
</channel>
</rss>
'''
        self._write_if_changed(PUBLIC_DIR / "feed.xml", rss_feed)

    def _generate_events_rss(self):
        """Generates a hidden events RSS feed for system monitoring."""
        events = db.get_recent_events(limit=100)
        rss_items = []
        for event in events:
            # Parse timestamp (SQLite format)
            try:
                dt = datetime.strptime(event['timestamp'], "%Y-%m-%d %H:%M:%S")
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except:
                pub_date = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

            # Clean title for XML
            clean_title = html.escape(html.unescape(f"[{event['event_type']}] {event['message'][:50]}..."))

            item = f"""
            <item>
                <title>{clean_title}</title>
                <description><![CDATA[{event['message']}]]></description>
                <pubDate>{pub_date}</pubDate>
                <guid>{event['timestamp']}-{event['event_type']}</guid>
            </item>
            """
            rss_items.append(item)
            
        rss_feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>BiblioAssistant Events</title>
    <link>https://biblio.quintanasegui.com</link>
    <description>Internal system events and errors</description>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(rss_items)}
</channel>
</rss>
'''
        self._write_if_changed(PUBLIC_DIR / "events.xml", rss_feed)
