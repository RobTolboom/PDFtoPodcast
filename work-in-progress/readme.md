Heb bewust geen schema's gemaakt voor de volgende soorten studies aangezien deze niet vaak voorkomen of relevant zijn voor de anesthesiologie:

1) Diagnostic Accuracy (één schema)
diagnostic_accuracy.schema.json (STARD-achtig) Dekt: index-test(s) vs referentiestandaard, thresholds, 2×2-tabellen per drempel, sensitiviteit/specificiteit/PLR/NLR, ROC/AUC, subgroep-/cut-off-analyses. Waarom apart? Volledig ander kernobject (2×2 per drempel/test), geen “arms”.

2) Health Economics & Decision Modeling (één schema, optioneel)
health_econ.schema.json Dekt: CEA/CUA/CBA/BIA, decision-trees/Markov, perspectief, horizon, kostenbronnen, QALY, ICER, onzekerheidsanalyses (DSA/PSA). Waarom apart? Structuur rond modellen en kosten/utility—anders dan klinische effectschattingen.

3) Implementation / Quality Improvement / Mixed Methods (één schema, optioneel)
implementation_qi.schema.json Dekt: QI/implementatiestudies (PDSA-cycli, context, proces-/balans-uitkomsten), mixed methods met kwalitatieve component (thema’s/codes). Waarom apart? Proces- en contextvariabelen + kwalitatieve synthese → andere resultstructuur.

4) Preclinical & Lab (één schema, optioneel)
preclinical_lab.schema.json Dekt: dierstudies (ARRIVE-achtig), in-vitro/omics (pipelines, QC-metrics). Waarom apart? Andere entiteiten (species/assays), geen “arms” zoals in klinische trials.

5) Protocols & Methods (compact, optioneel)
protocol_methods.schema.json Dekt: trial protocol, systematic review protocol, statistical analysis plan (SAP), methods papers. Waarom samen? Documenteert plannen/methoden; geen (definitieve) resultaten.

10) Editorials & Opinion (ultra-simpel, optioneel)
editorial_opinion.schema.json Dekt: editorial, commentary, viewpoint, correspondence. Waarom? Voor volledigheid in je corpus; extractie minimaal (alleen Metadata + samenvatting).




Nog te doen:
1. Classifier maken die één van onderstaande labels geeft; die mapt 1-op-1 op het schema:
	interventional_trial
	observational_analytic
	evidence_synthesis
	prediction_prognosis
	editorial_opinion
	other
