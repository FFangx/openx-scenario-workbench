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
    image_input: bool


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
    folder: str = Field(description="The project's folder on this computer.")
    pdf_count: int


class MissingProject(Shape):
    """A project whose folder was moved or deleted outside the workbench."""
    project_id: str
    name: str
    folder: str


class ProjectList(Shape):
    projects: list[Project]
    missing: list[MissingProject]
    last_project_id: str | None
    location: str = Field(description="The folder new projects are created in.")


class ProjectLocation(Shape):
    location: str
    cancelled: bool


class OpenedProject(Shape):
    project: Project | None = Field(description="None when the folder dialog was cancelled.")


class DeletedProject(Shape):
    deleted: str


class SavedExport(Shape):
    filename: str
    path: str


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


class SceneFigure(Shape):
    """A figure the scene's structure was read with: its number, caption and box on the page."""
    label: str
    caption: str
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
    figures: list[SceneFigure] = []


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
    ego_turn: list[str]
    ego_lane: list[str]
    traffic_controls: list[str]


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
    tier: str = "core"  # core, adjustable, note or figure (reuse_policy.difference_tier)
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
    height: float | None


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
    map_name: str = Field(description="The road's name: the authoring tool's map name, the OpenDRIVE header's, or the file's.")
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


class CatalogProgress(Shape):
    state: Literal["idle", "loading", "ready", "failed"]
    stage: Literal["", "reading", "checking", "parsing"] = Field(
        description="While loading: reading kept entries, checking file standards, or parsing changed assets.")
    done: int
    total: int
    error: str


class EncoderStatus(Shape):
    name: str
    state: Literal["idle", "loading", "ready", "failed"]


class LibraryStatus(Shape):
    catalog: CatalogProgress
    encoder: EncoderStatus


# ---------- traces and reports ----------

class SummaryDocument(Shape):
    document_id: str
    filename: str
    pdf_sha256: str


class TraceSource(Open):
    title: str | None = None
    scene_id: str | None = None
    revision: int | None = None
    document_id: str | None = Field(None, description="The scene's PDF; in a whole-PDF summary only when it covers one PDF.")
    filename: str | None = Field(None, description="A summary row's PDF.")
    documents: list[SummaryDocument] = Field([], description="The PDFs a whole-PDF summary covers.")
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
    reuse: BatchAssessment


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
    failed: int = Field(description="Latest versions that were tried and could not play.")
    road_missing: int = Field(description="Latest versions whose road file was not imported: no preview.")
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
    # rule: read by the rules; manual_confirmed: a reviewer's. Records of the retired model review
    # (classified, failed, rule_only) keep their model labels until the rules label them again.
    status: str
    needs_review: bool
    final: ClassificationLabels
    rule: ClassificationLabels
    llm: ModelLabels | None = None
    model: str = ""
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
    kind: Literal["pdf_import", "asset_import", "schema_update", "binding_suggest", "preview_batch"]
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
    ranked: int | None = Field(None, description="Suggestions: scenes whose candidates are found; `done` counts the judged.")
    reports: list[ImportReport] | None = None


class VersionKey(Shape):
    asset_id: str
    version_id: str


class PendingClassification(Shape):
    count: int
    versions: list[VersionKey]


# ---------- requirement <-> asset bindings ----------

Verdict = Literal["同一测试", "同一测试但要改", "不是", "拿不准", ""]


class SuggestedCandidate(Shape):
    id: str = Field(description="C1, C2, … as the model saw them.")
    asset_id: str
    version_id: str
    version_number: int
    title: str
    rank: int = Field(description="Place in the workbench ranking.")
    routes: list[Literal["full", "rules", "name", "structure", "title"]]
    level: Level
    verdict: Verdict = Field(description="Empty when the model gave no usable reply.")
    reason: str
    changes: str
    latest: bool


class SuggestedCondition(Shape):
    """The asset the model suggests for one test condition of a scene."""
    id: str = Field(description="V1, V2, … in the order the scene lists its test conditions.")
    label: str
    asset: str | None = Field(description="Candidate id; null when no candidate builds this condition.")
    fit: Literal["直接复用", "修改复用", ""] = Field(description="As is, or after the changes named; empty without an asset.")
    changes: str
    agree: int = Field(description="Readings that name this asset (or none) for the condition.")
    other_assets: list[str | None] = Field(description="What the other readings named, most often first; null: none.")


class BindingSuggestion(Shape):
    created_at: str
    model: str
    binding: list[str] = Field(description="Candidate ids the model would bind; empty when none fits.")
    preferred: str | None
    note: str
    failure: str = Field(description="Why the model gave no usable reply; empty when it did.")
    candidates: list[SuggestedCandidate]
    outdated: list[Literal["scene", "asset"]] = Field(
        description="scene: the scene's facts changed since; asset: a candidate has a newer version.")
    readings: int | None = Field(description="Readings of the scene whose reply fits; null when kept before "
                                             "readings were counted.")
    agree: int | None = Field(description="Of those readings, how many name the suggested preferred asset (or none).")
    other_preferred: list[str | None] = Field(
        description="Candidate ids the other readings preferred, most often first; null: no asset fits.")
    stable: bool | None = Field(description="Every reading (two at least) names the same preferred asset; "
                                            "null for a failed suggestion or one kept before readings were counted.")
    recorded: bool = Field(description="Replayed from the recording shipped with the demo, not asked of a model here.")
    conditions: list[SuggestedCondition] = Field(
        description="For a scene with test conditions, the asset of each; then no asset is preferred and the "
                    "suggestion is stable only when the readings agree on every condition.")


