import shutil
import markdown2
import html
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Dict
from src.config import TEMPLATES_DIR, PUBLIC_DIR, SUMMARIES_DIR, PAPERS_DIR, SITE_URL, SITE_TITLE
from src.db import db
from src.logger import logger

class SiteGenerator:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def build(self):
        logger.info("Starting static site generation...")
        
        # Prepare public directory
        if PUBLIC_DIR.exists():
            shutil.rmtree(PUBLIC_DIR)
        PUBLIC_DIR.mkdir()
        
        # Copy assets
        assets_src = Path("assets")
        if assets_src.exists():
            shutil.copytree(assets_src, PUBLIC_DIR / "assets")

        # Collect all summaries
        papers = self._collect_papers()
        
        # Sort by added date (descending)
        papers.sort(key=lambda x: x['added_date_obj'], reverse=True)
        
        # Generate individual pages
        for paper in papers:
            self._render_paper(paper)
            
        # Generate Index (Recent 10)
        self._render_index(papers[:10])
        
        # Generate Archive
        self._render_archive(papers)
        
        # Generate About Page
        self._render_about()
        
        # Generate Stats Page
        self._render_stats(papers)
        
        # Generate RSS
        self._generate_rss(papers[:20]) # Feed for last 20 items
        
        # Generate Hidden Events RSS
        self._generate_events_rss()
        
        logger.info("Site generation complete.")

    def _collect_papers(self) -> List[Dict]:
        papers = []
        # Fetch added dates from DB
        try:
            added_dates_map = db.get_all_processed_dates()
        except Exception as e:
            logger.warning(f"Could not fetch processed dates from DB: {e}")
            added_dates_map = {}

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

                # Parse filename: YYYYMMDD-Author.md or DOI.md
                if len(md_file.name) > 8 and md_file.name[:8].isdigit():
                    try:
                        date_str = md_file.name[:8]
                        paper_date_obj = datetime.strptime(date_str, "%Y%m%d")
                        author = md_file.name[9:-3]
                    except ValueError:
                        pass
                
                # NEW: Look for date in the content if filename parsing failed
                if not paper_date_obj:
                    import re
                    # Look for Year in Identification section
                    # - **Year:** 2024
                    match = re.search(r"-\s+\*\*Year:\*\*\s+(\d{4})", raw_content)
                    if match:
                        year_str = match.group(1)
                        # We don't have the full date, so we use Year-01-01 as approximation
                        # or try to extract more from Identification if available.
                        # For now, Year-01-01 is better than current month.
                        try:
                            paper_date_obj = datetime.strptime(f"{year_str}0101", "%Y%m%d")
                        except ValueError:
                            pass

                # Fallback: use file mtime if content parsing also failed
                if not paper_date_obj:
                    paper_date_obj = datetime.fromtimestamp(md_file.stat().st_mtime)
                    author = md_file.stem

                # Parse Short Summary (between ## Short Summary and next ##)
                preview = ""
                # Strip warning if present for the preview
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
                    # Fallback to lines skipping the first few
                    preview = ' '.join(lines[2:5]) + '...'

                # Extract original link from metadata comment
                original_link = "#"
                if "<!-- metadata:original_link:" in raw_content:
                    try:
                        part = raw_content.split("<!-- metadata:original_link:")[1]
                        original_link = part.split(" -->")[0].strip()
                    except IndexError:
                        pass

                # Determine Added Date (for Sorting/RSS)
                added_date_obj = added_dates_map.get(original_link)
                if not added_date_obj:
                    # Fallback to file mtime if not in DB
                    added_date_obj = datetime.fromtimestamp(md_file.stat().st_mtime)

                # Convert to HTML (for summary page we keep everything except the warning comment tags)
                html_content = markdown2.markdown(
                    raw_content.replace("<!-- warning_start -->", "").replace("<!-- warning_end -->", ""),
                    extras=["fenced-code-blocks"]
                )
                
                # Relative paths for links
                # Page will be at: public/summaries/YYYY/filename.html
                
                rel_path = f"summaries/{year_dir.name}/{md_file.stem}.html"
                
                papers.append({
                    'title': title,
                    'author': author,
                    'date': paper_date_obj.strftime("%Y-%m-%d"), # Display date (Paper date)
                    'date_obj': paper_date_obj, # Keep for archive logic?
                    'added_date_obj': added_date_obj, # For Sorting/RSS
                    'preview': preview,
                    'content': html_content,
                    'raw_content': raw_content, # for RSS
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
        output = template.render(
            title=paper['title'],
            content=paper['content'],
            original_link=paper['original_link'],
            summary_link=summary_link,
            generated_at=self.generated_at
        )
        
        out_dir = PUBLIC_DIR / "summaries" / paper['year']
        out_dir.mkdir(parents=True, exist_ok=True)
        
        out_path = out_dir / f"{paper['filename']}.html"
        with open(out_path, "w") as f:
            f.write(output)

    def _render_index(self, papers):
        template = self.env.get_template("index.html")
        output = template.render(
            papers=papers,
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "index.html", "w") as f:
            f.write(output)

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
            archive=archive,
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "archive.html", "w") as f:
            f.write(output)
            
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
                    papers=data['papers'],
                    generated_at=self.generated_at
                )
                month_path = year_dir / f"{data['month_num']}.html"
                with open(month_path, "w") as f:
                    f.write(output)

    def _render_about(self):
        template = self.env.get_template("about.html")
        output = template.render(
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "about.html", "w") as f:
            f.write(output)

    def _render_stats(self, papers: List[Dict]):
        from collections import Counter
        
        # 1. Top 10 Journals
        journals = []
        for paper in papers:
            # Try to extract Journal from raw_content
            # Format: - **Journal:** Name
            import re
            match = re.search(r"-\s+\*\*Journal:\*\*\s+(.*)", paper['raw_content'])
            if match:
                journals.append(match.group(1).strip())
            else:
                # Fallback to 'author' field if it looks like a journal? 
                # Better to use a dedicated field if available.
                # For now, if we can't find it, skip or use 'Unknown'
                pass
        
        top_journals = Counter(journals).most_common(10)
        
        # 2. Top 10 Authors
        # paper['author'] usually contains the primary author from filename.
        # But for stats we might want ALL authors if available.
        all_authors = []
        for paper in papers:
            # Extract Authors from Identification or Bibliographic info
            # Format: - **Authors:** Name1, Name2...
            import re
            match = re.search(r"-\s+\*\*Authors:\*\*\s+(.*)", paper['raw_content'])
            if match:
                authors_str = match.group(1).strip()
                # Split by comma or 'and'
                authors_list = [a.strip() for a in re.split(r",| and ", authors_str) if a.strip()]
                all_authors.extend(authors_list)
            else:
                # Fallback to the primary author from metadata
                all_authors.append(paper['author'])
        
        top_authors = Counter(all_authors).most_common(10)
        
        # 3. Articles per Year
        years = [paper['date_obj'].year for paper in papers]
        articles_per_year = sorted(Counter(years).items(), reverse=True)
        
        template = self.env.get_template("stats.html")
        output = template.render(
            top_journals=top_journals,
            top_authors=top_authors,
            articles_per_year=articles_per_year,
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "stats.html", "w") as f:
            f.write(output)

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
        with open(PUBLIC_DIR / "feed.xml", "w") as f:
            f.write(rss_feed)

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
        with open(PUBLIC_DIR / "events.xml", "w") as f:
            f.write(rss_feed)
