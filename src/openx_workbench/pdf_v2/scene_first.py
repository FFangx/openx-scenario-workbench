"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import SectionTree
from .scene_proposer import (
    DEFAULT_SCENE_PROMPT_VERSION,
    SceneResponseInvalid,
    SceneResponseTruncated,
    build_document_view,
    build_scene_request,
    build_shared_container_appendix,
    parse_scene_response,
    request_sha256,
)
from .scene_schemas import (
    SceneFirstExtraction,
    build_buried_clause_index,
    parse_scene_proposal,
    resolve_scenes,
)
from .shared_containers import prefilter_shared_containers
from .stage_d_validation import StageDReport, validate_scene_extraction

SCENE_FIRST_RUN_VERSION = "scene-first-run-v1"

RETRY_REMINDER = (
    "\n\n注意：上一次回复不是合法的 JSON 对象。请严格只输出 JSON，"
    "不要包含解释文字、Markdown 代码块标记或任何其他内容。"
)

CallStatus = Literal[
    "planned",
    "ok",
    "retried_ok",
    "schema_failed",
    "truncated",
    "transport_failed",
    "input_too_large",
]

Transport = Callable[[dict[str, Any]], dict[str, Any]]

class ConfidenceSummary(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    count: int = Field(ge=0)
    minimum: float = Field(ge=0.0, le=1.0)
    maximum: float = Field(ge=0.0, le=1.0)
    mean: float = Field(ge=0.0, le=1.0)

    at_or_above_098: int = Field(ge=0)
    between_095_and_098: int = Field(ge=0)
    below_095: int = Field(ge=0)

class SceneFirstRun(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_version: Literal["scene-first-run-v1"] = SCENE_FIRST_RUN_VERSION
    standard: str = Field(min_length=1)
    heading_decoder: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    status: CallStatus
    request_sha256: str | None = None
    document_view_chars: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    prefilter_candidate_count: int = Field(ge=0)
    retry_attempted: bool = False
    retry_model: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    failure_detail: str | None = None
    extraction: SceneFirstExtraction | None = None
    validation: StageDReport | None = None
    confidence: ConfidenceSummary | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in {"ok", "retried_ok"}

def _estimate_tokens(text: str) -> int:

    cjk = sum(1 for character in text if "\u4e00" <= character <= "\u9fff")
    return int(cjk * 0.6 + (len(text) - cjk) * 0.3)

def _summarize_confidence(extraction: SceneFirstExtraction) -> ConfidenceSummary | None:
    values = [scene.confidence for scene in extraction.scenes]
    if not values:
        return None
    return ConfidenceSummary(
        count=len(values),
        minimum=min(values),
        maximum=max(values),
        mean=round(sum(values) / len(values), 4),
        at_or_above_098=sum(1 for value in values if value >= 0.98),
        between_095_and_098=sum(1 for value in values if 0.95 <= value < 0.98),
        below_095=sum(1 for value in values if value < 0.95),
    )

def _build_retry_request(request: dict[str, Any], retry_model: str | None) -> dict[str, Any]:

    messages = [dict(message) for message in request["messages"]]
    messages[-1]["content"] = messages[-1]["content"] + RETRY_REMINDER
    retry = dict(request)
    retry["messages"] = messages
    if retry_model:
        retry["model"] = retry_model
    return retry

def run_scene_first_extraction(
    tree: SectionTree,
    text_by_node: dict[str, str],
    *,
    standard: str,
    heading_decoder: str,
    model: str,
    transport: Transport | None = None,
    prompt_version: str = DEFAULT_SCENE_PROMPT_VERSION,
    retry_enabled: bool = True,
    retry_model: str | None = None,
    flagged_node_ids: frozenset[str] = frozenset(),
) -> SceneFirstRun:

    title_by_node = {node.node_id: node.title for node in tree.nodes}
    candidates = prefilter_shared_containers(tree)
    document_view = build_document_view(tree, text_by_node) + build_shared_container_appendix(
        candidates, title_by_node
    )

    def _record(status: CallStatus, **overrides: Any) -> SceneFirstRun:
        base: dict[str, Any] = {
            "standard": standard,
            "heading_decoder": heading_decoder,
            "prompt_version": prompt_version,
            "model": model,
            "status": status,
            "document_view_chars": len(document_view),
            "estimated_input_tokens": _estimate_tokens(document_view),
            "prefilter_candidate_count": len(candidates),
        }
        base.update(overrides)
        return SceneFirstRun(**base)

    try:
        request = build_scene_request(
            document_view, model=model, prompt_version=prompt_version
        )
    except Exception as error:
        return _record("input_too_large", failure_detail=f"{type(error).__name__}: {error}")

    sha = request_sha256(request)
    if transport is None:
        return _record("planned", request_sha256=sha)

    try:
        envelope = transport(request)
    except Exception as error:

        return _record(
            "transport_failed",
            request_sha256=sha,
            failure_detail=f"{type(error).__name__}: {error}",
        )

    usage = {
        key: int(value)
        for key, value in (envelope.get("usage") or {}).items()
        if isinstance(value, (int, float))
    }
    retry_attempted = False

    try:
        content = parse_scene_response(envelope)
        status: CallStatus = "ok"
    except SceneResponseTruncated as error:

        return _record(
            "truncated", request_sha256=sha, usage=usage,
            failure_detail=str(error),
        )
    except SceneResponseInvalid as first_error:
        if not retry_enabled:
            return _record(
                "schema_failed", request_sha256=sha, usage=usage,
                failure_detail=str(first_error),
            )

        retry_attempted = True
        retry_request = _build_retry_request(request, retry_model)
        try:
            retry_envelope = transport(retry_request)
        except Exception as error:
            return _record(
                "transport_failed", request_sha256=sha, usage=usage,
                retry_attempted=True, retry_model=retry_model,
                failure_detail=f"retry transport: {type(error).__name__}: {error}",
            )
        for key, value in (retry_envelope.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + int(value)
        try:
            content = parse_scene_response(retry_envelope)
        except (SceneResponseInvalid, SceneResponseTruncated) as retry_error:
            return _record(
                "schema_failed", request_sha256=sha, usage=usage,
                retry_attempted=True, retry_model=retry_model,
                failure_detail=f"first: {first_error}; retry: {retry_error}",
            )
        status = "retried_ok"

    known_node_ids = frozenset(node.node_id for node in tree.nodes)

    buried_clause_owners = build_buried_clause_index(text_by_node, known_node_ids)
    proposal = parse_scene_proposal(
        content,
        known_node_ids=known_node_ids,
        buried_clause_owners=buried_clause_owners,
    )
    extraction = resolve_scenes(
        proposal, tree, standard=standard, heading_decoder=heading_decoder
    )
    validation = validate_scene_extraction(
        extraction, tree, text_by_node=text_by_node, flagged_node_ids=flagged_node_ids
    )

    return _record(
        status,
        request_sha256=sha,
        usage=usage,
        retry_attempted=retry_attempted,
        retry_model=retry_model if retry_attempted else None,
        extraction=extraction,
        validation=validation,
        confidence=_summarize_confidence(extraction),
    )