class BoundAssetRecord(Shape):
    asset_id: str
    version_id: str
    version_number: int
    title: str
    preferred: bool
    verdict: Verdict
    reason: str
    changes: str
    latest: bool


class BindingOrigin(Shape):
    project_id: str | None
    document_id: str | None
    scene_id: str | None
    revision: int | None


class ConfirmedCondition(Shape):
    """The asset a person confirmed for one test condition of a scene."""
    id: str
    label: str
    status: Literal["same", "modify", "none"]
    asset_id: str | None
    version_id: str | None
    version_number: int | None
    title: str | None
    changes: str
    latest: bool | None = Field(description="The version is still the asset's latest; null without an asset.")


class ConfirmedBinding(Shape):
    status: Literal["same", "modify", "none"]
    changes: str
    assets: list[BoundAssetRecord]
    source: Literal["suggestion", "manual"]
    confirmed_at: str
    stale: list[Literal["scene", "asset"]] = Field(
        description="scene: the scene's facts changed since; asset: a bound asset has a newer version.")
    confirmed_in: BindingOrigin
    conditions: list[ConfirmedCondition] = Field(
        description="For a scene with test conditions, the asset of each; the status follows from them.")


class ConditionDimension(Shape):
    """One way a scene's test conditions differ."""
    name: str
    kind: str
    how: Literal["都要做", "按被测车选一", "任选一"] = Field(
        description="Every value is run, or the tested vehicle (or the tester) picks one.")
    quote: str | None = Field(description="The sentence of the source it rests on.")
    review: str | None = Field(description="Why a person should check it (its sentence was not found); null when found.")


class TestCondition(Shape):
    id: str = Field(description="V1, V2, … in the order the source lists them.")
    label: str
    values: dict[str, str] = Field(description="Its value per dimension name.")


class SceneConditions(Shape):
    """The test conditions (工况) the source sets for one scene: several runs whose scenario files differ."""
    dimensions: list[ConditionDimension]
    items: list[TestCondition]
    review_flags: list[str]


class SceneBinding(Shape):
    document_id: str
    filename: str
    scene_id: str
    revision: int
    title: str
    section_id: str
    key: str = Field(description="The requirement: PDF content, clause number and extracted title.")
    pages: list[int] | None
    suggestion: BindingSuggestion | None
    binding: ConfirmedBinding | None
    test_conditions: SceneConditions | None = Field(description="Null for a scene of one run, or one not read yet.")


class GroupBindings(Shape):
    documents: list[SummaryDocument] = Field(description="The PDFs shown together, in the order selected.")
    scenes: list[SceneBinding]
    job: Job | None


class AssetBinding(Shape):
    """A requirement clause bound to some version of an asset."""
    key: str
    filename: str | None
    standard: str | None
    section_id: str | None
    title: str | None
    project_id: str | None
    document_id: str | None
    scene_id: str | None
    status: Literal["same", "modify", "none"]
    changes: str
    preferred: bool
    group_size: int = Field(description="How many assets the clause is bound to.")
    version_id: str
    version_number: int
    latest: bool = Field(description="The bound version is still the asset's latest.")
    stale: list[Literal["scene", "asset"]]
    source: Literal["suggestion", "manual"]
    confirmed_at: str


class CoverageScene(Shape):
    scene_id: str
    section_id: str
    title: str
    status: Literal["same", "modify", "none", "unconfirmed"]
    stale: bool
    assets: list[str] = Field(description="Titles of the bound assets, the preferred one first.")


class DocumentCoverage(Shape):
    document_id: str
    filename: str
    standard: str
    same: int
    modify: int
    none: int
    unconfirmed: int
    stale: int
    scenes: list[CoverageScene]


class UnusedAsset(Shape):
    asset_id: str
    version_id: str
    title: str
    source_name: str


class BindingCoverage(Shape):
    documents: list[DocumentCoverage]
    asset_count: int
    bound_asset_count: int = Field(description="Assets some clause of any project is bound to.")
    unused_assets: list[UnusedAsset]


# ---------- settings and preview ----------

class ModelSettings(Shape):
    base_url: str
    model: str
    thinking: bool
    reasoning_effort: str
    max_tokens: int
    timeout: int
    concurrency: int
    image_input: bool
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
    show_file_names: bool = Field(description="Candidates are named by their files instead of the scenario and map names.")
    auto_preview: bool = Field(description="An asset import is followed by making previews of the library.")


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
