import requests
import json
import re
from src.config import OLLAMA_HOST, OLLAMA_FILTER_MODEL, RELEVANCE_ENGINE, RELEVANCE_MODEL, GEMINI_API_KEY
from src.models import Paper
from src.logger import logger
from src.db import db

SYSTEM_PROMPT = """
You are an expert research assistant for a Senior Hydrologist and Climate Scientist. 
Your task is to filter scientific papers based on their Title and Abstract.

**User Profile:**
The user works on Land Surface Interactions, Hydrometeorological Modeling, and Climate Extremes (Droughts/Floods) in the Mediterranean.

**Criteria for RELEVANT:**
1.  **Core Subjects:** Land Surface Models (LSM), Soil Moisture, Evapotranspiration, Runoff generation, Groundwater recharge.
2.  **Specific Models/Tools:** ISBA, SURFEX, SAFRAN, MODCOU, ORCHIDEE, SWAT, mHM (Samaniego), JULES, Sentinel-1, SMOS, SWOT.
3.  **Phenomena:** Drought propagation, Drought indicators/indices, Flash floods, Heatwaves, Climate Change impacts on hydrological cycle and water resources.
4.  **Techniques:** Downscaling (Bias correction), Data Assimilation.
5.  **Remote Sensing & Irrigation:** Remote sensing of soil moisture, Irrigation mapping and quantification (RS), Irrigation simulation in LSMs, Irrigation recommendation methods.
6.  **Region:** Mediterranean, Pyrenees, Spain, France, Southern Europe.

**Criteria for NOT RELEVANT:**
- Purely marine/oceanography (unless coastal aquifers).
- Purely atmospheric dynamics without surface coupling.
- Social sciences/policy without quantitative physical basis.
- Studies on specific crops/agriculture without hydrological perspective.

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

class RelevanceFilter:
    def __init__(self, engine: str = RELEVANCE_ENGINE, model: str = RELEVANCE_MODEL):
        self.engine = engine
        self.model = model
        self.ollama_url = f"{OLLAMA_HOST}/api/generate"

    def check_relevance(self, paper: Paper) -> bool:
        logger.info(f"Checking relevance for: {paper.title[:50]}... using {self.engine}")
        
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
