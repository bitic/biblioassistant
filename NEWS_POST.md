# Nou projecte: BiblioAssistant, seguiment automàtic de la literatura científica

Mantenir-se al dia de les publicacions científiques és una tasca cada vegada més feixuga a causa del gran volum d'articles que es publiquen diàriament. Per facilitar aquesta tasca en els meus àmbits de recerca (hidrologia, clima i meteorologia), he creat **[BiblioAssistant](https://github.com/bitic/biblioassistant/)**.

BiblioAssistant és una eina automatitzada que monitoritza diverses fonts (via l'API d'OpenAlex i feeds RSS) i filtra els articles segons els interessos de recerca del grup d'**[Hidrologia i Canvi Climàtic](https://observatoriebre.gencat.cat)** de l'**[Observatori de l'Ebre](https://observatoriebre.gencat.cat)**.

El sistema utilitza una combinació de models de llenguatge locals (via Ollama) per al filtratge inicial i models més potents (com Gemini) per generar resums estructurats ("fitxes esteses") que inclouen la metodologia, dades, resultats i finançament de cada estudi rellevant.

Els resultats es publiquen automàticament al nou portal:

👉 **[biblio.quintanasegui.com](https://biblio.quintanasegui.com)**

El codi del projecte és totalment obert i es pot trobar a **[GitHub](https://github.com/bitic/biblioassistant/)**. El desenvolupament s'ha realitzat amb l'assistència d'eines d'IA, especialment **[Gemini CLI](https://geminicli.com)**.

Espero que aquesta eina sigui útil no només per al nostre grup, sinó per a qualsevol investigador interessat en les interaccions entre la superfície terrestre i l'atmosfera o en els extrems climàtics al Mediterrani.
