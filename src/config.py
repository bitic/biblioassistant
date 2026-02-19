import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SUMMARIES_DIR = DATA_DIR / "summaries"
PAPERS_DIR = DATA_DIR / "papers"
TEMPLATES_DIR = BASE_DIR / "templates"
PUBLIC_DIR = BASE_DIR / "public"

# Database (Simple JSON or SQLite path)
DB_PATH = DATA_DIR / "db.sqlite3"

# Feeds (Deprecated: using OpenAlex Journal Watch instead)
RSS_FEEDS = []

# Local LLM (Ollama)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_FILTER_MODEL = os.getenv("OLLAMA_FILTER_MODEL", "llama3.1:8b")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")

# Relevance Engine ('gemini' or 'ollama')
RELEVANCE_ENGINE = os.getenv("RELEVANCE_ENGINE", "gemini")
RELEVANCE_MODEL = os.getenv("RELEVANCE_MODEL", "gemini-2.5-flash")

# Synthesis Engine ('gemini-api', 'gemini-cli', or 'ollama')
SYNTHESIS_ENGINE = os.getenv("SYNTHESIS_ENGINE", "gemini-api")

# Remote LLM (Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Deployment
REMOTE_HOST = os.getenv("REMOTE_HOST", "your.server.com")
REMOTE_USER = os.getenv("REMOTE_USER", "username")
REMOTE_PATH = os.getenv("REMOTE_PATH", "/var/www/biblio/")
SITE_URL = os.getenv("SITE_URL", "https://biblio.quintanasegui.com")
SITE_TITLE = "Hydrology and Climate Change Article Summaries"

# Budget Control
MAX_MONTHLY_COST = float(os.getenv("MAX_MONTHLY_COST", "10.0"))

# OpenAlex Discovery
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "your-email@example.com")

# CORE API (Optional)
CORE_API_KEY = os.getenv("CORE_API_KEY")

# Elsevier API (Optional)
ELSEVIER_API_KEY = os.getenv("ELSEVIER_API_KEY")
ELSEVIER_INST_TOKEN = os.getenv("ELSEVIER_INST_TOKEN")

DISCOVERY_TASKS = [
    # 1. Author Tracking: Pere Quintana Seguí
    {"name": "Pere Quintana Seguí", "type": "author", "id": "A5053499463"}, 
    
    # 2. Citation Watch: Automated tracking for all papers by Pere Quintana Seguí
    {"name": "My Citation Watch", "type": "author_citations", "id": "A5053499463"}, 

    # 3. Journal Watch: Monitor core and high-impact journals directly via OpenAlex
    {
        "name": "Journal Watch", 
        "type": "journal", 
        "id": "S204847658|S37844757|S93121129|S55737203|S32061424|S70708404|S137773608|S183584863|S64187185|S48977010|S4210188283|S4387286383|S196734849|S141808269|S17729819|S80591372|S86852077"
    },

    # 4. Regional Focus: Pyrenees and Ebro Basin (Keep specific)
    {"name": "Local: Pyrenees & Ebro", "type": "search", "query": "(Pyrenees OR \"Ebro Basin\"  OR Catalonia OR Spain OR \"Iberian Peninsula\") AND (drought OR snow OR hydrology OR \"water resources\")"},

    # 5. Global Methodological: Irrigation & Water Management
    {"name": "Global: Irrigation & LSM", "type": "search", "query": "irrigation AND (\"remote sensing\" OR \"soil moisture\" OR \"evapotranspiration\" OR \"streamflow\" OR \"groundwater\")"},

    # 6. Global Model Watch: LSM & Hydrological Models
    {"name": "Global: Model Development", "type": "search", "query": "\"SURFEX\" OR \"SAFRAN\" OR \"mHM model\" OR \"ORCHIDEE model\" OR \"JULES model\" OR \"VIC model\" OR \"LPRM\" OR \"global hydrolocial model\""},

    # 7. Global Process: Drought & Flood Extremes
    {"name": "Global: Hydrological Extremes", "type": "search", "query": "(\"drought\" OR \"flash flood\") AND (\"groundwater\" OR \"soil moisture\" OR \"data assimilation\")"},

    # 8. New Journal Watch: Earth Observation (EO)
    {"name": "Earth Observation (EO)", "type": "issn", "issn": "3054-1786"}
]
