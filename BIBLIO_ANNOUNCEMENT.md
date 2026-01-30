# Naixement de BiblioAssistant i biblio.quintanasegui.com

Avui, 29 de gener de 2026, he posat en marxa **BiblioAssistant** (SCRC - Sistema de Curació i Resum Científic), un projecte personal per automatitzar la vigilància tecnològica i científica en els àmbits de la hidrologia, el clima i la meteorologia. Amb aquest sistema, també neix el portal **[biblio.quintanasegui.com](https://biblio.quintanasegui.com)**, on publicaré els resums generats automàticament.

### Com funciona BiblioAssistant?

El sistema funciona com una "cascada de filtratge" per gestionar el gran volum de publicacions diàries sense morir en l'intent ni disparar els costos de computació:

1.  **Ingesta (Discovery):** Utilitzo l'API d'**OpenAlex** per monitoritzar autors específics (com jo mateix i els meus col·laboradors), citacions dels meus treballs, i una llista seleccionada de revistes d'alt impacte (WRR, JHM, HESS, etc.). També tinc la capacitat de llegir feeds RSS tradicionals.
2.  **Filtratge Local (Ollama):** Per mantenir la privadesa i reduir costos, tots els articles descoberts passen per un primer filtre local utilitzant **Ollama** (amb models com Llama 3.1 o DeepSeek-R1). Aquest model analitza el títol i el resum segons uns criteris de rellevància molt específics (models de superfície, sequeres, Pirineus, teledetecció de la humitat del sòl, reg, etc.). Només els articles realment interessants passen a la següent fase.
3.  **Extracció de Text Complet:** Si un article és rellevant, el sistema intenta descarregar el PDF original i n'extreu el text complet, preparant-lo per a la síntesi profunda.
4.  **Síntesi i Resum (Gemini API):** El text de l'article s'envia a models de llenguatge avançats (com **Gemini 1.5 Pro**) per generar una "Fitxa Estesa". Aquesta fitxa no és un simple resum: identifica el finançament, la metodologia, les dades utilitzades (satèl·lits, reanàlisis), els resultats quantitatius i la contribució original respecte a la literatura existent. Tot es normalitza al Sistema Internacional d'Unitats (SI).
5.  **Generació del Lloc Estàtic:** Finalment, el sistema genera un lloc web estàtic utilitzant plantilles Jinja2, organitzant els resums per cronologia i arxiu, i el publica automàticament al servidor.

### Objectius i Filosofia

L'objectiu no és substituir la lectura profunda, sinó filtrar el soroll i tenir una base de dades estructurada i searchable de la recerca que realment impacta en la meva feina. És un sistema dissenyat per ser eficient: processament local per al "soroll" i APIs potents només per al "senyal".

---

### Properes passes (Taques pendents)

- [ ] **Seguiment de costos:** Implementar un sistema de logging per monitoritzar l'ús de tokens i el cost econòmic de l'API de Gemini/Claude.
- [ ] **Millora de l'extracció de taules:** Optimitzar l'extracció de dades quantitatives de les taules dels PDFs, que sovint es perden en la conversió a text.
- [ ] **Integració amb Delta Chat:** Afegir un mòdul per rebre els resums diaris directament a través d'un grup de Delta Chat.
- [ ] **Cerca semàntica:** Implementar una cerca vectorial (embeddings) sobre els resums generats per trobar connexions entre papers de diferents anys.
- [ ] **Promoció automàtica:** Refinar la lògica que detecta quins autors o revistes apareixen sovint com a rellevants per afegir-los automàticament a la llista de monitoratge.

Pere Quintana Seguí
29 de gener de 2026
