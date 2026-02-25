from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass
class Paper:
    title: str
    link: str
    published: datetime
    source: str  # Journal name or Feed title
    source_id: Optional[str] = None # OpenAlex Source ID or similar
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    author_ids: List[str] = field(default_factory=list) # OpenAlex Author IDs
    doi: Optional[str] = None
    pdf_link: Optional[str] = None
    type: Optional[str] = None # e.g., 'article', 'preprint', 'book'
    
    # Filtering status
    is_relevant: bool = False
    relevance_reason: str = ""
    
    # Synthesis status
    is_processed: bool = False
    summary_path: Optional[str] = None  # Path to the generated markdown file
    
    def __post_init__(self):
        """Fix capitalization if title is all uppercase."""
        if self.title and self.title.isupper():
            # Basic Title Case for all-caps titles
            import re
            
            # Words that should generally stay lowercase in titles (unless first/last)
            lower_words = {
                'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 
                'to', 'from', 'by', 'of', 'in', 'with', 'as'
            }
            
            words = self.title.lower().split()
            if not words:
                return
                
            capitalized_words = []
            for i, word in enumerate(words):
                # Always capitalize first and last word
                if i == 0 or i == len(words) - 1 or word not in lower_words:
                    # Special handling for words with punctuation/hyphens
                    # e.g., "AI-BASED" -> "Ai-Based"
                    parts = re.split('([- ])', word)
                    capitalized_parts = [p.capitalize() if p.strip() and p not in "- " else p for p in parts]
                    capitalized_words.append("".join(capitalized_parts))
                else:
                    capitalized_words.append(word)
            
            self.title = " ".join(capitalized_words)

    def to_filename(self) -> str:
        """Generates the filename using DOI if available, otherwise Date-Author."""
        if self.doi:
            # Clean DOI for filename safety (remove / and :)
            clean_doi = "".join(c if c.isalnum() or c in ".-_" else "_" for c in self.doi)
            return f"{clean_doi}.md"
            
        date_str = self.published.strftime("%Y%m%d")
        # clean author name (first author only, alphanumeric)
        first_author = self.authors[0] if self.authors else "Unknown"
        clean_author = "".join(c for c in first_author if c.isalnum())
        return f"{date_str}-{clean_author}.md"
