import shutil
import markdown2
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Dict
from src.config import TEMPLATES_DIR, PUBLIC_DIR, SUMMARIES_DIR, PAPERS_DIR
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
        
        # Collect all summaries
        papers = self._collect_papers()
        
        # Sort by date (descending)
        papers.sort(key=lambda x: x['date_obj'], reverse=True)
        
        # Generate individual pages
        for paper in papers:
            self._render_paper(paper)
            
        # Generate Index (Recent 10)
        self._render_index(papers[:10])
        
        # Generate Archive
        self._render_archive(papers)
        
        # Generate About Page
        self._render_about()
        
        # Generate RSS
        self._generate_rss(papers[:20]) # Feed for last 20 items
        
        # Generate Hidden Events RSS
        self._generate_events_rss()
        
        logger.info("Site generation complete.")

    def _collect_papers(self) -> List[Dict]:
        papers = []
        # Walk through YYYY directories
        for year_dir in SUMMARIES_DIR.glob("*"):
            if not year_dir.is_dir(): continue
            
            for md_file in year_dir.glob("*.md"):
                # 1. Parse metadata from content/file
                with open(md_file, "r") as f:
                    raw_content = f.read()
                
                # Default values
                title = "Untitled"
                date_obj = None
                author = "Unknown"
                
                # Parse Title (Assume first line is # Title)
                lines = raw_content.split('\n')
                if lines and lines[0].startswith('# '):
                    title = lines[0][2:].strip()

                # Parse filename: YYYYMMDD-Author.md or DOI.md
                if len(md_file.name) > 8 and md_file.name[:8].isdigit():
                    try:
                        date_str = md_file.name[:8]
                        date_obj = datetime.strptime(date_str, "%Y%m%d")
                        author = md_file.name[9:-3]
                    except ValueError:
                        pass
                
                # Fallback: use file mtime if filename didn't yield a date
                if not date_obj:
                    date_obj = datetime.fromtimestamp(md_file.stat().st_mtime)
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

                # Convert to HTML (for summary page we keep everything except the warning comment tags)
                html_content = markdown2.markdown(raw_content.replace("<!-- warning_start -->", "").replace("<!-- warning_end -->", ""))
                
                # Relative paths for links
                # Page will be at: public/summaries/YYYY/filename.html
                
                rel_path = f"summaries/{year_dir.name}/{md_file.stem}.html"
                
                papers.append({
                    'title': title,
                    'author': author,
                    'date': date_obj.strftime("%Y-%m-%d"),
                    'date_obj': date_obj,
                    'preview': preview,
                    'content': html_content,
                    'raw_content': raw_content, # for RSS
                    'rel_path': rel_path,
                    'original_link': original_link,
                    'year': year_dir.name,
                    'month': date_obj.strftime("%B"),
                    'filename': md_file.stem
                })
        return papers

    def _render_paper(self, paper):
        template = self.env.get_template("paper.html")
        output = template.render(
            title=paper['title'],
            content=paper['content'],
            original_link=paper['original_link'],
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
            if y not in archive: archive[y] = {}
            if m not in archive[y]: archive[y][m] = []
            archive[y][m].append(paper)
            
        template = self.env.get_template("archive.html")
        output = template.render(
            archive=archive,
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "archive.html", "w") as f:
            f.write(output)

    def _render_about(self):
        template = self.env.get_template("about.html")
        output = template.render(
            generated_at=self.generated_at
        )
        with open(PUBLIC_DIR / "about.html", "w") as f:
            f.write(output)

    def _generate_rss(self, papers):
        # Basic RSS 2.0 generation
        rss_items = []
        base_url = "https://biblio.quintanasegui.com"
        for paper in papers:
            item = f"""
            <item>
                <title>{paper['title']}</title>
                <link>{base_url}/summaries/{paper['year']}/{paper['filename']}.html</link>
                <description><![CDATA[{paper['preview']}]]></description>
                <pubDate>{paper['date_obj'].strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
                <guid>{paper['filename']}</guid>
            </item>
            """
            rss_items.append(item)
            
        rss_feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>BiblioAssistant Feed</title>
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

            item = f"""
            <item>
                <title>[{event['event_type']}] {event['message'][:50]}...</title>
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
