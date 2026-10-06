"""Response shapes of the HTTP API, for the OpenAPI document and the web client's generated types.

Routes keep returning plain dicts; `documented(Model)` only describes them in the OpenAPI
document, so serialization stays byte-for-byte what the route returns.
tests/test_api_contract.py checks every JSON response the API tests receive against these
models, and web/scripts/gen-api-types.mjs turns the document into web/src/api-types.ts.

Models forbid unknown fields, except where a payload is open by design (saved traces, parsed
facts, audits, model output).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .pdf_v2.scene_schemas import SceneStructure

Level = Literal["direct", "modify", "major_modify", "review", "new_build"]
Compatibility = Literal["not_tested", "playable", "warning", "unsupported", "failed", "timeout"]


def documented(model: Any) -> dict[str, Any]:
    """Route options that document `model` as the 200 response without validating or reshaping it."""
    return {"response_model": None, "responses": {200: {"model": model}}}


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Open(BaseModel):
    """A payload whose listed fields are reliable, with further fields allowed."""

    model_config = ConfigDict(extra="allow")


# ---------- small results ----------

class Health(Shape):
    status: str


class SelectedProject(Shape):
    project_id: str


class SavedDecision(Shape):
    report_id: str
    saved_to: str


class SavedBatch(Shape):
    report_id: str


class DeletedVersion(Shape):
    deleted: str


class OpenedFolder(Shape):
    opened: str


class ModelInfo(Shape):
    id: str
    effort_levels: list[str]
    default_effort: str
    max_output_tokens: int | None


class ModelList(Shape):
    models: list[str]
    details: list[ModelInfo]


class ModelProbe(Shape):
    model: str


# ---------- projects, documents and scenes ----------

class Project(Shape):
    project_id: str
    name: str
    created_at: str


class ProjectList(Shape):
    projects: list[Project]
    last_project_id: str | None


class PdfDocument(Shape):
    document_id: str
    project_id: str
    filename: str
    source_standard: str
    sha256: str
    imported_at: str
    page_count: int
    scene_count: int
    extraction_engine: str
    size_bytes: int | None


class Evidence(Shape):
    source_pdf: str
    section_id: str
    page_start: int
    page_end: int
    source_text: str


class SourceRegion(Shape):
    page: int
    clip: tuple[float, float, float, float]


class NoStructure(Shape):
    """A scene extracted without a typed structure (legacy rules)."""


class Scene(Shape):
    scene_id: str
    revision: int
    package_id: str
    title: str
    preferred_text: str
    section_id: str
    pages: tuple[int, int] | None
    evidence: list[Evidence]
    review_status: str
    classification: dict[str, str | float | None]
    entities: list[str]
    actions: list[str]
    road_types: list[str]
    source_region: SourceRegion | None
    document_id: str
    structure: SceneStructure | NoStructure
    triggers: list[str]
    weather: list[str]
    time_of_day: list[str]
    parameters: dict[str, float]
    issues: list[str]
    ocr: bool


class QueuedScene(Scene):
    """A scene in the review queue: confirmed into the library, or already assessed."""

    published: bool
    queue_status: Literal["pending", "confirmed", "assessed"]


class Revision(Shape):
    revision: int
    title: str
    parameters: dict[str, float]
    structure: SceneStructure | NoStructure


class SceneSchema(Shape):
    """Controlled vocabulary of the typed requirement editor."""

    road_class: list[str]
    tested_function: list[str]
    test_intent: list[str]
    ego_actions: list[str]
    semantic_triggers: list[str]
    weather: list[str]
    time_of_day: list[str]
    participant_kind: list[str]
    bearing: list[str]
    facing: list[str]
    participant_actions: list[str]
    age: list[str]


class Publication(Shape):
    library_id: str
    revision: int
    reviewed_at: str


class ExtractionRecord(Shape):
    engine: str
    current_engine: str
    outdated: bool
    has_record: bool
    model: str | None
    issues: list[str]
    flags: list[str]
    ocr: bool


class EvidenceSnippet(Shape):
    evidence_id: str
    location: str
    text: str


class Observation(Shape):
    text: str
    citations: list[str]


class GroundedExplanation(Shape):
    verdict: str
    observations: list[Observation]
    evidence: list[EvidenceSnippet]
    insufficient_evidence: list[str]
    method: str


class Explanation(Shape):
    """The evidence a model request would send; with an explanation once one was generated."""

    evidence: list[EvidenceSnippet]
    insufficient: list[str]
    explanation_id: str | None = None
    explanation: GroundedExplanation | None = None


# ---------- matching ----------

class Difference(Shape):
    category: str
    requested: str
    candidate: str
    action: str
    blocking: bool
    cost: float
    verified: bool
    tier: str = "core"  # core, adjustable or note (reuse_policy.difference_tier)
    category_label: str
    requested_label: str
    candidate_label: str
    text: str


class ReviewItem(Shape):
    id: str
    kind: Literal["difference", "standards"]
    difference: int | None = Field(description="Index into the candidate's differences.")


class CheckIssue(Open):
    message: str
    line: int | None = None
    path: str | None = None


class StandardCheck(Open):
    status: str
    standard: str | None = None
    version: str | None = None
    issues: list[CheckIssue] = []
    detail: str | None = None


class StandardGate(Shape):
    passed: bool
    pending: dict[str, str]
    checks: dict[str, StandardCheck]


class Scores(Shape):
    combined: float
    semantic: float
    scenario: float
    road: float


class Reason(Shape):
    code: str
    label: str


class CandidateEntity(Shape):
    name: str
    kind: str
    category: str | None
    model: str | None
    width: float | None


class CandidateScenario(Shape):
    name: str | None
    entities: list[CandidateEntity]
    actions: list[str]
    trigger_count: int
    parameters: list[str]
    environment: dict[str, str | float]


class CandidateRoad(Shape):
    total_length_m: float
    lane_count: int
    lane_types: dict[str, int]
    geometry_types: dict[str, int]
    junction_count: int
    road_count: int
    revision: str | None
    file_missing: bool
    inferred_features: list[str]
    lanes_same_direction: int
    lanes_total: int
    lane_markings: list[str]


class Candidate(Shape):
    asset_id: str
    version_id: str | None
    version_number: int | None
    source_name: str
    compatibility: str
    title: str
    display_title: str
    xosc: str
    xodr: str
    description: str
    classification: dict[str, str | list[str]]
    scores: Scores
    level: Level
    structural_level: Level
    review_kind: str
    review_items: list[ReviewItem] = Field(
        description="What a reviewer confirms, each with a reason, before a review decision can be saved.")
    change_cost: float | None
    reasons: list[Reason]
    differences: list[Difference]
    standard_checks: StandardGate
    scenario: CandidateScenario
    road: CandidateRoad
    has_frame: bool


class SearchResponse(Shape):
    encoder: str
    total: int
    library_size: int
    scene: Scene | None
    results: list[Candidate]


class Library(Shape):
    asset_count: int
    last_import: str | None
    encoder: str
    facets: dict[str, list[str]]


# ---------- traces and reports ----------

class TraceSource(Open):
    title: str | None = None
    scene_id: str | None = None
    revision: int | None = None
    document_id: str | None = None
    evidence: list[Evidence] = []


class TraceCandidate(Open):
    title: str | None = None
    xosc: str | None = None
    xodr: str | None = None
    asset_id: str | None = None
    version_id: str | None = None
    version_number: int | None = None


class DifferenceRecord(Shape):
    category: str
    requested: str
    candidate: str
    action: str
    blocking: bool
    cost: float
    verified: bool
    tier: str = "core"  # absent in reports saved before tiers: read conservatively as core


class SignedItem(Shape):
    id: str
    kind: Literal["difference", "standards"]
    reason: str
    difference: DifferenceRecord | None = None


class ReviewSignoff(Shape):
    signed_at: str
    items: list[SignedItem]


class TraceReuse(Open):
    level: Level
    structural_level: Level | None = None
    review_kind: str | None = None
    estimated_change_cost: float | None = None
    review_signoff: ReviewSignoff | None = None


class BatchAssessment(Open):
    level: Level | Literal["no_candidates"]
    review_kind: str | None = None
    estimated_change_cost: float | None = None


class BatchCandidate(Open):
    candidate: TraceCandidate


class BatchEntry(Open):
    source: TraceSource
    assessment: BatchAssessment
    candidates: list[BatchCandidate]


class Trace(Open):
    """A reuse assessment of one scene, or (kind "batch_match") of every scene of a PDF."""

    kind: Literal["batch_match"] | None = None
    source: TraceSource | None = None
    candidate: TraceCandidate | None = None
    reuse: TraceReuse | None = None
    scene_count: int | None = None
    encoder: str | None = None
    counts: dict[str, int] | None = None
    entries: list[BatchEntry] | None = None


class BatchResult(Shape):
    signature: str
    trace: Trace


class ReportScene(Shape):
    title: str | None
    scene_id: str | None
    revision: int | None
    document_id: str | None


class Report(Shape):
    report_id: str
    saved_at: str
    asset_id: str | None
    version_id: str | None
    kind: Literal["decision", "batch"]
    level: Level | None = Field(description="None for a whole-PDF summary.")
    review_kind: str
    signed_off: bool
    counts: dict[str, int] | None
    scene_count: int | None
    scene: ReportScene


class ReopenableScene(Shape):
    document_id: str
    scene_id: str


class ReportDetail(Open):
    report_id: str
    saved_at: str
    version_id: str | None = None
    trace: Trace
    reopenable: list[ReopenableScene]


class RecentVersion(Shape):
    asset_id: str
    version_id: str
    title: str
    source_name: str
    version_number: int
    compatibility: str
    created_at: str


class Overview(Shape):
    assets: int
    versions: int
    playable: int
    unavailable: int
    untested: int
    recent: list[RecentVersion]


# ---------- assets ----------

class AssetRow(Shape):
    asset_id: str
    version_id: str
    version_number: int
    name: str
    xosc_name: str
    xodr_name: str
    source_name: str
    created_at: str
    compatibility: str
    latest: bool
    function: str
    road: str
    targets: list[str]
    classification: str
    needs_review: bool


class ClassificationLabels(Shape):
    function_type: str
    label_road_type: str
    label_target_type: list[str]
    label_actions: list[str]
    scenario_intent: str


class ModelLabels(ClassificationLabels):
    confidence: float
    reason: str


class ClassificationRecord(Open):
    status: str
    needs_review: bool
    final: ClassificationLabels
    rule: ClassificationLabels
    llm: ModelLabels | None
    model: str
    error: str | None = None
    saved_at: str | None = None


class ClassificationSchema(Shape):
    function_type: list[str]
    label_road_type: list[str]
    label_target_type: list[str]


class StoredFile(Open):
    role: str
    original_name: str
    sha256: str


class StoredVersion(Shape):
    asset_id: str
    version_id: str
    version_number: int
    title: str
    source_name: str
    xosc_name: str
    xodr_name: str
    created_at: str
    content_sha256: str
    source_sha256: str
    compatibility: str
    compatibility_detail: str
    files: list[StoredFile]


class VersionHistory(Shape):
    version_id: str
    version_number: int
    created_at: str
    compatibility: str
    source_name: str


class AssetSummary(Shape):
    title: str
    entities: int
    road_length_m: float
    lane_count: int
    junction_count: int
    description: str
    road_file_missing: bool
    road_name: str | None
    inferred_road_features: list[str]


class AssetDetail(Shape):
    version: StoredVersion
    classification: ClassificationRecord | None
    references: list[str]
    has_frame: bool
    history: list[VersionHistory]
    standard_export: bool
    summary: AssetSummary | None = None
    validation: dict[str, StandardCheck] | None = None
    error: str | None = None


class StandardExportAudit(Open):
    validation: dict[str, StandardCheck]
    external_dependencies: list[Any]
    runtime_extension_points: list[Any]
    parameter_issues: list[Any]
    unresolved: list[Any]


class StandardExportResult(Shape):
    ready: bool
    audit: StandardExportAudit


class RequirementRecord(Shape):
    library_id: str
    revision: int
    reviewed_at: str
    project_id: str
    document_id: str
    scene_id: str
    title: str
    preferred_text: str
    classification: dict[str, Any]
    structure: dict[str, Any]


# ---------- jobs ----------

class ImportReport(Open):
    source_name: str
    case_count: int
    imported_count: int
    missing_road_references: list[str]
    road_missing_count: int = 0


class JobResult(Open):
    project_id: str | None = None
    document_ids: list[str] | None = None
    versions: list[dict[str, str]] | None = None


class Job(Shape):
    id: str
    kind: Literal["pdf_import", "asset_import", "schema_update"]
    status: Literal["running", "completed", "failed", "stopped", "interrupted"]
    stage: str
    current: str
    done: int
    total: int
    started: float
    updated: float
    finished: float | None = None
    error: str
    messages: list[str]
    result: JobResult
    cancelling: bool
    saved: int | None = None
    failed: int | None = None
    reports: list[ImportReport] | None = None


class VersionKey(Shape):
    asset_id: str
    version_id: str


class PendingClassification(Shape):
    count: int
    versions: list[VersionKey]


# ---------- settings and preview ----------

class ModelSettings(Shape):
    base_url: str
    model: str
    thinking: bool
    reasoning_effort: str
    max_tokens: int
    timeout: int
    has_key: bool
    readable: bool


class PreviewSettings(Shape):
    configured: str
    executable: str | None
    folder: str | None
    cancelled: bool | None = None


class Preferences(Shape):
    language: Literal["zh", "en"]
    appearance: Literal["light", "dark", "system"]
    encoder: Literal["bge", "hashing"]


class Settings(Shape):
    model: ModelSettings
    preview: PreviewSettings
    data_dir: str
    preferences: Preferences


class SchemaRegistry(Shape):
    revision: str
    commit_date: str | None = None
    installed_at: str
    versions: list[str]
    skipped: dict[str, str]


class VerdictCount(Shape):
    status: str
    issues: int


class SchemaVerdictChange(Shape):
    asset_id: str
    version_id: str
    title: str
    role: Literal["scenario", "road"]
    standard: str | None = None
    version: str | None = None
    before: VerdictCount
    after: VerdictCount


class SchemaPreview(Shape):
    """Library verdicts a staged registry would change; nothing is switched until the user applies it."""
    revision: str
    date: str
    message: str
    compared: int
    changes: list[SchemaVerdictChange]
    created_at: str


class StagedSchemaRegistry(SchemaRegistry):
    preview: SchemaPreview | None = None


class SchemaStatus(Shape):
    active: SchemaRegistry | None
    previous: SchemaRegistry | None
    staged: StagedSchemaRegistry | None
    pinned: str
    job: Job | None = None


class SchemaCheck(Shape):
    revision: str
    date: str
    message: str
    installed: bool
    up_to_date: bool
    changed: list[str]
    added: list[str]
    removed: list[str]
    new_versions: list[str]
    dropped_versions: list[str]
    unmapped: dict[str, str]


class PreviewStatus(Shape):
    state: Literal["idle", "starting", "running", "finished", "failed", "stopped"]
    asset_id: str | None = None
    version_id: str | None = None
    frames: int | None = None
    error: str | None = None
    snapshot_error: str | None = None
    stream_url: str | None = None
    log: str | None = None
