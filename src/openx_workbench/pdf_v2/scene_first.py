"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .figures import Figure, referenced_labels
from .models import SectionTree
from .scene_proposer import (
    DEFAULT_SCENE_PROMPT_VERSION,
    STRUCTURE_PROMPTS,
    SceneResponseInvalid,
    SceneResponseTruncated,
    build_document_view,
    build_language_note,
    build_scene_request,
    build_shared_container_appendix,
    build_structure_request,
    parse_scene_response,
    parse_structure_response,
    request_sha256,
)
from .scene_schemas import (
    ResolvedScene,
    SceneFirstExtraction,
    SceneStructure,
    build_buried_clause_index,
    parse_scene_proposal,
    parse_scene_structure,
    resolve_scenes,
)
from .scene_variants import (
    SceneVariants,
    build_variant_request,
    ground_variants,
    parse_variant_response,
    reconcile_variant_readings,
)
from .shared_containers import prefilter_shared_containers
from .stage_d_validation import StageDReport, validate_scene_extraction
from .structure_evidence import check_contradictions, ground_structure, reconcile_readings

SCENE_FIRST_RUN_VERSION = "scene-first-run-v1"

RETRY_REMINDER = (
    "\n\n注意：上一次回复不是合法的 JSON 对象。请严格只输出 JSON，"
    "不要包含解释文字、Markdown 代码块标记或任何其他内容。"
)

# Structure calls (prompts with a structure step): one scene per call, with the clauses its text
# refers to, read three times independently; a spatial fact stands where most readings agree on it
# (structure_evidence.reconcile_readings). A small context keeps quotes verbatim and the readings
# consistent (2026-10-06, L2 + IVISTA: four scenes per call paraphrased quotes, two readings left
# four times the unknowns); the calls run concurrently, so the wait is about the slowest call.
STRUCTURE_BATCH_SCENES = 1
STRUCTURE_BATCH_CHARS = 40_000
STRUCTURE_SAMPLES = 3
STRUCTURE_ATTEMPTS = 3  # the first call and two retries per batch and reading
DEFAULT_CONCURRENCY = 64


_PAGE_NUMBER = re.compile(r"\d{1,4}")
# A clause number in running text: lettered (A.6, C.3.3.2.3.9) or with at least three numeric
# levels (7.4.4), so a decimal such as 3.5 m is none; a figure or table number (图C.5) is none either.
_CLAUSE_REFERENCE = re.compile(r"(?<![A-Za-z0-9_.图表])([A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+){2,})(?!\.?\d)")
REFERENCED_CHARS = 20_000  # at most this much referenced text per scene
MAX_FIGURES = 6  # figures sent with one scene


def structure_timeout(scene_count: int) -> int:
    """Seconds one structure call may take: a small batch that hangs is retried soon."""
    return 120 + 60 * scene_count

CallStatus = Literal[
    "planned",
    "ok",
    "retried_ok",
    "schema_failed",
    "truncated",
    "transport_failed",
    "input_too_large",
    "structure_failed",
]

# transport(request) for the scene list; transport(request, sample=k, timeout=s) for structure
# batches: sample tells the k-th independent reading of the same request apart.
Transport = Callable[..., dict[str, Any]]


