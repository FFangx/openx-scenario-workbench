"""Model suggestions of requirement ↔ asset bindings, and the table a person confirms (fake model, no network)."""
import json
import re
import time
from collections import Counter
from pathlib import Path
from threading import Lock

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from openx_workbench import api, demo_workspace
from openx_workbench.asset_store import AssetStore
from openx_workbench.binding_suggest import candidate_pool, judge_efforts, title_order
from openx_workbench.catalog import AssetFile
from openx_workbench.llm_service import ModelClient, ModelConfig, ModelError, ModelInfo
from openx_workbench.pdf_store import PdfStore
from openx_workbench.retrieval import OpenXIndex
from openx_workbench.scene_package import scene_package_to_query
from test_structured_reuse import authored_asset, requirement

FIXTURES = Path(__file__).parent / "fixtures"


def reply(data, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(data, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def judged(body, preferred="C1"):
    """Binds the first two candidates (the ranking's best) as the same test, judges the others not."""
    ids = re.findall(r"### (C\d+)", body["messages"][1]["content"])
    return reply({"candidates": [{"id": key, "verdict": "同一测试" if key in ("C1", "C2") else "不是",
                                  "reason": "依据", "changes": ""} for key in ids],
                  "binding": ["C1", "C2"], "preferred": preferred, "note": ""})


class FakeModel:
    def __init__(self):
        self.calls = 0
        self.efforts = Counter()  # thinking effort of every call
        self.seen = Counter()  # calls per request
        self.lock = Lock()
        self.answer = None  # set to replace the reply: answer(body, client, nth call of this request)

    def __call__(self, client, body, **_):
        with self.lock:
            self.calls += 1
            self.efforts[client.config.reasoning_effort] += 1
            key = json.dumps(body, sort_keys=True, ensure_ascii=False)
            self.seen[key] += 1
            nth = self.seen[key]
        return judged(body) if self.answer is None else self.answer(body, client, nth)


class Base:
    """The binding routes of the selected PDFs of a project."""

    def __init__(self, client, project, documents):
        self.client, self.documents, self.url = client, documents, f"/api/projects/{project}"

    def view(self):
        return self.client.get(self.url + "/bindings", params={"document_ids": self.documents}).json()

    def suggest(self, **extra):
        return self.client.post(self.url + "/bindings/suggest", json={"document_ids": self.documents, **extra})

    def accept(self, **extra):
        return self.client.post(self.url + "/bindings/accept", json={"document_ids": self.documents, **extra})

    def scene(self, row):
        return f"{self.url}/documents/{row['document_id']}/scenes/{row['scene_id']}/binding"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENX_LLM_API_KEY", "test-key")
    monkeypatch.delenv("OPENX_LLM_URL", raising=False)
    seeded = demo_workspace.seed(tmp_path / "data", "fixtures")
    model = FakeModel()
    monkeypatch.setattr(ModelClient, "complete", lambda self, body, **kwargs: model(self, body, **kwargs))
    monkeypatch.setattr(ModelClient, "catalog", lambda self: [ModelInfo(self.config.model, ("low", "high", "max"), "high")])
    api._cache.clear()
    client = TestClient(api.app, base_url="http://127.0.0.1")
    client.put("/api/settings/preferences", json={"encoder": "hashing"})  # BGE would load a large model
    project, document = seeded["project_id"], seeded["documents"][0]["document_id"]
    yield client, Base(client, project, [document]), model, seeded
    api._cache.clear()


def finished(client, job):
    for _ in range(3000):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def suggested(client, base):
    response = base.suggest()
    assert response.status_code == 200, response.text
    job = finished(client, response.json())
    assert job["status"] == "completed", job
    return job, base.view()


def test_title_order_reads_chinese_pieces_and_ignores_numbers_and_notes():
    assets = [authored_asset() for _ in range(3)]
    assets[0].title, assets[1].title, assets[2].title = "7.4.1 切入（白天）", "目标车切入 v2", "行人横穿"
    assert title_order("目标车辆切入（夜间）7.4.1", assets) == [1, 0]  # 车切入 shares more than 切入
    assert title_order("Cut-in 7.4.1", assets) == []


def test_pool_starts_with_the_ranking_and_names_the_routes():
    assets = [authored_asset(function="AEB") for _ in range(12)]
    for number, asset in enumerate(assets):
        asset.asset_id, asset.title = f"a{number}", f"Asset {number}"
    assets[11].title = "目标车辆前方静止"
    package = requirement()
    package.title = "目标车辆前方静止"
    index = OpenXIndex(assets)
    pool = candidate_pool(index, package)
    ranked = index.search("", query=scene_package_to_query(package), top_k=len(assets))
    assert [item.result.asset.asset_id for item in pool[:10]] == [item.asset.asset_id for item in ranked[:10]]
    assert all("full" in item.routes for item in pool[:10]) and [item.rank for item in pool[:10]] == list(range(1, 11))
    titled = next(item for item in pool if item.result.asset.asset_id == "a11")
    assert "title" in titled.routes and len(pool) == len({item.result.asset.asset_id for item in pool})


def test_suggestions_are_kept_and_accepting_them_binds_and_pins(demo):
    client, base, model, _ = demo
    job, view = suggested(client, base)
    # Three readings of each of the four scenes, all at the deepest effort the model declares.
    assert job["result"]["failed"] == 0 and job["result"]["usage"]["calls"] == 12 == model.calls
    assert job["result"]["effort"] == "max" and model.efforts == {"max": 12}
    rows = view["scenes"]
    assert len(rows) == 4 and all(row["binding"] is None for row in rows)
    for row in rows:
        suggestion = row["suggestion"]
        assert suggestion["outdated"] == [] and suggestion["failure"] == ""
        assert (suggestion["readings"], suggestion["agree"], suggestion["other_preferred"], suggestion["stable"]) == (3, 3, [], True)
        preferred = next(item for item in suggestion["candidates"] if item["id"] == suggestion["preferred"])
        assert preferred["verdict"] == "同一测试" and preferred["latest"] and preferred["routes"][0] == "full"
    # The same request again is answered from the cache.
    suggested(client, base)
    assert model.calls == 12

    view = base.accept().json()
    bound = [row["binding"] for row in view["scenes"]]
    assert all(item and item["status"] == "same" and item["source"] == "suggestion" and item["stale"] == []
               for item in bound)
    first = bound[0]["assets"][0]
    store = AssetStore()
    version = next(item for item in store.versions() if item.version_id == first["version_id"])
    assert any(reference.startswith("binding:") for reference in store.references(version))
    with pytest.raises(ValueError):
        store.delete_version(version)  # a bound version stays


def test_one_job_suggests_for_several_pdfs_and_lists_them_together(demo):
    client, base, model, seeded = demo
    documents = [item["document_id"] for item in reversed(seeded["documents"])]
    group = Base(client, seeded["project_id"], documents)
    job, view = suggested(client, group)
    expected = [item["document_id"] for item in reversed(seeded["documents"]) for _ in range(item["scenes"])]
    assert [row["document_id"] for row in view["scenes"]] == expected  # the PDFs in the order selected
    assert model.calls == 3 * len(expected) and job["result"]["document_ids"] == documents
    assert [item["document_id"] for item in view["documents"]] == documents
    assert {row["filename"] for row in view["scenes"]} == {"demo-aeb-protocol.pdf", "demo-aeb-protocol-zh.pdf"}
    assert base.view()["job"]["id"] == job["id"]  # one suggestion job per project, seen from any selection
    assert all(row["binding"] for row in group.accept().json()["scenes"])
    assert client.get(group.url + "/bindings", params={"document_ids": documents[:1] * 2}).status_code == 400
    assert client.get(group.url + "/bindings", params={"document_ids": ["unknown"]}).status_code == 404


def test_a_person_changes_the_choice_marks_none_and_removes(demo):
    client, base, _, _ = demo
    _, view = suggested(client, base)
    row = view["scenes"][0]
    others = [item for item in row["suggestion"]["candidates"] if item["verdict"] == "不是"][:2]
    request = {"status": "modify", "changes": "把目标车改成静止",
               "assets": [{"asset_id": item["asset_id"], "version_id": item["version_id"]} for item in others],
               "preferred": others[1]["asset_id"]}
    url = base.scene(row)
    binding = client.put(url, json=request).json()["binding"]
    assert binding["source"] == "manual" and binding["status"] == "modify" and binding["changes"] == "把目标车改成静止"
    assert [item["preferred"] for item in binding["assets"]] == [False, True]
    assert binding["assets"][0]["verdict"] == "不是"  # the model's words travel with the asset

    store = AssetStore()
    pinned = lambda: {item.version_id for item in store.versions()
                      if any(ref.startswith("binding:") for ref in store.references(item))}
    assert pinned() == {item["version_id"] for item in others}
    none = client.put(url, json={"status": "none"}).json()["binding"]
    assert none["status"] == "none" and none["assets"] == [] and pinned() == set()
    assert client.put(url, json={"status": "same"}).status_code == 400  # same test needs an asset
    assert client.delete(url).json()["binding"] is None
    assert client.delete(url).status_code == 400

    # Accepting the row's own suggestion as is counts as the suggestion.
    suggestion = row["suggestion"]
    chosen = [item for item in suggestion["candidates"] if item["id"] in suggestion["binding"]]
    exact = {"status": "same", "assets": [{"asset_id": item["asset_id"], "version_id": item["version_id"]}
                                          for item in chosen]}
    assert client.put(url, json=exact).json()["binding"]["source"] == "suggestion"


def test_an_edited_scene_or_a_new_asset_version_asks_for_a_second_look(demo):
    client, base, _, seeded = demo
    _, view = suggested(client, base)
    base.accept()
    row = view["scenes"][0]
    pdf = PdfStore(AssetStore())
    project, document = seeded["project_id"], seeded["documents"][0]["document_id"]
    pdf.revise_scene(project, document, row["scene_id"], {"title": row["title"] + " (edited)"})
    edited = base.view()["scenes"][0]
    assert edited["key"] == row["key"]  # an edit keeps the requirement
    assert edited["binding"]["stale"] == ["scene"] and edited["suggestion"]["outdated"] == ["scene"]
    assert base.accept(scenes=[{"document_id": row["document_id"], "scene_id": row["scene_id"]}]).status_code == 400

    # A new version of a bound asset: the binding keeps its version and asks again.
    bound = base.view()["scenes"][1]["binding"]["assets"][0]
    store = AssetStore()
    version = next(item for item in store.versions() if item.version_id == bound["version_id"])
    scenario = store.file_bytes(version, "scenario").replace(b"<FileHeader", b"<!-- v2 -->\n<FileHeader", 1)
    store.import_files([AssetFile(version.source_name, scenario), AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes())])
    api._cache.clear()
    again = base.view()["scenes"][1]
    assert again["binding"]["stale"] == ["asset"] and again["binding"]["assets"][0]["version_id"] == bound["version_id"]
    assert "asset" in again["suggestion"]["outdated"]


def test_the_same_pdf_in_another_project_finds_the_binding(demo):
    client, base, _, seeded = demo
    suggested(client, base)
    base.accept()
    store = AssetStore()
    pdf = PdfStore(store)
    source = pdf.documents(seeded["project_id"])[-1]
    other = pdf.projects.create("Second")
    copy = pdf.import_pdf(other.project_id, source.filename, pdf.pdf_bytes(source), source.source_standard, engine="legacy")
    rows = Base(client, other.project_id, [copy.document_id]).view()["scenes"]
    first = base.view()["scenes"]
    # Revision 1 of the copy has the extracted titles; the demo's confirmed scenes are revision 2.
    assert [row["key"] for row in rows] == [row["key"] for row in first]
    assert all(row["binding"]["confirmed_in"]["project_id"] == seeded["project_id"] for row in rows)


def test_readings_that_disagree_leave_the_scene_to_a_person(demo):
    client, base, model, _ = demo
    model.answer = lambda body, client, nth: judged(body, "C2" if nth == 3 else "C1")
    _, view = suggested(client, base)
    suggestion = view["scenes"][0]["suggestion"]
    assert suggestion["preferred"] == "C1" and suggestion["binding"] == ["C1", "C2"]  # what most readings say
    assert (suggestion["readings"], suggestion["agree"], suggestion["other_preferred"], suggestion["stable"]) == (3, 2, ["C2"], False)
    assert all(row["binding"] is None for row in base.accept().json()["scenes"])  # "accept all" leaves them
    first = view["scenes"][0]
    named = base.accept(scenes=[{"document_id": first["document_id"], "scene_id": first["scene_id"]}]).json()
    assert named["scenes"][0]["binding"]["source"] == "suggestion"  # a person accepts it by name


def test_a_reply_cut_off_at_the_deepest_effort_is_read_again_at_the_default(demo):
    client, base, model, _ = demo
    model.answer = lambda body, client, nth: (reply({}, finish="length") if client.config.reasoning_effort == "max"
                                              else judged(body))
    first = base.view()["scenes"][0]
    only = [{"document_id": first["document_id"], "scene_id": first["scene_id"]}]
    job = finished(client, base.suggest(scenes=only).json())
    assert job["result"]["failed"] == 0 and model.efforts == {"max": 3, "high": 3}
    assert base.view()["scenes"][0]["suggestion"]["stable"]
    finished(client, base.suggest(scenes=only).json())
    assert model.calls == 6  # the replies kept under the default effort answer the next run


def test_the_deepest_declared_effort_and_its_fallback(monkeypatch):
    def efforts(levels=(), default="", thinking=True, fails=False):
        def catalog(self):
            if fails:
                raise ModelError("no list")
            return [ModelInfo("judge", levels, default)]
        monkeypatch.setattr(ModelClient, "catalog", catalog)
        return judge_efforts(ModelClient(ModelConfig(model="judge", api_key="k", thinking=thinking, reasoning_effort="low")))

    assert efforts(("low", "high", "max"), "high") == ("max", "high")
    assert efforts(("max", "low", "high"), "max") == ("max", "high")  # listed in any order
    assert efforts(("low", "medium", "high"), "") == ("high", "medium")
    assert efforts(("high",), "high") == ("high", "high")
    assert efforts() == efforts(fails=True) == efforts(("low", "max"), thinking=False) == ("low", "low")


def test_replies_that_never_fit_fail_the_scene_and_a_wrong_key_fails_the_run(demo):
    client, base, model, _ = demo
    model.answer = lambda body, client, nth: reply({"candidates": [], "binding": []})
    job, view = suggested(client, base)
    assert job["result"]["failed"] == 4 and model.calls == 24  # two tries of three readings each
    assert all(row["suggestion"]["failure"].startswith("candidates not judged") for row in view["scenes"])
    assert all(row["suggestion"]["stable"] is None for row in view["scenes"])
    assert base.accept().json()["scenes"][0]["binding"] is None

    def refuse(body, client, nth):
        raise ModelError("模型服务 HTTP 401")
    model.answer = refuse
    first = view["scenes"][0]
    response = base.suggest(scenes=[{"document_id": first["document_id"], "scene_id": first["scene_id"]}])
    assert finished(client, response.json())["status"] == "failed"


def test_suggestions_need_a_model(demo, monkeypatch):
    client, base, _, _ = demo
    monkeypatch.delenv("OPENX_LLM_API_KEY")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = base.suggest()
    assert response.status_code == 400 and "Key" in response.json()["detail"]


def test_an_asset_lists_its_clauses_and_coverage_counts_every_pdf(demo):
    client, base, _, seeded = demo
    _, view = suggested(client, base)
    base.accept()
    rows = view["scenes"]
    client.put(base.scene(rows[3]), json={"status": "none"})
    preferred = next(item for item in base.view()["scenes"][0]["binding"]["assets"] if item["preferred"])

    clauses = client.get(f"/api/assets/{preferred['asset_id']}/bindings").json()
    first = next(item for item in clauses if item["scene_id"] == rows[0]["scene_id"])
    assert first["preferred"] and first["status"] == "same" and first["group_size"] == 2 and first["latest"]
    assert first["title"] == rows[0]["title"] and first["stale"] == []
    assert client.get("/api/assets/unknown/bindings").json() == []

    project = seeded["project_id"]
    coverage = client.get(f"/api/projects/{project}/bindings/coverage").json()
    matched, other = sorted(coverage["documents"], key=lambda item: item["unconfirmed"])
    assert (matched["same"], matched["none"], matched["unconfirmed"]) == (3, 1, 0)
    assert other["unconfirmed"] == 4 and other["same"] == 0
    assert next(row for row in matched["scenes"] if row["scene_id"] == rows[0]["scene_id"])["assets"][0] == preferred["title"]
    bound = {item["asset_id"] for row in base.view()["scenes"] if row["binding"]
             for item in row["binding"]["assets"]}
    assert coverage["bound_asset_count"] == len(bound)
    assert len(coverage["unused_assets"]) == coverage["asset_count"] - len(bound) == 6 - len(bound)


def test_the_binding_table_exports_as_csv_and_html(demo):
    client, base, _, _ = demo
    _, view = suggested(client, base)
    rows = view["scenes"]
    client.put(base.scene(rows[0]), json={"status": "modify", "changes": "把目标车改成静止",
                                          "assets": [{"asset_id": item["asset_id"], "version_id": item["version_id"]}
                                                     for item in rows[0]["suggestion"]["candidates"][:2]]})
    client.put(base.scene(rows[1]), json={"status": "none"})
    url = base.url + "/bindings/export"
    response = client.get(url, params={"document_ids": base.documents, "format": "csv"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith("\ufeff".encode())  # a spreadsheet reads it as UTF-8
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("PDF,条款,条款标题,复用结论,首选复用素材") and len(lines) == 1 + len(rows)
    first, second, third = lines[1:4]
    assert ",修改复用," in first and "把目标车改成静止" in first and ",人工指定," in first
    assert ",不适用," in second
    assert ",待确认," in third and "（直接复用）" in third and third.endswith(",一致 3/3")  # the suggestion while unconfirmed

    english = client.get(url, params={"document_ids": base.documents, "format": "html", "lang": "en"})
    assert english.status_code == 200 and english.headers["content-type"].startswith("text/html")
    assert "Clause reuse assessment" in english.text and "To confirm" in english.text and "Consistent 3/3" in english.text
    assert "filename*=UTF-8''" in english.headers["content-disposition"]
