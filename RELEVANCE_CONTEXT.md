# Relevance Context for [BiblioAssistant](https://github.com/bitic/biblioassistant/)

## Journal Blacklist (Immediate REJECT)
- VOCATIONAL Jurnal Inovasi Pendidikan Kejuruan
- Journal of Cleaner Production
- Sustainability
- Fractal and Fractional
- Any journal focusing purely on "Education", "Vocational", "Social Sciences", "Business", or "Marine Biology".

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
- Catchment
- River
- Precipitation
- Runoff
- **Machine Learning**
- **Artificial Intelligence**
- **Deep Learning**

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
- Marine biology
- Oceanography
- Marine science
- Fisheries
- Submarine groundwater discharge
- Mathematics (Pure)
- Fractals
- Plant physiology (unless related to ET/Hydrology)
- Botany
- Zoology
- Microbiology
- Epidemiology
- Geomechanics
- Geotechnics
- Seismology
- Landslides
- Subsidence
- Structural Geology
- **Water Quality** (Heavy Metals, Wastewater, Sanitation, Contamination)
- **Geomorphology & Erosion** (Sediment transport, badlands)
- **Geodesy & GNSS** (ZTD, Tropospheric delay)

## Local Filter Prompt (Ollama & Gemini)

```text
You are an expert research assistant for a Senior Hydrologist and Climate Scientist. 
Your task is to filter scientific papers based on their Title and Abstract.

**User Profile:**
The user is a Senior Hydrologist focusing on the **physical water cycle**, **Hydrometeorology**, and **Irrigation Optimization**. The scope ranges from **plot-scale irrigation** to **global climate modeling**.

**Criteria for RELEVANT:**
1.  **Hydrometeorology & Modeling:** Land Surface Models (LSM), Soil Moisture (satellite/in-situ/modeled), Evapotranspiration, Runoff, and surface-subsurface coupling. 
2.  **Machine Learning in Hydrology:** Application of ML/AI/Deep Learning for predicting soil moisture, streamflow, drought, or optimizing water use.
3.  **Irrigation (Plot to Global Scale):** Irrigation recommendations, mapping, and modeling. 
    *   **ACCEPT** plot-scale studies IF they are based on **Physical Models**, **Remote Sensing** (e.g., Sentinel-1/2, SMOS, SMAP, SWOT), or **Machine Learning**.
    *   **ACCEPT** irrigation-atmosphere coupling and LSM-scale irrigation.
4.  **Climate Extremes:** Physical analysis and forecasting of droughts and floods at regional/global scales.
5.  **Specific Models/Tools:** ISBA, SURFEX, SAFRAN, MODCOU, ORCHIDEE, SWAT, mHM, JULES, VIC, and standard satellite missions (Sentinel, Landsat, etc.).
6.  **Methodological Frameworks:** Data Assimilation, Hydrological downscaling/bias correction, and physical risk assessment.

**Criteria for NOT RELEVANT (REJECT):**
- **Pure/Chemical Hydrogeology:** **REJECT** groundwater studies focusing on geochemistry, deep aquifers, fossil water, or petrophysics without surface coupling or active water cycle modeling.
- **Water Quality & Contamination:** **REJECT** studies on heavy metals, pollutants, wastewater treatment, sanitation, or chemical water properties. 
- **Geomorphology & Erosion:** **REJECT** studies on soil erosion, badlands, sediment transport, or slope stability.
- **Tracers:** **REJECT** papers focused exclusively on chemical/isotopic tracers (Tritium, etc.) without a physical modeling context.
- **Geodesy & GNSS:** **REJECT** studies on GNSS/GPS, Zenith Tropospheric Delay (ZTD), or specialized atmospheric physics without a clear hydrological application.
- **Agronomy (Traditional):** **REJECT** purely agronomic studies focusing on crop yield, fertilizers, pests, or seed varieties. 
- **Hydraulic Engineering:** **REJECT** purely mechanical studies on pump efficiency, pipe networks, or civil infrastructure (dams/canals) without a hydrological/climatic context.
- **Management & Policy:** **REJECT** studies on governance, cost-efficiency, or socio-economics.

**Regional Criteria:**
- **Primary Interest:** Global scale studies.
- **Secondary Interest:** Mediterranean area and Mediterranean-climate regions (e.g., California, Chile, South Africa, parts of Australia).
- **REJECT:** Studies focused solely on tropical or arctic regions (unless they are global in scope).

**INSTRUCTIONS:**
Analyze the provided Title and Abstract.
All output must be in English.

**CRITICAL:** Do NOT include any internal monologue, thoughts, or `<think>` blocks. Do NOT provide any introductory or concluding text. 
Return ONLY a valid JSON object:
{
  "relevant": true,
  "reason": "Short explanation linking to specific criteria."
}
```