class StructureCall(BaseModel):
    """One reading of one structure batch: its attempts, and what came back."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    batch: int = Field(ge=0)
    sample: int = Field(ge=0)
    scene_ids: tuple[str, ...]
    status: Literal["ok", "partial", "failed"]
    attempts: int = Field(ge=0)
    request_sha256: tuple[str, ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    rejected_values: tuple[str, ...] = ()
    failure_detail: str | None = None
    # Figures sent with the batch, by number.
    figures: tuple[str, ...] = ()

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
    structure_prompt_version: str | None = None
    structure_calls: tuple[StructureCall, ...] = ()

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


def _add_usage(total: dict[str, int], envelope: dict[str, Any]) -> None:
    for key, value in (envelope.get("usage") or {}).items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + int(value)


class _Document:
    """The text a structure batch is read from, and each scene's own text for checking quotes."""

    def __init__(self, tree: SectionTree, text_by_node: dict[str, str], extraction: SceneFirstExtraction,
                 figures: Sequence[Figure] = ()):
        self.nodes = {node.node_id: node for node in tree.nodes}
        self.order = {node.node_id: index for index, node in enumerate(tree.nodes)}
        self.parent = {child: node.node_id for node in tree.nodes for child in node.child_ids}
        self.text = text_by_node
        self.context = tuple(extraction.document_context_node_ids)
        self.context_view = self.view(self.context)
        # Page furniture a PDF puts inside running text (a page number, a running header repeated
        # on every page): a quote leaves it out of the sentence it spans.
        lines = Counter(line.strip() for text in text_by_node.values() for line in (text or "").splitlines())
        self.furniture = {line for line, count in lines.items() if line and (count >= 3 or _PAGE_NUMBER.fullmatch(line))}
        # Figures by the section their caption is in, and by number where the number is unique.
        self.figures_in: dict[str, list[Figure]] = {}
        for figure in figures:
            self.figures_in.setdefault(figure.node_id or "", []).append(figure)
        labels = Counter(figure.label for figure in figures)
        self.figure_named = {figure.label: figure for figure in figures if labels[figure.label] == 1}

    def figures(self, scene: ResolvedScene) -> tuple[Figure, ...]:
        """The figures a scene is read with: those its own text names by number ("如图C.10所示"),
        in its order, then those captioned in its own sections, then those of the clauses it refers
        to. Figures of the sections it shares with other scenes (how light is measured, what a
        target looks like) stay out unless its own text names them."""
        own = [node_id for node_id in scene.node_ids
               if node_id not in self.context and node_id not in scene.declared_shared_node_ids]
        found = [self.figure_named[label] for node_id in own for label in referenced_labels(self.clause(node_id))
                 if label in self.figure_named]
        found += [figure for node_id in own for figure in self.figures_in.get(node_id, ())]
        found += [figure for node_id in self.referenced(scene) for figure in self.figures_in.get(node_id, ())]
        return tuple({(figure.page_number, figure.clip): figure for figure in found}.values())[:MAX_FIGURES]

    def clause(self, node_id: str) -> str:
        """What a clause says: its heading line without its own number, then its body. A one-sentence
        clause or a list item ("a) …按照图A.1要求静止放置…") is all heading."""
        node = self.nodes.get(node_id)
        title = node.title if node else ""
        if node and node.section_id and title.startswith(node.section_id):
            title = title[len(node.section_id):]
        return "\n".join(part for part in (title.strip(), self.text.get(node_id) or "") if part)

    def view(self, node_ids) -> str:
        parts = []
        for node_id in sorted(node_ids, key=lambda item: self.order.get(item, len(self.order))):
            node = self.nodes[node_id]
            head = f"[{node_id}] (L{node.level}) {node.title}"
            body = (self.text.get(node_id) or "").strip()
            parts.append(f"{head}\n{body}" if body else head)
        return "\n\n".join(parts)

    def ancestors(self, node_id: str) -> list[str]:
        chain = []
        while node_id in self.parent:
            node_id = self.parent[node_id]
            chain.append(node_id)
        return chain[::-1]

    def own_nodes(self, scene: ResolvedScene) -> tuple[str, ...]:
        """The scene's sections and the clauses its text refers to, without the document-wide ones."""
        return tuple(node_id for node_id in (*scene.node_ids, *self.referenced(scene)) if node_id not in self.context)

    def referenced(self, scene: ResolvedScene) -> tuple[str, ...]:
        """Clauses the scene's text refers to by number, with their sub-clauses ("在夜间条件下，按照
        C.3.3.2.3.9的方法进行试验"): a scene read on its own needs what it repeats."""
        # Only the scene's own text: shared requirements refer to whole sections. A clause that
        # contains the scene is no other clause.
        above = set(self.ancestors(scene.anchor_node_id))
        found: list[str] = []
        for node_id in scene.node_ids:
            if node_id in scene.declared_shared_node_ids:
                continue
            for match in _CLAUSE_REFERENCE.finditer(self.clause(node_id)):
                clause = match.group(1)
                if clause in self.nodes and clause not in scene.node_ids and clause not in above and clause not in found:
                    found.append(clause)
        result: list[str] = []
        size = 0
        for clause in found:
            stack = [clause]
            while stack:
                node_id = stack.pop()
                if node_id in result or node_id in scene.node_ids:
                    continue
                size += len(self.text.get(node_id) or "")
                if size > REFERENCED_CHARS:
                    return tuple(result)
                result.append(node_id)
                stack.extend(reversed(self.nodes[node_id].child_ids))
        return tuple(result)

    def scene_line(self, scene: ResolvedScene) -> str:
        path = " > ".join(self.nodes[item].title for item in self.ancestors(scene.anchor_node_id))
        shared = [item for item in (*scene.declared_shared_node_ids, *self.referenced(scene)) if item not in self.context]
        own = [item for item in self.own_nodes(scene) if item not in shared]
        lines = [f"- scene_id: {scene.scene_id}", f"  场景名：{scene.name}"]
        if path:
            lines.append(f"  所在章节：{path}")
        lines.append("  本场景章节：" + ", ".join(own))
        if shared:
            lines.append("  共用章节：" + ", ".join(shared))
        if figures := self.figures(scene):
            lines.append("  示意图：" + "、".join(figure.label for figure in figures))
        return "\n".join(lines)

    def source(self, scene: ResolvedScene) -> str:
        """Everything a quote for this scene may come from: its own and shared sections, the
        document-wide conditions and the headings above them."""
        ids = [*scene.node_ids, *self.referenced(scene), *self.context]
        titles = {self.nodes[item].title for node_id in ids for item in (node_id, *self.ancestors(node_id))}
        texts = [self.text.get(node_id) or "" for node_id in ids]
        # The sections once more without page furniture: a sentence broken by a page break is found too.
        clean = ["\n".join(line for line in text.splitlines() if line.strip() not in self.furniture) for text in texts]
        return "\n".join([*texts, *titles, *clean])

    def size(self, scenes) -> int:
        return sum(len(self.text.get(node_id) or "") for node_id in {item for scene in scenes for item in self.own_nodes(scene)})

    def batches(self, scenes) -> list[list[ResolvedScene]]:
        """Scenes in document order, a few at a time: siblings that differ in detail are read together."""
        ordered = sorted(scenes, key=lambda scene: self.order.get(scene.anchor_node_id, len(self.order)))
        batches: list[list[ResolvedScene]] = []
        for scene in ordered:
            if batches and len(batches[-1]) < STRUCTURE_BATCH_SCENES and self.size([*batches[-1], scene]) <= STRUCTURE_BATCH_CHARS:
                batches[-1].append(scene)
            else:
                batches.append([scene])
        return batches

    def batch_figures(self, scenes) -> tuple[Figure, ...]:
        return tuple({(figure.page_number, figure.clip): figure for scene in scenes for figure in self.figures(scene)}.values())

    def request(self, scenes, *, model: str, prompt_version: str) -> dict[str, Any]:
        own = {node_id for scene in scenes for node_id in self.own_nodes(scene)}
        return build_structure_request(self.context_view, self.view(own), "\n".join(self.scene_line(scene) for scene in scenes),
                                       model=model, prompt_version=prompt_version, figures=self.batch_figures(scenes))


