"""The model's suggestion of which assets to bind to each scene of a PDF.

Candidates come from five routes over the library: the workbench ranking, the structural rules
alone, the asset names, the name-free structure text and the requirement title against the asset
names. A library whose names say little still reaches the right family through structure, one whose
files the rules misread still through its names. The model then judges every candidate
(binding_judge) three times at the thinking effort of the settings, the preferred asset most readings name is the
suggestion, and a person confirms. Readings that disagree mark the suggestion for a second look.
Replies are cached by request, so asking again about unchanged scenes and candidates calls nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock
from typing import Any, Callable

from .binding_judge import (
    JUDGE_VERSION,
    ConditionChoice,
    Judgement,
    JudgementInvalid,
    condition_count,
    judge_request,
    parse_judgement,
)
from .atomic_write import write_json
from .catalog import OpenXAsset
from .llm_service import ModelClient, ModelError, base_url
from .retrieval import OpenXIndex, RetrievalResult
from .reuse import change_cost, figure_cost
from .scene_package import ScenePackage, query_structure_text, scene_package_to_query

# (route, how many of its best candidates join the pool); the pool keeps this order, then rank.
ROUTES = (("full", 10), ("rules", 10), ("name", 5), ("structure", 5), ("title", 5))
# Independent readings of every scene. On three standards (105 scenes, max effort) the readings
# named the same preferred asset for 91 scenes, and that asset was right every time it could be checked.
VOTES = 3
TRIES = 2  # tries of one reading whose reply is cut off or does not fit the candidates
ATTEMPTS = 5  # tries of one call while the service is busy or unreachable
EFFORT_DEPTH = ("minimal", "low", "medium", "high", "xhigh", "max")  # thinking efforts, shallow to deep


@dataclass(frozen=True)
class PoolCandidate:
    result: RetrievalResult
    routes: tuple[str, ...]
    rank: int  # 1-based place in the workbench ranking


def _grams(text: str) -> set[str]:
    """Chinese two-character pieces of a title; bracketed notes, numbers and ids are no title clue."""
    text = re.sub(r"[（(][^）)]*[）)]", "", text or "")
    text = re.sub(r"[\s\-_—–·,，/、:：.0-9a-zA-Z=]+", "|", text)
    return {part[i:i + 2] for part in text.split("|") for i in range(len(part) - 1)}


def title_order(title: str, assets: list[OpenXAsset]) -> list[int]:
    """Library positions by the share of the requirement title's pieces the asset's name contains."""
    wanted = _grams(title)
    if not wanted:
        return []
    scored = sorted(((len(wanted & _grams(asset.title)) / len(wanted), -position)
                     for position, asset in enumerate(assets)), reverse=True)  # ties: library order
    return [-negative for share, negative in scored if share > 0]


def candidate_pool(index: OpenXIndex, package: ScenePackage) -> list[PoolCandidate]:
    """The union of every route's best candidates, each with the routes that found it."""
    query = scene_package_to_query(package)
    ranked = index.search("", query=query, top_k=len(index.assets))  # every asset, with its differences
    position = {id(asset): number for number, asset in enumerate(index.assets)}
    by_position = {position[id(result.asset)]: result for result in ranked}
    order = {"full": [position[id(result.asset)] for result in ranked]}
    order["rules"] = sorted(by_position, key=lambda number: (
        sum(item.blocking for item in by_position[number].differences), change_cost(by_position[number].differences),
        figure_cost(by_position[number].differences), number))
    # The whole library is recalled, then cut: a shorter recall breaks ties between near-identical variants differently.
    count = len(index.assets)
    order["name"] = [number for number, _ in index.recall(index.encoder.encode(query.text), count)]
    order["structure"] = [number for number, _ in
                          index.recall(index.encoder.encode(query_structure_text(query)), count, structure=True)]
    order["title"] = title_order(package.title, index.assets)
    found: dict[int, list[str]] = {}
    for route, depth in ROUTES:
        for number in order[route][:depth]:
            found.setdefault(number, []).append(route)
    rank = {number: place for place, number in enumerate(order["full"], 1)}
    return [PoolCandidate(by_position[number], tuple(routes), rank[number]) for number, routes in found.items()]


def judge_efforts(client: ModelClient) -> tuple[str, str]:
    """The thinking effort of the settings (empty: the service's default), and the one a reading falls
    back to when its reply is cut off there: the model's default when that is shallower, else the next
    shallower level the model declares. Without thinking, a model list or a shallower level, the
    settings' effort for both."""
    config = client.config
    effort = config.reasoning_effort
    if not config.thinking:
        return effort, effort
    try:
        info = next((item for item in client.catalog() if item.id == config.model), None)
    except ModelError:
        info = None
    levels = sorted((level for level in (info.effort_levels if info else ()) if level in EFFORT_DEPTH),
                    key=EFFORT_DEPTH.index)
    current = effort or (info.default_effort if info else "")
    shallower = levels[:levels.index(current)] if current in levels else []
    if not shallower:
        return effort, effort
    return effort, info.default_effort if info.default_effort in shallower else shallower[-1]


