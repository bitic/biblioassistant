import requests
import json
import re
from src.config import OLLAMA_HOST, OLLAMA_FILTER_MODEL, RELEVANCE_ENGINE, RELEVANCE_MODEL, GEMINI_API_KEY
from src.models import Paper
from src.logger import logger
from src.db import db

def load_system_prompt() -> str:
    """Reads the system prompt from RELEVANCE_CONTEXT.md."""
    try:
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent
        context_file = base_dir / "RELEVANCE_CONTEXT.md"
        
        if not context_file.exists():
            logger.warning(f"{context_file} not found. Using hardcoded fallback.")
            return HARDCODED_FALLBACK
            
        content = context_file.read_text()
        # Find the text between ```text and ```
        match = re.search(r"```text\n(.*?)\n```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        logger.warning("Could not find prompt block in RELEVANCE_CONTEXT.md. Using fallback.")
        return HARDCODED_FALLBACK
    except Exception as e:
        logger.error(f"Error loading system prompt from file: {e}")
        return HARDCODED_FALLBACK

HARDCODED_FALLBACK = """
You are an expert research assistant for a Senior Hydrologist and Climate Scientist. 
Your task is to filter scientific papers based on their Title and Abstract.

**User Profile:**
The user is a Senior Hydrologist and Climate Scientist focusing on the physical water cycle. The goal is to track research on Hydrology, Water Resources Management, and Irrigation.

**Criteria for RELEVANT:**
1.  **Hydrology & Modeling:** Land Surface Models (LSM), Soil Moisture, Evapotranspiration, Runoff generation, Groundwater recharge, Catchment hydrology.
2.  **Water Resources:** Drought propagation, Drought indicators, Flash floods, Water scarcity, impacts of Climate Change SPECIFICALLY on the hydrological cycle and water availability.
3.  **Irrigation (Regional/LSM Scale):** Remote sensing of irrigation, Irrigation mapping, Irrigation simulation in LSMs, Irrigation-atmosphere coupling. **ONLY accept** if the study is integrated into a catchment-scale or regional hydrological model.
4.  **Specific Models/Tools:** ISBA, SURFEX, SAFRAN, MODCOU, ORCHIDEE, SWAT, mHM (mesoscale Hydrological Model by Samaniego), JULES, Sentinel-1, SMOS, SWOT.
5.  **Techniques:** Data Assimilation of water variables, Hydrological downscaling/bias correction.

**Criteria for NOT RELEVANT:**
- **Purely Climate/Atmospheric:** Studies on atmospheric dynamics, teleconnections (ENSO, NAO), or general climate change trends WITHOUT a direct, primary focus on hydrological variables or water resources.
- **Microbiology & Health:** Studies on pathogens (Salmonella, E. coli), epidemiology, or biological aerosols (pollen), even if they use meteorological data.
- **Purely Ecological or Physiological:** Species distribution, phenology, or biodiversity studies. Also REJECT purely plant-physiological or eco-physiological studies (e.g., sap flow, xylem dynamics, stomatal conductance, leaf-level gas exchange) unless they are directly and primarily used to calibrate or validate a catchment-scale or regional hydrological model.
- **Marine/Oceanography:** Unless focusing on coastal aquifers or saltwater intrusion.
- **Management & Planning:** **REJECT** studies on water systems resilience planning, benchmarking frameworks, cost-efficiency, decision-making under uncertainty, or water governance, even if they use hydrological data (e.g., CMIP6, flood data). The primary focus must be the **physical process** or its modeling, not the planning/economic framework.
- **Social Sciences:** Policy, management, or sociological studies without a quantitative physical/hydrological basis. This includes qualitative analyses of "post-modern transformations", "digitalization challenges", or "sustainability narratives".
- **Engineering & IoT:** Technical studies on sensor hardware, IoT protocols, cloud platforms, or general AI frameworks for "Smart Agriculture" if they lack a rigorous physical evaluation of the water cycle or land surface processes. Also REJECT purely hydraulic engineering of irrigation systems (e.g., emitter discharge rates, pump efficiency, pipe design) without a larger hydrological or water resource context.
- **Local Irrigation Engineering:** **REJECT** irrigation studies (e.g., water balance of a specific field or local scheme) that focus on a single local area, specific crop, or irrigation system reliability without a broader physical integration into a catchment-scale or regional hydrological model.
- **Smart Agriculture (Management):** REJECT articles focusing on the adoption, market analysis, or business management of "smart farming" technologies.
- **Purely Agricultural:** Studies on specific crops (e.g., rice, sugar cane, ginger, etc.), yield optimization, pests, or fertilizer management that do not have a primary hydrological or water resource focus. This includes purely agronomic studies of water requirements for a single crop without a catchment-scale or regional resource management context.
- **Geophysics & Geomechanics:** Seismology, tectonics, or structural geology studies (e.g., "mountain bangs", fault dynamics, seismic monitoring) even if they occur within an aquifer, unless the primary focus is the water balance or resource management.
- **Purely Hydrogeological or Geochemical:** Studies on groundwater potential mapping (e.g., using AHP, GIS overlay for zonation), aquifer characterization, petrophysical modeling, or stratigraphic reconstructions of deep/offshore aquifers without a physical modeling of the active water cycle or surface-subsurface coupling. REJECT studies focused purely on geological structure, stratigraphy, or salinity mapping of deep fossil or offshore water resources.

**Disambiguation Rules:**
- **mHM:** ONLY relevant if it refers to the "mesoscale Hydrological Model". REJECT if it refers to "Modified Hald Model" or other microbiological models.
- **Climate Change:** REJECT if the paper is about general warming, emissions, or non-water impacts. ONLY accept if it models changes in streamflow, groundwater, soil moisture, or irrigation demand.

**INSTRUCTIONS:**
Analyze the provided Title and Abstract.
All output must be in English.

**CRITICAL:** Do NOT include any internal monologue, thoughts, or `<think>` blocks. Do NOT provide any introductory or concluding text. 
Return ONLY a valid JSON object.

{
  "relevant": true,
  "reason": "Short explanation linking to specific criteria."
}
"""

def load_topic_lists() -> tuple[list[str], list[str]]:
    """Reads topic whitelist and blacklist from RELEVANCE_CONTEXT.md."""
    try:
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent
        context_file = base_dir / "RELEVANCE_CONTEXT.md"
        
        if not context_file.exists():
            return [], []
            
        content = context_file.read_text()
        
        # 1. Topic Whitelist
        whitelist = []
        match_w = re.search(r"## Topic Whitelist \(Pre-screening\)\n(.*?)\n##", content, re.DOTALL)
        if match_w:
            whitelist = [t.strip().lower() for t in re.findall(r"-\s+(.+)", match_w.group(1))]
            
        # 2. Topic Blacklist
        blacklist = []
        match_b = re.search(r"## Topic Blacklist \(Immediate REJECT\)\n(.*?)\n##", content, re.DOTALL)
        if match_b:
            blacklist = [t.strip().lower() for t in re.findall(r"-\s+(.+)", match_b.group(1))]
            
        return whitelist, blacklist
    except Exception as e:
        logger.error(f"Error loading topic lists: {e}")
        return [], []

def load_journal_blacklist() -> list[str]:
    """Reads journal blacklist from RELEVANCE_CONTEXT.md."""
    try:
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent
        context_file = base_dir / "RELEVANCE_CONTEXT.md"
        
        if not context_file.exists():
            return []
            
        content = context_file.read_text()
        match = re.search(r"## Journal Blacklist \(Immediate REJECT\)\n(.*?)\n##", content, re.DOTALL)
        if match:
            return [j.strip().lower() for j in re.findall(r"-\s+(.+)", match.group(1))]
        
        return []
    except Exception as e:
        logger.error(f"Error loading journal blacklist: {e}")
        return []

SYSTEM_PROMPT = load_system_prompt()
TOPIC_WHITELIST, TOPIC_BLACKLIST = load_topic_lists()
JOURNAL_BLACKLIST = load_journal_blacklist()

class RelevanceFilter:
    def __init__(self, engine: str = RELEVANCE_ENGINE, model: str = RELEVANCE_MODEL):
        self.engine = engine
        self.model = model
        self.ollama_url = f"{OLLAMA_HOST}/api/generate"

    def check_relevance(self, paper: Paper) -> bool:
        logger.info(f"Checking relevance for: {paper.title[:50]}... using {self.engine}")
        
        # 1. BARRERA 1: Journal Blacklist (Immediate REJECT)
        if paper.source and JOURNAL_BLACKLIST:
            source_lower = paper.source.lower()
            for blocked_journal in JOURNAL_BLACKLIST:
                if blocked_journal in source_lower:
                    msg = f"Fast-track REJECTED: Journal '{paper.source}' is in the blacklist."
                    logger.info(f"❌ {msg}")
                    paper.is_relevant = False
                    paper.relevance_reason = msg
                    return False

        # 2. BARRERA 2: Topic Whitelist (Pre-screening)
        # We only apply this if OpenAlex actually returned topics.
        if paper.topics and TOPIC_WHITELIST:
            paper_topics_lower = [t.lower() for t in paper.topics]
            found_relevant_topic = False
            for allowed in TOPIC_WHITELIST:
                # Check for substring match (e.g. 'Hydrology' matches 'Stochastic Hydrology')
                if any(allowed in t for t in paper_topics_lower):
                    found_relevant_topic = True
                    break
            
            if not found_relevant_topic:
                msg = f"Fast-track REJECTED: No topics match the Whitelist."
                logger.info(f"❌ {msg} (Topics: {', '.join(paper.topics)})")
                paper.is_relevant = False
                paper.relevance_reason = msg
                return False

        # 3. BARRERA 3: Topic Blacklist (Immediate REJECT)
        if paper.topics and TOPIC_BLACKLIST:
            paper_topics_lower = [t.lower() for t in paper.topics]
            for blocked in TOPIC_BLACKLIST:
                if any(blocked in t for t in paper_topics_lower):
                    msg = f"Fast-track REJECTED: Paper belongs to blacklisted topic '{blocked.capitalize()}'."
                    logger.info(f"❌ {msg} (Topics: {', '.join(paper.topics)})")
                    paper.is_relevant = False
                    paper.relevance_reason = msg
                    return False

        # 4. BARRERA 4: LLM FILTER
        if self.engine == "gemini":
            return self._check_relevance_gemini(paper)
        else:
            return self._check_relevance_ollama(paper)

    def _check_relevance_gemini(self, paper: Paper) -> bool:
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not found. Falling back to Ollama.")
            return self._check_relevance_ollama(paper)

        prompt = f"Title: {paper.title}\n\nAbstract: {paper.abstract}\n"
        
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Using JSON mode for structured output if supported, or just prompt engineering
            response = client.models.generate_content(
                model=self.model,
                contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
                config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json"
                }
            )

            if response and response.text:
                # Record usage
                try:
                    usage = response.usage_metadata
                    # Costs for Gemini 1.5 Flash (approximate: Input $0.10/1M, Output $0.40/1M)
                    # Note: These rates might change, checking official pricing is good but this is an estimate.
                    # 1.5 Flash prices (Feb 2026): Input $0.075/1M, Output $0.30/1M (<128k context)
                    # Using the provided rates in synthesizer.py ($0.10/$0.40) for consistency or updating if needed.
                    # I'll stick to the one used in synthesizer for now or use the generic one.
                    # Let's use $0.10 and $0.40 as "safe" upper bounds or standard.
                    cost = (usage.prompt_token_count * 0.10 / 1_000_000) + (usage.candidates_token_count * 0.40 / 1_000_000)
                    db.add_usage(self.model, usage.prompt_token_count, usage.candidates_token_count, cost)
                except Exception as e:
                    logger.warning(f"Could not record usage: {e}")

                result = json.loads(response.text)
                paper.is_relevant = result.get("relevant", False)
                paper.relevance_reason = result.get("reason", "No reason provided.")
                
                if paper.is_relevant:
                    logger.info(f"✅ Paper is relevant: {paper.relevance_reason}")
                else:
                    logger.info(f"❌ Paper not relevant.")
                
                return paper.is_relevant
            
            return False

        except Exception as e:
            msg = f"Error calling Gemini: {e}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return False

    def _check_relevance_ollama(self, paper: Paper) -> bool:
        # Use config model if engine is ollama and model not specified or default to config
        model = self.model if self.engine == "ollama" else OLLAMA_FILTER_MODEL
        
        prompt = f"Title: {paper.title}\n\nAbstract: {paper.abstract}\n"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,  # Deterministic
                "num_predict": 200,   # Keep response short
                "stop": ["<think>", "</think>"] # Force stop thinking
            }
        }

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=300)
            response.raise_for_status()
            
            data = response.json()
            result = json.loads(data.get("response", "{}"))
            
            paper.is_relevant = result.get("relevant", False)
            paper.relevance_reason = result.get("reason", "No reason provided.")
            
            if paper.is_relevant:
                logger.info(f"✅ Paper is relevant: {paper.relevance_reason}")
            else:
                logger.info(f"❌ Paper not relevant.")
                
            return paper.is_relevant

        except Exception as e:
            msg = f"Error calling Ollama: {e}"
            logger.error(msg)
            db.add_event("ERROR", msg)
            return False
