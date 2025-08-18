# schemas.py

from textwrap import dedent

code = dedent(
    """
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Dict, Union

from pydantic import BaseModel, Field, ConfigDict, constr, conint, conlist, confloat


# -------------------------
# Common / shared types
# -------------------------

HexSha256 = constr(pattern=r'^[A-Fa-f0-9]{64}$')
VersionTag = constr(pattern=r'^v\\d+\\.\\d+(\\.\\d+)?$')
Iso639_1 = constr(pattern=r'^[a-z]{2}$')
Iso8601Duration = constr(pattern=r'^P(T)?[\\dYMDHMS]+$')
ISSNPattern = constr(pattern=r'^(\\d{4}-\\d{3}[\\dxX])$')
ORCIDPattern = constr(pattern=r'^\\d{4}-\\d{4}-\\d{4}-\\d{3}[\\dX]$')
DOIPattern = constr(pattern=r'^10\\.\\d{4,9}/[-._;()/:A-Z0-9]+$')
PMIDPattern = constr(pattern=r'^\\d{1,8}$')
PMCIDPattern = constr(pattern=r'^PMC\\d+$')
StudyIdPattern = constr(pattern=r'^[A-Za-z0-9._-]+$')
CountryAlpha2 = constr(pattern=r'^[A-Z]{2}$')


# -------------------------
# $defs ported to Pydantic
# -------------------------

class SourceRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    anchor: Optional[str] = Field(
        None, description="Free-text pointer like 'Table 2', 'Fig 1', or sentence quote"
    )
    page: Optional[conint(ge=1)] = None
    figure_id: Optional[str] = None
    table_id: Optional[str] = None


class Author(BaseModel):
    model_config = ConfigDict(extra='forbid')
    last_name: str
    initials: Optional[str] = None
    given_names: Optional[str] = None
    orcid: Optional[ORCIDPattern] = None
    affiliations: List[str] = Field(default_factory=list)
    corresponding: bool = False


class RegistryEnum(str, Enum):
    ClinicalTrials_gov = "ClinicalTrials.gov"
    ISRCTN = "ISRCTN"
    EudraCT = "EudraCT"
    ChiCTR = "ChiCTR"
    ANZCTR = "ANZCTR"
    Other = "Other"


class Registration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    registry: Optional[RegistryEnum] = None
    identifier: Optional[str] = None
    url: Optional[str] = Field(default=None)  # format uri is not re-enforced by Pydantic without custom validator


class Metadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    journal: str
    journal_abbrev: Optional[str] = None

    published_date: Optional[date] = None
    published_date_precision: Optional[str] = Field(
        default=None, pattern=r'^(year|month|day)$'
    )

    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    page_start: Optional[str] = None
    page_end: Optional[str] = None
    article_number: Optional[str] = None
    elocation_id: Optional[str] = None

    issn: Optional[ISSNPattern] = None
    eissn: Optional[ISSNPattern] = None

    authors: List[Author] = Field(default_factory=list)

    pmid: Optional[PMIDPattern] = None
    pmcid: Optional[PMCIDPattern] = None
    doi: Optional[DOIPattern] = Field(
        default=None, description="Case-insensitive"
    )

    registration: Optional[Registration] = None
    protocol_ref: Optional[str] = None
    funding: Optional[str] = None
    conflict_of_interest: Optional[str] = None

    epub_ahead_of_print_date: Optional[str] = None

    vancouver_citation: Optional[str] = None
    vancouver_source: Optional[SourceRef] = None

    source: Optional[SourceRef] = None


class StudyDesignLabel(str, Enum):
    RCT = "RCT"
    Cohort = "Cohort"
    Case_control = "Case-control"
    Cross_sectional = "Cross-sectional"
    Before_after = "Before-after"
    Other = "Other"


class YesNoUnclear(str, Enum):
    yes = "yes"
    no = "no"
    unclear = "unclear"


class PopContext(str, Enum):
    adult = "adult"
    pediatric = "pediatric"
    mixed = "mixed"
    unclear = "unclear"


class Randomisation(str, Enum):
    individual = "individual"
    cluster = "cluster"
    blocked = "blocked"
    stratified = "stratified"
    minimisation = "minimisation"
    none = "none"
    unclear = "unclear"


class Concealment(str, Enum):
    adequate = "adequate"
    inadequate = "inadequate"
    unclear = "unclear"


class Blinding(str, Enum):
    open_label = "open-label"
    single_blind = "single-blind"
    double_blind = "double-blind"
    triple_blind = "triple-blind"
    unclear = "unclear"


class AnalysisPopulation(str, Enum):
    ITT = "ITT"
    mITT = "mITT"
    PP = "PP"
    Safety = "Safety"
    Other = "Other"


class StudyDesign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: StudyDesignLabel
    ethics_approval: Optional[str] = None
    consent_obtained: Optional[YesNoUnclear] = None
    population_context: Optional[PopContext] = None
    design_details: Optional[str] = None
    centres: Optional[conint(ge=1)] = None
    countries: List[CountryAlpha2] = Field(default_factory=list)
    setting: Optional[str] = None
    randomisation: Optional[Randomisation] = None
    allocation_concealment: Optional[Concealment] = None
    blinding: Optional[Blinding] = None
    analysis_population: Optional[AnalysisPopulation] = None
    non_inferiority_margin: Optional[str] = None
    source: Optional[SourceRef] = None


class Population(BaseModel):
    model_config = ConfigDict(extra='forbid')
    n_randomised: conint(ge=1)

    n_screened: Optional[conint(ge=0)] = None
    n_analysed: Optional[conint(ge=0)] = None
    age_mean: Optional[float] = None
    age_sd: Optional[confloat(ge=0)] = None
    sex_female_pct: Optional[confloat(ge=0, le=100)] = None
    asa_distribution: Optional[str] = None
    bmi_mean: Optional[float] = None
    bmi_sd: Optional[confloat(ge=0)] = None
    comorbidities_key: Optional[str] = None
    surgery_type: Optional[str] = None
    urgency: Optional[str] = None
    inclusion_criteria: Optional[str] = None
    exclusion_criteria: Optional[str] = None
    follow_up_duration_iso8601: Optional[Iso8601Duration] = Field(
        default=None, description="ISO 8601 duration, e.g. 'P30D', 'PT24H'"
    )

    class MissingData(BaseModel):
        model_config = ConfigDict(extra='forbid')
        outcome_missing_pct: Optional[confloat(ge=0, le=100)] = None
        imputation: Optional[str] = None

    missing_data: Optional[MissingData] = None
    source: Optional[SourceRef] = None


class Intervention(BaseModel):
    model_config = ConfigDict(extra='forbid')
    arm_id: str
    arm_label: str
    description: Optional[str] = None
    dose_regimen: Optional[str] = None
    route_timing: Optional[str] = None
    co_interventions: Optional[str] = None
    anesthesia_technique: Optional[str] = None
    airway_management: Optional[str] = None
    monitoring: Optional[str] = None
    neuromuscular_block: Optional[str] = None
    analgesia_strategy: Optional[str] = None
    source: Optional[SourceRef] = None


class Arm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    arm_id: str
    label: str
    n_assigned: Optional[conint(ge=0)] = None
    n_analysed: Optional[conint(ge=0)] = None
    description: Optional[str] = None


class Comparison(BaseModel):
    model_config = ConfigDict(extra='forbid')
    comparison_id: str
    arm_a: str
    arm_b: str
    is_primary: bool = False


class OutcomeType(str, Enum):
    binary = "binary"
    continuous = "continuous"
    time_to_event = "time_to_event"
    ordinal = "ordinal"
    count = "count"


class DirectionOfBenefit(str, Enum):
    higher_better = "higher_better"
    lower_better = "lower_better"
    neutral_or_na = "neutral_or_na"


class Outcome(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome_id: str
    name: str
    definition: Optional[str] = None
    type: OutcomeType
    is_primary: bool = False
    direction_of_benefit: Optional[DirectionOfBenefit] = None
    unit: Optional[str] = None
    timepoint: Optional[str] = None
    timepoint_iso8601: Optional[Iso8601Duration] = None
    measurement_method: Optional[str] = None
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    source: Optional[SourceRef] = None
    unit_ucum: Optional[str] = Field(default=None, description="UCUM code if available")


class EffectCI(BaseModel):
    model_config = ConfigDict(extra='forbid')
    level: Optional[confloat()] = Field(default=95, description="e.g. 95")
    lower: float
    upper: float


class ContrastEffectType(str, Enum):
    RR = "RR"
    OR = "OR"
    HR = "HR"
    MD = "MD"
    SMD = "SMD"
    RD = "RD"
    RMST = "RMST"
    Other = "Other"


class ContrastEffect(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: ContrastEffectType
    point: float
    ci: Optional[EffectCI] = None
    p_value: Optional[confloat(ge=0, le=1)] = None


class PerArmResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome_id: str
    arm_id: str
    n: Optional[conint(ge=0)] = None
    events: Optional[conint(ge=0)] = None
    mean: Optional[float] = None
    sd: Optional[confloat(ge=0)] = None
    median: Optional[float] = None

    class IQR(BaseModel):
        model_config = ConfigDict(extra='forbid')
        p25: Optional[float] = None
        p75: Optional[float] = None

    iqr: Optional[IQR] = None
    unit: Optional[str] = None
    source: Optional[SourceRef] = None


class ContrastResultModel(str, Enum):
    fixed = "fixed"
    random = "random"
    cox = "cox"
    logistic = "logistic"
    linear = "linear"
    poisson = "poisson"
    nb = "nb"
    other = "other"
    na = "na"


class ContrastResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome_id: str
    comparison_id: str
    population: Optional[AnalysisPopulation] = None
    adjusted: bool = False
    covariates: List[str] = Field(default_factory=list)
    model: Optional[ContrastResultModel] = None
    effect: ContrastEffect
    source: Optional[SourceRef] = None


class HarmsResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    class SeverityGradeScale(str, Enum):
        CTCAE = "CTCAE"
        Clavien_Dindo = "Clavien-Dindo"
        Other = "Other"
        NA = "NA"

    event: str
    arm_id: str
    severity_grade_scale: Optional[SeverityGradeScale] = None
    events: conint(ge=0)
    total: conint(ge=0)
    source: SourceRef


class Results(BaseModel):
    model_config = ConfigDict(extra='forbid')
    per_arm: List[PerArmResult] = Field(default_factory=list)
    contrasts: List[ContrastResult] = Field(default_factory=list)
    harms: List[HarmsResult] = Field(default_factory=list)


class ParsedTableRow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cells: conlist(str, min_length=1)


class ParsedTableType(str, Enum):
    baseline = "baseline"
    outcomes = "outcomes"
    harms = "harms"
    methods = "methods"
    other = "other"


class ParsedTable(BaseModel):
    model_config = ConfigDict(extra='forbid')
    table_id: str
    title: str
    page: Optional[conint(ge=1)] = None
    type: Optional[ParsedTableType] = None
    rows: List[ParsedTableRow] = Field(default_factory=list)
    source: Optional[SourceRef] = None


class FigureSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    figure_id: str
    caption: str
    key_values: Dict[str, float] = Field(default_factory=dict)
    page: Optional[conint(ge=1)] = None
    source: Optional[SourceRef] = None


class RiskOfBiasJudgement(str, Enum):
    low = "low"
    some = "some"
    high = "high"
    unclear = "unclear"


class RiskOfBiasDomain(BaseModel):
    model_config = ConfigDict(extra='forbid')
    domain: str
    judgement: RiskOfBiasJudgement
    notes: Optional[str] = None


class RiskOfBias(BaseModel):
    model_config = ConfigDict(extra='forbid')

    class Tool(str, Enum):
        RoB2 = "RoB2"
        ROBINS_I = "ROBINS-I"
        Other = "Other"

    tool: Optional[Tool] = None
    overall: Optional[RiskOfBiasJudgement] = None
    domains: List[RiskOfBiasDomain] = Field(default_factory=list)


class ExtractionWarningCode(str, Enum):
    TABLE_PARSE_FAIL = "TABLE_PARSE_FAIL"
    AMBIGUOUS_UNIT = "AMBIGUOUS_UNIT"
    CI_PARSE_FAIL = "CI_PARSE_FAIL"
    MISSING_ARM_ID = "MISSING_ARM_ID"
    OTHER = "OTHER"


class ExtractionWarning(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: ExtractionWarningCode
    message: str
    source: Optional[SourceRef] = None


class TruncationReason(str, Enum):
    token_limit = "token_limit"
    page_limit = "page_limit"
    timeout = "timeout"
    other = "other"


class TruncationInfo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: bool = False
    reason: Optional[TruncationReason] = None


class Document(BaseModel):
    filename: str
    content_type: Literal["application/pdf"] = "application/pdf"
    size_bytes: int | None = Field(default=None, ge=0)
    page_count: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class Generator(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    model: str
    temperature: Optional[float] = None
    timestamp: datetime


class ClinicalTrialExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: VersionTag
    document: Optional[Document] = None
    study_id: Optional[StudyIdPattern] = Field(
        default=None, description="Internal opaque ID for this study/article"
    )
    generator: Optional[Generator] = None
    language: Optional[Iso639_1] = Field(
        default=None, description="ISO 639-1 code (e.g., 'en', 'nl')"
    )

    metadata: Metadata
    study_design: StudyDesign
    population: Population

    interventions: List[Intervention] = Field(default_factory=list)
    arms: List[Arm]
    comparisons: List[Comparison] = Field(default_factory=list)
    outcomes: List[Outcome]
    results: Results

    tables_parsed: List[ParsedTable] = Field(default_factory=list)
    figures_summary: List[FigureSummary] = Field(default_factory=list)
    risk_of_bias: Optional[RiskOfBias] = None
    protocol_deviations: Optional[str] = None
    extraction_warnings: List[ExtractionWarning] = Field(default_factory=list)
    truncated: Optional[TruncationInfo] = None


# -------------------------
# Convenience utilities
# -------------------------

def validate_against_model(data: dict) -> ClinicalTrialExtraction:
    \"\"\"Validate an extracted dict against the ClinicalTrialExtraction model.
    Raises pydantic.ValidationError if invalid; returns the parsed model if valid.
    \"\"\"
    return ClinicalTrialExtraction.model_validate(data)


__all__ = [
    # primitives
    'SourceRef','Author','Registration','Metadata','StudyDesign','Population','Intervention','Arm',
    'Comparison','Outcome','EffectCI','ContrastEffect','PerArmResult','ContrastResult','HarmsResult',
    'Results','ParsedTableRow','ParsedTable','FigureSummary','RiskOfBiasDomain','RiskOfBias',
    'ExtractionWarning','TruncationInfo','Document','Generator','ClinicalTrialExtraction',
    'validate_against_model',
]
"""
)

with open("/mnt/data/schemas.py", "w", encoding="utf-8") as f:
    f.write(code)

"/mnt/data/schemas.py"