def _retry_note(request: dict[str, Any], note: str) -> dict[str, Any]:
    messages = [dict(message) for message in request["messages"]]
    text = f"\n\n注意：上一次回复有问题（{note}）。请严格只输出符合要求的 JSON。"
    content = messages[-1]["content"]
    # With figures the message is a list of parts; the note is one more text part after them.
    messages[-1]["content"] = [*content, {"type": "text", "text": text.strip()}] if isinstance(content, list) else content + text
    return {**request, "messages": messages}


def _read_batch(document: _Document, batch_index: int, scenes: list[ResolvedScene], sample: int, *,
                transport: Transport, model: str, prompt_version: str) -> tuple[StructureCall, dict[str, SceneStructure]]:
    """One reading of a batch: retried while scenes are missing, the reply is broken or the call
    failed in a way that may pass next time; what came back is kept."""
    expected = [scene.scene_id for scene in scenes]
    found: dict[str, SceneStructure] = {}
    usage: dict[str, int] = {}
    hashes: list[str] = []
    rejected: set[str] = set()
    failure, note, attempts = None, "", 0
    while len(found) < len(expected) and attempts < STRUCTURE_ATTEMPTS:
        attempts += 1
        remaining = [scene for scene in scenes if scene.scene_id not in found]
        request = document.request(remaining, model=model, prompt_version=prompt_version)
        if note:
            request = _retry_note(request, note)
        hashes.append(request_sha256(request))
        try:
            envelope = transport(request, sample=sample, timeout=structure_timeout(len(remaining)))
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
            if not getattr(error, "retryable", False):
                break
            time.sleep(min(30, 5 * attempts))
            continue
        _add_usage(usage, envelope)
        try:
            structures = parse_structure_response(envelope)
            note = ""
        except SceneResponseTruncated as error:
            failure, note = str(error), ""
            continue
        except SceneResponseInvalid as error:
            failure, note = str(error), str(error)[:200]
            continue
        for scene in remaining:
            try:
                structure = parse_scene_structure(structures.get(scene.scene_id), rejected)
            except ValueError as error:  # a value the schema refuses: read the scene again
                rejected.add(f"{scene.scene_id}: {str(error)[:120]}")
                continue
            if structure is not None:
                found[scene.scene_id] = structure
        if len(found) < len(expected):
            failure = "missing scenes: " + ", ".join(item for item in expected if item not in found)
    status = "ok" if len(found) == len(expected) else "partial" if found else "failed"
    return StructureCall(batch=batch_index, sample=sample, scene_ids=tuple(expected), status=status, attempts=attempts,
                         request_sha256=tuple(hashes), usage=usage, rejected_values=tuple(sorted(rejected)),
                         failure_detail=None if status == "ok" else failure,
                         figures=tuple(figure.label for figure in document.batch_figures(scenes))), found


