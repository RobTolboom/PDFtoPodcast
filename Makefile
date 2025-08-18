# Makefile voor PDFtoPodcast project

# Variabelen
PYTHON := python
PIP := pip
VENV := .venv/bin

# --------------------------------------
# Basiscommando's
# --------------------------------------

# Installeer dependencies in je venv
install:
	$(PIP) install -r requirements.txt

# Verwijder __pycache__ etc.
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	rm -rf out/*

# --------------------------------------
# Code quality
# --------------------------------------

# Lint met Ruff (check)
lint:
	$(VENV)/ruff check .

# Fix lint errors automatisch
lint-fix:
	$(VENV)/ruff check . --fix

# Format met Black
fmt:
	$(VENV)/black .

# Combineer lint + format
check: lint fmt

# --------------------------------------
# Pipeline runnen
# --------------------------------------

# Run pipeline op test.pdf (max 2 pagina's)
test:
	$(PYTHON) run_pipeline.py "test.pdf" --max-pages 2

# Run pipeline op willekeurige PDF (pad meegeven)
run:
	$(PYTHON) run_pipeline.py "$(file)" --max-pages 5
