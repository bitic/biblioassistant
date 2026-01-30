import requests
import json
import re
from src.config import OLLAMA_HOST, OLLAMA_FILTER_MODEL
from src.models import Paper
from src.logger import logger

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

class LocalFilter:
    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_FILTER_MODEL):
        self.url = f"{host}/api/generate"
        self.model = model

    def check_relevance(self, paper: Paper) -> bool:
        prompt = f"Title: {paper.title}\n\nAbstract: {paper.abstract}\n"
        
        payload = {
            "model": self.model,
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
            logger.info(f"Checking relevance for: {paper.title[:50]}...")
            response = requests.post(self.url, json=payload, timeout=300)
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
            from src.db import db
            db.add_event("ERROR", msg)
            # In case of error, we default to False but could be safer to True to not miss anything?
            # Given it's a "Daily" script, better to skip or retry.
            return False