class Judge:
    """Model calls of one suggestion run: cached by request and reading, retried while the service is busy,
    stoppable. `efforts` = (effort of every reading, effort of a reading whose reply was cut off)."""

    def __init__(self, client: ModelClient, cache_root: Path, cancel: Event | None = None,
                 efforts: tuple[str, str] | None = None):
        self.client = client
        self.cache_root = cache_root
        self.cancel = cancel or Event()
        self.lock = Lock()
        self.spent: Counter = Counter()
        self.efforts = efforts or (client.config.reasoning_effort, client.config.reasoning_effort)
        self.clients = {effort: ModelClient(replace(client.config, reasoning_effort=effort), opener=client.opener)
                        for effort in self.efforts}

    def _path(self, request: dict, reading: int, effort: str) -> Path:
        config = self.client.config
        identity = {"judge": JUDGE_VERSION, "endpoint": base_url(config.base_url), "model": config.model,
                    "thinking": config.thinking, "effort": effort, "request": request, "sample": reading}
        return self.cache_root / (hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest() + ".json")

    def _call(self, effort: str, request: dict) -> dict:
        for attempt in range(1, ATTEMPTS + 1):
            if self.cancel.is_set():
                raise InterruptedError()
            try:
                envelope = self.clients[effort].complete(request)
                break
            except Exception as error:  # noqa: BLE001 - only a retryable service failure is tried again
                if not getattr(error, "retryable", False) or attempt == ATTEMPTS:
                    raise
                if self.cancel.wait(5 * attempt):
                    raise InterruptedError() from None
        with self.lock:
            self.spent["calls"] += 1
            for key, value in (envelope.get("usage") or {}).items():
                if isinstance(value, int):
                    self.spent[key] += value
        return envelope

    def reading(self, request: dict, count: int, number: int, conditions: int = 0) -> tuple[Judgement | None, str]:
        """Reading `number` of a request about `count` candidates (and `conditions` test conditions): the
        judgement, or None and why there is none.

        A reply cut off at the deep effort is asked again at the fallback effort, one off the candidates
        at the same. Only a reply that fits is cached, under the effort that gave it. A service still
        busy after every attempt fails this reading only; any other service failure (a wrong key, an
        unknown model) would fail every scene and stops the run.
        """
        deep, fallback = self.efforts
        for effort in dict.fromkeys((deep, fallback)):
            path = self._path(request, number, effort)
            try:
                return parse_judgement(json.loads(path.read_text(encoding="utf-8")), count, conditions), ""
            except (OSError, ValueError):  # not cached, unreadable, or no longer fits
                pass
        failure, effort = "", deep
        for _ in range(TRIES):
            try:
                envelope = self._call(effort, request)
                judgement = parse_judgement(envelope, count, conditions)
            except JudgementInvalid as error:
                failure = str(error)
                if (envelope.get("choices") or [{}])[0].get("finish_reason") == "length":
                    effort = fallback
                continue
            except ModelError as error:
                if not error.retryable:
                    raise
                return None, str(error)
            path = self._path(request, number, effort)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, envelope, ensure_ascii=False, prefix="judge-", suffix=".tmp")
            return judgement, ""
        return None, failure


@dataclass(frozen=True)
class ConditionVote:
    """The readings of one test condition taken together."""
    choice: ConditionChoice  # from the earliest reading naming the asset most readings name for it
    agree: int  # readings naming that asset (or none)
    others: tuple[str | None, ...]  # the other assets named, most often first; None: no asset


@dataclass(frozen=True)
class Vote:
    """The readings of one scene taken together."""
    judgement: Judgement | None  # the earliest reading naming the preferred asset most readings name
    readings: int  # readings whose reply fits the candidates
    agree: int  # of them, how many name that preferred asset (or none); with test conditions, the fewest of any
    others: tuple[str | None, ...]  # the other preferred assets named, most often first; None: no asset
    failure: str = ""  # why no reading fits
    conditions: tuple[ConditionVote, ...] = ()

    @property
    def stable(self) -> bool:
        return self.readings >= 2 and self.agree == self.readings


def vote(readings: list[tuple[Judgement | None, str]]) -> Vote:
    """A scene of one run takes the preferred asset most readings name; a scene with test conditions takes,
    for each condition, the asset most readings name for it, and the reading agreeing with most of them."""
    fitting = [judgement for judgement, _ in readings if judgement]
    if not fitting:
        return Vote(None, 0, 0, (), next((why for _, why in reversed(readings) if why), ""))
    if fitting[0].conditions:
        votes = []
        for position in range(len(fitting[0].conditions)):
            named = Counter(item.conditions[position].asset for item in fitting)
            most = max(named.values())
            choice = next(item.conditions[position] for item in fitting if named[item.conditions[position].asset] == most)
            votes.append(ConditionVote(choice, most, tuple(key for key, _ in named.most_common() if key != choice.asset)))
        chosen = max(fitting, key=lambda item: sum(mine.asset == voted.choice.asset
                                                   for mine, voted in zip(item.conditions, votes)))
        return Vote(chosen, len(fitting), min(item.agree for item in votes), (), conditions=tuple(votes))
    named = Counter(item.preferred for item in fitting)
    most = max(named.values())
    chosen = next(item for item in fitting if named[item.preferred] == most)
    return Vote(chosen, len(fitting), most, tuple(key for key, _ in named.most_common() if key != chosen.preferred))


