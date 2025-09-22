# Medical Literature Data Extraction Schemas

Een uitgebreide collectie van JSON Schema's voor gestructureerde data-extractie uit medisch-wetenschappelijke artikelen. Deze schema's ondersteunen alle belangrijke onderzoeksmethodologieën en zorgen voor consistente, gevalideerde extractie van klinische studies, systematische reviews, en predictiemodellen.

## 📋 Overzicht van Schema's

| Schema | Onderzoekstype | Beschrijving | Status |
|--------|----------------|--------------|--------|
| [`common.schema.json`](#common-schema) | Gedeelde componenten | Herbruikbare definities voor alle schema's | ✅ Compleet |
| [`interventional_trial.schema.json`](#interventional-trial-schema) | Interventionele studies | RCT's, cluster trials, crossover studies | ✅ Compleet |
| [`observational_analytic.schema.json`](#observational-analytic-schema) | Observationele studies | Cohort, case-control, cross-sectioneel | ✅ Compleet |
| [`evidence_synthesis.schema.json`](#evidence-synthesis-schema) | Evidence synthese | Systematische reviews, meta-analyses | ✅ Compleet |
| [`prediction_prognosis.schema.json`](#prediction-prognosis-schema) | Predictiemodellen | Prognostische modellen, validatiestudies | ✅ Compleet |
| [`editorials_opinion.schema.json`](#editorial-opinion-schema) | Non-research content | Editorials, commentaries, opinies | ✅ Compleet |

## 🏗️ Modulaire Architectuur

Alle schema's gebruiken een **modulaire architectuur** waarbij gemeenschappelijke componenten worden gedeeld via `common.schema.json`:

```json
{
  "language": { "$ref": "common.schema.json#/$defs/LanguageCode" },
  "metadata": { "$ref": "common.schema.json#/$defs/Metadata" },
  "risk_of_bias": { "$ref": "common.schema.json#/$defs/RiskOfBias" }
}
```

### Voordelen:
- 🔄 **Herbruikbaarheid**: Geen duplicatie van definities
- 🎯 **Consistentie**: Uniforme structuren across schema's
- 🛠️ **Onderhoud**: Centraal beheer van gemeenschappelijke componenten
- 📦 **Bundling**: Compatible met standalone schema generatie

---

## 📚 Schema Documentatie

### Common Schema

**`common.schema.json`** - Gedeelde definities voor alle schema's

#### Belangrijkste componenten:
- **Metadata**: Auteurs, journal info, DOI, registratienummers
- **SourceRef**: Verwijzingen naar tabellen, figuren, pagina's
- **RiskOfBias**: RoB2, ROBINS-I, PROBAST ondersteuning
- **ContrastEffect**: Effect measures (RR, OR, HR, MD, SMD, IRR)
- **ParsedTable/FigureSummary**: Geëxtraheerde tabellen en figuren
- **ISO8601Duration**: Gestandaardiseerde tijdsduren
- **CountryCode/LanguageCode**: Gevalideerde land- en taalcodes

---

### Interventional Trial Schema

**`interventional_trial.schema.json`** - Voor interventionele studies

#### Ondersteunde studietypes:
- **RCT**: Randomized Controlled Trial
- **Cluster-RCT**: Cluster gerandomiseerde studies
- **Crossover-RCT**: Crossover ontwerpen
- **Factorial-RCT**: Factoriële ontwerpen
- **Stepped-wedge**: Stepped-wedge cluster trials
- **Adaptive**: Adaptieve trials
- **Nonrandomized**: Niet-gerandomiseerde interventies
- **Before-after**: Voor-na vergelijkingen
- **Single-arm**: Eenarmige studies

#### Kernstructuren:
```json
{
  "study_design": {
    "label": "RCT",
    "randomisation": "individual",
    "blinding": "double-blind"
  },
  "arms": [
    { "arm_id": "intervention", "label": "Treatment A" },
    { "arm_id": "control", "label": "Placebo" }
  ],
  "outcomes": [
    { "outcome_id": "primary", "name": "Mortality", "type": "binary" }
  ]
}
```

#### Validatieregels:
- RCT's vereisen `randomisation ≠ "none"`
- Cluster-RCT's vereisen `cluster_unit` en `clusters_per_arm`
- Crossover studies vereisen `periods ≥ 2`
- Minstens één primaire uitkomst vereist

---

### Observational Analytic Schema

**`observational_analytic.schema.json`** - Voor observationele studies

#### Ondersteunde studietypes:
- **Cohort**: Prospectief/retrospectief cohort
- **Case-control**: Case-control studies
- **Cross-sectional**: Cross-sectionele studies
- **Ecological**: Ecologische studies

#### Kernstructuren:
```json
{
  "study_design": {
    "label": "Cohort",
    "cohort_direction": "prospective",
    "follow_up_scheme": "Fixed intervals"
  },
  "exposures": [
    { "name": "Smoking", "type": "categorical", "categories": ["Never", "Former", "Current"] }
  ],
  "groups": [
    { "group_id": "exposed", "label": "Smokers" },
    { "group_id": "unexposed", "label": "Non-smokers" }
  ]
}
```

#### Geavanceerde analyses:
- **Confounding adjustment**: Covariaat lijst en methoden
- **Propensity scores**: Matching, weighting, stratificatie
- **Causal inference**: IV, IPW, g-methods ondersteuning

---

### Evidence Synthesis Schema

**`evidence_synthesis.schema.json`** - Voor systematische reviews en meta-analyses

#### Ondersteunde synthesetypes:
- **Systematic review**: Kwalitatieve synthese
- **Meta-analysis**: Pairwise meta-analyse
- **Network meta-analysis**: Indirecte vergelijkingen
- **Individual patient data**: IPD meta-analyse
- **Living systematic review**: Continue updates

#### Kernstructuren:
```json
{
  "search_strategy": {
    "databases": ["PubMed", "Embase", "Cochrane"],
    "search_date": "2024-01-15",
    "limits": ["human", "English"]
  },
  "included_studies": [
    { "study_id": "smith2023", "design": "RCT", "participants": 150 }
  ],
  "syntheses": [
    { "type": "pairwise", "outcome": "mortality", "effect": "RR", "heterogeneity": "I2=45%" }
  ]
}
```

#### PRISMA ondersteuning:
- **Flow diagram**: Screening en selectieproces
- **GRADE assessment**: Evidence certainty
- **Publication bias**: Funnel plots, Egger test

---

### Prediction Prognosis Schema

**`prediction_prognosis.schema.json`** - Voor predictiemodellen en prognostische studies

#### TRIPOD categorieën:
- **Development**: Model ontwikkeling
- **Internal validation**: Interne validatie
- **External validation**: Externe validatie
- **Temporal validation**: Temporele validatie
- **Update**: Model updates
- **Impact**: Implementatiestudies

#### Kernstructuren:
```json
{
  "models": [
    {
      "algorithm": "logistic",
      "predictors_used": ["age", "sex", "comorbidity"],
      "coefficients": [
        { "predictor": "age", "beta": 0.05, "se": 0.01 }
      ]
    }
  ],
  "performance": [
    {
      "discrimination": { "auc_roc": { "point": 0.75, "ci": [0.70, 0.80] } },
      "calibration": { "slope": 0.95, "intercept": 0.02 }
    }
  ]
}
```

#### Performance metrics:
- **Discriminatie**: AUC-ROC, C-statistic, PR-AUC
- **Calibratie**: Slope, intercept, Brier score
- **Clinical utility**: Decision curves, net benefit

---

### Editorial Opinion Schema

**`editorials_opinion.schema.json`** - Voor non-research content

#### Ondersteunde types:
- **Editorial**: Redactionele commentaren
- **Commentary**: Wetenschappelijke commentaren
- **Opinion**: Opiniestukken
- **Correspondence**: Brieven en reacties

#### Minimale structuur:
```json
{
  "content_type": "editorial",
  "stance_overall": "supportive",
  "thesis": "Implementation of AI in clinical practice requires careful validation",
  "arguments": [
    { "point": "Safety concerns", "evidence_type": "expert_opinion" }
  ]
}
```

---

## 🛠️ Gebruik en Implementatie

### Basisgebruik

1. **Schema selectie**: Kies het juiste schema op basis van studieontwerp
2. **Validatie**: Gebruik JSON Schema validators
3. **Extractie**: Vul de vereiste velden in volgens de specificaties

### Bundling voor Standalone Gebruik

Voor situaties waarbij externe referenties niet gewenst zijn:

```bash
python json-bundler.py
```

Dit genereert standalone schema's met alle common definities geïnternaliseerd.

### Integratie in Extractie Pipeline

```python
import json
import jsonschema

# Laad schema en valideer data
with open('interventional_trial.schema.json', 'r') as f:
    schema = json.load(f)

# Valideer geëxtraheerde data
jsonschema.validate(extracted_data, schema)
```

---

## 🔮 Toekomstige Uitbreidingen

Geplande schema's voor specifieke domeinen:

### Diagnostische Studies
- **`diagnostic_accuracy.schema.json`**
- STARD-compliant extractie
- 2×2 tabellen, ROC curves, cut-off analyses

### Health Economics
- **`health_econ.schema.json`**
- CEA/CUA/CBA/BIA studies
- Markov modellen, QALY, ICER

### Implementation Science
- **`implementation_qi.schema.json`**
- PDSA cycles, mixed methods
- Context en procesvariabelen

### Preclinical Research
- **`preclinical_lab.schema.json`**
- ARRIVE-compliant dierstudies
- In-vitro en omics pipelines

---

## 📋 Classifier Mapping

Voor automatische schema selectie zijn de volgende labels gedefinieerd:

| Label | Schema | Beschrijving |
|-------|--------|--------------|
| `interventional_trial` | interventional_trial.schema.json | RCT's en interventies |
| `observational_analytic` | observational_analytic.schema.json | Observationele analyses |
| `evidence_synthesis` | evidence_synthesis.schema.json | Systematische reviews |
| `prediction_prognosis` | prediction_prognosis.schema.json | Predictiemodellen |
| `editorial_opinion` | editorials_opinion.schema.json | Editorials en opinies |
| `other` | - | Niet-geclassificeerde content |

---

## ⚙️ Technische Specificaties

- **JSON Schema versie**: Draft 2020-12
- **Encoding**: UTF-8
- **Validatie**: Volledige constraint ondersteuning
- **Compatibiliteit**: Cross-platform, taal-agnostisch
- **Documentatie**: Inline beschrijvingen en voorbeelden

---

## 📄 Licentie en Bijdragen

Deze schema's zijn ontwikkeld voor medisch-wetenschappelijk onderzoek en data-extractie. Voor bijdragen of suggesties, zie de hoofdrepository.

**Laatste update**: September 2025