def read_structures(
    tree: SectionTree,
    text_by_node: dict[str, str],
    extraction: SceneFirstExtraction,
    *,
    transport: Transport,
    model: str,
    prompt_version: str,
    samples: int = STRUCTURE_SAMPLES,
    concurrency: int = DEFAULT_CONCURRENCY,
    figures: Sequence[Figure] = (),
    progress: Callable[[str], None] | None = None,
) -> tuple[SceneFirstExtraction, tuple[StructureCall, ...], list[str]]:
    """Each scene's structure, read batch by batch with evidence that is checked against its text
    and figures (find_figures; none for a model that reads no images).

    Returns the extraction with structures, the calls made and the scenes left without one."""
    document = _Document(tree, text_by_node, extraction, figures)
    batches = document.batches(extraction.scenes)
    jobs = [(index, sample) for index in range(len(batches)) for sample in range(samples)]
    readings: dict[str, list[SceneStructure | None]] = {scene.scene_id: [None] * samples for scene in extraction.scenes}
    calls: list[StructureCall] = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(jobs) or 1))) as pool:
        futures = [pool.submit(_read_batch, document, index, batches[index], sample, transport=transport,
                               model=model, prompt_version=prompt_version) for index, sample in jobs]
        for future in as_completed(futures):
            call, found = future.result()
            with lock:
                calls.append(call)
                for scene_id, structure in found.items():
                    readings[scene_id][call.sample] = structure
                if progress:
                    progress(f"读取场景结构 {len(calls)}/{len(jobs)} / Reading scene structure")
    scenes, missing = [], []
    for scene in extraction.scenes:
        source, sent = document.source(scene), [figure.label for figure in document.figures(scene)]
        structure = reconcile_readings([ground_structure(reading, source, sent) if reading else None
                                        for reading in readings[scene.scene_id]])
        if structure is None:
            missing.append(scene.scene_id)
        else:
            structure = check_contradictions(structure)
        scenes.append(scene.model_copy(update={"structure": structure}))
    calls.sort(key=lambda call: (call.batch, call.sample))
    return extraction.model_copy(update={"scenes": tuple(scenes)}), tuple(calls), missing

def _read_variants_once(document: _Document, scene: ResolvedScene, sample: int, *, transport: Transport,
                        model: str) -> tuple[SceneVariants | None, dict[str, int], str | None]:
    """One reading of one scene's variants, retried like a structure batch."""
    usage: dict[str, int] = {}
    failure, note = None, ""
    for attempt in range(1, STRUCTURE_ATTEMPTS + 1):
        request = build_variant_request(document.context_view, document.view(document.own_nodes(scene)), scene.name,
                                        model=model)
        if note:
            request = _retry_note(request, note)
        try:
            envelope = transport(request, sample=sample, timeout=structure_timeout(1))
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
            if not getattr(error, "retryable", False):
                break
            time.sleep(min(30, 5 * attempt))
            continue
        _add_usage(usage, envelope)
        try:
            return parse_variant_response(envelope), usage, None
        except SceneResponseTruncated as error:
            failure, note = str(error), ""
        except SceneResponseInvalid as error:
            failure, note = str(error), str(error)[:200]
    return None, usage, failure