def suggestion_record(pool: list[PoolCandidate], versions: dict, result: Vote,
                      scene_digest: str, revision: int, model: str, conditions: dict | None = None) -> dict[str, Any]:
    """What is kept of one scene's suggestion: the candidates as asset versions with the words of the
    reading chosen, how far the readings agree, and the asset of each test condition (`conditions`, the
    scene's SceneVariants as JSON) with its own agreement."""
    judgement = result.judgement
    judged = {item.id: item for item in judgement.candidates} if judgement else {}
    candidates = []
    for number, item in enumerate(pool, 1):
        version = versions[item.result.asset.asset_id]
        words = judged.get(f"C{number}")
        candidates.append({"id": f"C{number}", "asset_id": version.asset_id, "version_id": version.version_id,
                           "version_number": version.version_number, "title": item.result.asset.title,
                           "rank": item.rank, "routes": list(item.routes), "level": item.result.confirmation_level,
                           "verdict": words.verdict if words else "", "reason": words.reason if words else "",
                           "changes": words.changes if words else ""})
    labels = [item.get("label", "") for item in (conditions or {}).get("variants") or []]
    chosen = [{"id": item.choice.id, "label": labels[number] if number < len(labels) else "",
               "asset": item.choice.asset, "fit": item.choice.fit, "changes": item.choice.changes,
               "agree": item.agree, "other_assets": list(item.others)}
              for number, item in enumerate(result.conditions)]
    binding = [*judgement.binding, *(item["asset"] for item in chosen if item["asset"])] if judgement else []
    return {"created_at": datetime.now(timezone.utc).isoformat(), "model": model, "judge": JUDGE_VERSION,
            "revision": revision, "scene_digest": scene_digest, "candidates": candidates,
            "binding": list(dict.fromkeys(binding)),
            "preferred": judgement.preferred if judgement else None,
            "note": judgement.note if judgement else "", "failure": result.failure,
            "readings": result.readings, "agree": result.agree, "other_preferred": list(result.others),
            **({"conditions": chosen} if chosen else {})}


def suggest_scenes(scenes: list, index: OpenXIndex, versions: dict, judge: Judge, concurrency: int, *,
                   digest: Callable[[ScenePackage], str], save: Callable[[Any, dict], None],
                   ranked: Callable[[Any], None] = lambda scene: None,
                   judged: Callable[[Any], None] = lambda scene: None, language: str = "zh",
                   conditions: Callable[[Any], dict | None] = lambda scene: None) -> int:
    """Rank each scene's candidates and ask the model about them, VOTES readings at once, while the next
    scene is ranked. Replies are taken in between scenes, so a scene's suggestion is saved as soon as its
    readings are in, and a failure that stops the run does so before every scene is ranked.

    `save(scene, record)` receives each finished suggestion; returns how many scenes failed. `language`
    ("zh" or "en") is the language the model writes its reasons in; `conditions(scene)` the scene's test
    conditions, each of which then gets its own asset.
    """
    failed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(scenes) * VOTES))) as executor:
        futures = {}
        readings: dict[int, list] = {}
        stories: dict[str, str] = {}  # a candidate of several scenes is described once

        def take(future) -> None:
            nonlocal failed
            number, reading, scene, pool, asked = futures.pop(future)
            done = readings.setdefault(number, [None] * VOTES)
            done[reading] = future.result()
            if None in done:
                return
            result = vote(done)
            failed += result.judgement is None
            save(scene, suggestion_record(pool, versions, result, digest(scene.package),
                                          scene.revision, judge.client.config.model, asked))
            judged(scene)

        try:
            for number, scene in enumerate(scenes):
                if judge.cancel.is_set():
                    raise InterruptedError()
                pool = candidate_pool(index, scene.package)
                asked = conditions(scene) if condition_count(conditions(scene)) else None
                request = judge_request(scene.package, [(item.result.asset, item.result.differences) for item in pool],
                                        stories=stories, language=language, conditions=asked)
                for reading in range(VOTES):
                    futures[executor.submit(judge.reading, request, len(pool), reading, condition_count(asked))] = (
                        number, reading, scene, pool, asked)
                ranked(scene)
                for future in [item for item in futures if item.done()]:
                    take(future)
            for future in as_completed(list(futures)):
                take(future)
        except BaseException:
            executor.shutdown(cancel_futures=True)  # calls already sent finish; their replies are cached
            raise
    return failed
