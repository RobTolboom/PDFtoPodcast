# 📁 src/ — Projectstructuur

In deze map staat de kern van de **PDF → Podcast pipeline**.
De code is modulair opgezet, zodat iedere component een duidelijke verantwoordelijkheid heeft.

---

## Bestandsoverzicht

### ⚙️ `config.py`
- Leest instellingen uit `.env` (API key, model, tokens).
- Bundelt alles in een `Settings` object dat overal hergebruikt kan worden.
- Voorkomt hardcoded secrets in de code.

---

### 📄 `pdf_io.py`
- Opent en leest PDF-bestanden met **PyMuPDF**.

---

### 💬 `prompts.py`
- Bevat de **systeeminstructies (prompts)** voor de LLM:
  - **Extractie**: haal kernmetadata en inhoud uit de PDF-tekst.
  - **Appraisal**: valideer en corrigeer de JSON.
  - **Rapportage**: genereer podcastscript, shownotes en rapport.

---

### 🗂️ `schemas.py`
- Definieert **Pydantic-modellen** die de structuur van de JSON-output afdwingen:
  - `Extraction`: titel, auteurs, abstract, key points, secties.
  - `Appraisal`: lijst met issues + verbeterde extractie.
  - `Deliverables`: podcastscript, shownotes, rapport.

---

### 🤖 `llm.py`
- Wrapper rond de **OpenAI Python client**.
- Functies:
  - `respond_json()`: vraag LLM om gestructureerde JSON volgens schema.
  - `respond_text()`: vraag LLM om platte tekst.
- Ingebouwde retries & backoff via `tenacity`.

---

### 🛠️ `utils.py`
- Kleine hulpmethodes:
  - `ensure_out_dir()`: maakt `out/` map aan.
  - `write_json()`: schrijft JSON weg met nette formatting.
  - `timestamp()`: maakt tijdstempel voor bestandsnamen.

---

### 🔗 `pipeline.py`
- **Hoofd-orkestratie van de pipeline**:
  1. PDF → tekst (`pdf_io`)
  2. Tekst → JSON-extractie (`llm` + `prompts`)
  3. Validatie/appraisal (`llm`)
  4. Genereren van deliverables (`llm`)
  5. Wegschrijven van resultaten (`utils`)
- Retourneert ook een dict met alle resultaten voor gebruik in code.

---

## Output
Na een run met `run_pipeline.py` worden in `out/` bestanden weggeschreven:
- `*_01_extraction.json` → ruwe extractie
- `*_02_appraisal.json` → validatie + verbeterde JSON
- `*_03_outputs.json` → eindresultaten (script, shownotes, rapport)
- `*_podcast_script.md`, `*_shownotes.md`, `*_rapport.md`
