# LaTeX Templates

This directory contains LaTeX templates for report rendering.

## Available Templates

### `vetrix/` (Default)

Professional medical report template with:

| File | Description |
|------|-------------|
| `main.tex` | Main template with section placeholders |
| `preamble.tex` | Package imports and custom macros |
| `sections.tex` | Section rendering templates |
| `tables.tex` | Table styles (booktabs) |
| `figures.tex` | Figure placement macros |

#### Features

- **Professional typography**: `microtype`, `fontspec` (XeLaTeX)
- **Publication-quality tables**: `booktabs`, `longtable`, `threeparttable`
- **Number formatting**: `siunitx` for consistent numeric display
- **Colored callouts**: `tcolorbox` for warnings, notes, implications
- **Cross-references**: `hyperref`, `cleveref` for internal links
- **Forest plots**: `pgfplots` for statistical visualizations

#### Placeholders

Templates use `{{PLACEHOLDER}}` syntax:

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `{{TITLE}}` | `report.metadata.title` | Report title |
| `{{AUTHORS}}` | `report.metadata.authors` | Author list |
| `{{DATE}}` | `report.metadata.publication_date` | Publication date |
| `{{CONTENT}}` | Rendered sections | Main report body |

## Creating Custom Templates

1. Copy `vetrix/` to a new directory (e.g., `custom/`)
2. Modify template files as needed
3. Use `--report-template custom` in CLI

### Template Requirements

- Must include `main.tex` as entry point
- Must define placeholders for metadata injection
- Should use UTF-8 encoding throughout
- XeLaTeX recommended for Unicode support

## Compilation

Templates are compiled using:

```bash
# Default (XeLaTeX)
xelatex -interaction=nonstopmode main.tex

# Fallback (pdfLaTeX)
pdflatex -interaction=nonstopmode main.tex
```

## Dependencies

Required LaTeX packages (included in TeX Live):

```
booktabs        # Professional tables
longtable       # Multi-page tables
threeparttable  # Table notes
siunitx         # Number formatting
caption         # Caption customization
subcaption      # Subfigures
xcolor          # Colors for traffic lights
hyperref        # Hyperlinks
cleveref        # Cross-references
pgfplots        # Forest plots
geometry        # Page layout
microtype       # Typography
tcolorbox       # Callout boxes
fontspec        # Font selection (XeLaTeX)
```

Install via:

```bash
# Debian/Ubuntu
sudo apt-get install texlive-latex-recommended texlive-fonts-recommended texlive-xetex

# macOS (MacTeX)
brew install --cask mactex

# Windows (MiKTeX)
# Download from https://miktex.org/
```

## Related Documentation

- [Report Generation Guide](../../docs/report.md)
- [Feature Specification](../../features/report-generation.md)
- [API Reference](../../API.md)
