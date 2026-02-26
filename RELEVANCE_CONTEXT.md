# Relevance Context for [BiblioAssistant](https://github.com/bitic/biblioassistant/)

## Journal Blacklist (Immediate REJECT)
- VOCATIONAL Jurnal Inovasi Pendidikan Kejuruan
- Journal of Cleaner Production
- Sustainability
- Any journal focusing purely on "Education", "Vocational", "Social Sciences", or "Business".

## Topic Whitelist (Pre-screening)
Papers must have AT LEAST ONE of these topics/concepts to proceed to LLM:
- Hydrology
- Water Resources
- Land Surface Models
- Remote Sensing
- Soil Moisture
- Evapotranspiration
- Drought
- Flood
- Irrigation
- Meteorology
- Climatology
- Earth Science
- Environmental Science
- Catchment
- River
- Aquifer
- Groundwater
- Surface water
- Precipitation
- Runoff

## Topic Blacklist (Immediate REJECT)
- Vocational Education
- Vocational training
- Pedagogy
- Medical Education
- Clinical psychology
- Sociology
- Business Management
- Macroeconomics
- Political science
- Law
- Marketing
- Public administration
- Ethics

## Local Filter Prompt (Ollama & Gemini)

```text
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
- **Management & Planning:** **REJECT** studies on water systems resilience planning, benchmarking frameworks, cost-efficiency, decision-making under uncertainty, or water governance, even if they use hydrological data (e.g., CMIP6, flood data). The primary focus must be the **physical process** or its modeling, not the planning/economic framework.
- **Social Sciences:** Policy, management, or sociological studies without a quantitative physical/hydrological basis.
- **Engineering & IoT:** Technical studies on sensor hardware, IoT protocols, or general AI frameworks for "Smart Agriculture" if they lack a rigorous physical evaluation of the water cycle.
- **Local Irrigation Engineering:** **REJECT** irrigation studies that focus on a single local area, specific crop (e.g., rice, sugar cane), or irrigation system reliability without a broader physical integration into a catchment-scale or regional hydrological model.

**INSTRUCTIONS:**
Analyze the provided Title and Abstract.
All output must be in English.
Return ONLY a valid JSON object:
{
  "relevant": true/false,
  "reason": "Short explanation linking to specific criteria."
}
```