def read_variants(
    tree: SectionTree,
    text_by_node: dict[str, str],
    extraction: SceneFirstExtraction,
    *,
    transport: Transport,
    model: str,
    samples: int = STRUCTURE_SAMPLES,
    concurrency: int = DEFAULT_CONCURRENCY,
    progress: Callable[[str], None] | None = None,
) -> tuple[dict[str, SceneVariants], dict[str, int], list[str]]:
    """Each scene's test conditions (scene_variants), read from the same text as its structure,
    several times independently; the count most readings agree on stands.

    Returns the variants by scene id, the usage and the scenes no reading came back for."""
    document = _Document(tree, text_by_node, extraction)
    scenes = list(extraction.scenes)
    jobs = [(scene, sample) for scene in scenes for sample in range(samples)]
    readings: dict[str, list[SceneVariants | None]] = {scene.scene_id: [None] * samples for scene in scenes}
    usage: dict[str, int] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(jobs) or 1))) as pool:
        futures = {pool.submit(_read_variants_once, document, scene, sample, transport=transport, model=model): (scene, sample)
                   for scene, sample in jobs}
        for future in as_completed(futures):
            scene, sample = futures[future]
            reading, used, _ = future.result()
            readings[scene.scene_id][sample] = reading
            for key, value in used.items():
                usage[key] = usage.get(key, 0) + value
            done += 1
            if progress:
                progress(f"读取试验工况 {done}/{len(jobs)} / Reading test conditions")
    result, missing = {}, []
    for scene in scenes:
        grounded = [ground_variants(reading, document.source(scene)) if reading else None
                    for reading in readings[scene.scene_id]]
        chosen = reconcile_variant_readings(grounded)
        if chosen is None:
            missing.append(scene.scene_id)
        else:
            result[scene.scene_id] = chosen
    return result, usage, missing


def scene_figures(tree: SectionTree, text_by_node: dict[str, str], extraction: SceneFirstExtraction,
                  figures: Sequence[Figure]) -> dict[str, tuple[Figure, ...]]:
    """The figures each scene is read with, by scene id (as read_structures sends them)."""
    document = _Document(tree, text_by_node, extraction, figures)
    return {scene.scene_id: document.figures(scene) for scene in extraction.scenes}


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
    concurrency: int = DEFAULT_CONCURRENCY,
    structure_samples: int | None = None,
    figures: Sequence[Figure] = (),
    progress: Callable[[str], None] | None = None,
) -> SceneFirstRun:
    """Find the document's scenes in one call; with a prompt that has a structure step, then read
    their structures batch by batch (read_structures)."""

    structure_version = STRUCTURE_PROMPTS.get(prompt_version)
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
            "structure_prompt_version": structure_version,
        }
        base.update(overrides)
        return SceneFirstRun(**base)

    try:
        # Scene names and stories in the document's own language.
        language_note = build_language_note([*title_by_node.values(), *text_by_node.values()])
        request = build_scene_request(
            document_view + language_note, model=model, prompt_version=prompt_version
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
    structure_calls: tuple[StructureCall, ...] = ()
    missing: list[str] = []
    if structure_version and extraction.scenes:
        if progress:
            progress(f"找到 {len(extraction.scenes)} 个场景，正在读取结构 / Found {len(extraction.scenes)} scenes, reading structure")
        extraction, structure_calls, missing = read_structures(
            tree, text_by_node, extraction, transport=transport, model=model, prompt_version=structure_version,
            samples=structure_samples or STRUCTURE_SAMPLES, concurrency=concurrency, figures=figures, progress=progress)
        for call in structure_calls:
            for key, value in call.usage.items():
                usage[key] = usage.get(key, 0) + value
    validation = validate_scene_extraction(
        extraction, tree, text_by_node=text_by_node, flagged_node_ids=flagged_node_ids
    )

    return _record(
        "structure_failed" if missing else status,
        request_sha256=sha,
        usage=usage,
        retry_attempted=retry_attempted,
        retry_model=retry_model if retry_attempted else None,
        extraction=extraction,
        validation=validation,
        confidence=_summarize_confidence(extraction),
        structure_calls=structure_calls,
        failure_detail=("no structure for: " + ", ".join(missing)) if missing else None,
    )
