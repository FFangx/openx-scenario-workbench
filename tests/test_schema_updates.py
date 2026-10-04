"""Registry updates against an authored esmini stand-in: no network, and none of these are ASAM XSDs."""
import json
import time

import pytest

from openx_workbench import schema_updates as su
from openx_workbench.schema_validation import ENTRIES, validate_xml

pytest.importorskip("lxml")
pytest.importorskip("xmlschema")

OLD, NEW = "a" * 40, "b" * 40
XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
HEADER = ('<xs:element name="FileHeader"><xs:complexType>'
          '<xs:attribute name="revMajor" type="xs:integer" use="required"/>'
          '<xs:attribute name="revMinor" type="xs:integer" use="required"/>'
          '<xs:anyAttribute processContents="skip"/></xs:complexType></xs:element>')


def scenario(body: str) -> bytes:
    return (f'<xs:schema {XS}><xs:include schemaLocation="parts.xsd"/>'
            f'<xs:element name="OpenSCENARIO"><xs:complexType><xs:sequence>{HEADER}{body}'
            '</xs:sequence></xs:complexType></xs:element></xs:schema>').encode()


PARTS = f'<xs:schema {XS}><xs:complexType name="Body"/></xs:schema>'.encode()
ANY = '<xs:any processContents="skip" minOccurs="0" maxOccurs="unbounded"/>'
ROAD = (f'<xs:schema {XS}><xs:element name="OpenDRIVE"><xs:complexType><xs:sequence>'
        '<xs:element name="header"><xs:complexType><xs:anyAttribute processContents="skip"/></xs:complexType></xs:element>'
        f'{ANY}</xs:sequence><xs:assert test="header"/></xs:complexType></xs:element></xs:schema>').encode()

REMOTE = {
    # The older revision insists on an element the fixture scenario does not have.
    OLD: {"OpenSCENARIOv1.2.xsd": scenario('<xs:element name="RequiredBody" type="Body"/>' + ANY),
          "parts.xsd": PARTS},
    NEW: {"OpenSCENARIOv1.2.xsd": scenario(ANY), "parts.xsd": PARTS,
          "OpenDRIVE_1.7/local/OpenDRIVE_Core.xsd": ROAD,
          "OpenDRIVE_2.0/a_core.xsd": ROAD, "OpenDRIVE_2.0/b_core.xsd": ROAD,
          "OpenSCENARIOv1.3.xsd": f'<xs:schema {XS}><xs:include schemaLocation="https://example.com/x.xsd"/></xs:schema>'.encode()},
}


@pytest.fixture
def remote(monkeypatch):
    calls = []
    latest = {"revision": OLD}

    def commit(revision):
        return {"sha": revision, "commit": {"committer": {"date": "2026-09-0%dT00:00:00Z" % (1 + (revision == NEW))},
                                            "message": f"Authored {revision[0]}\n\nbody"}}

    def get(url, accept=""):
        calls.append(url)
        for revision, files in REMOTE.items():
            prefix = su.RAW.format(revision=revision)
            if url.startswith(prefix):
                if url[len(prefix):] not in files:
                    raise su.SchemaUpdateError("404")
                return files[url[len(prefix):]]
        if url.startswith(f"{su.API}/commits?"):
            body = [commit(latest["revision"])]
        elif url.startswith(f"{su.API}/commits/"):
            body = commit(url.rsplit("/", 1)[1])
        elif url.startswith(f"{su.API}/contents/resources?ref="):
            body = [{"name": "schema", "type": "dir", "sha": "tree-" + url.rsplit("=", 1)[1]}]
        else:
            revision = url.split("tree-", 1)[1].split("?", 1)[0]
            body = {"truncated": False, "tree": [{"type": "blob", "path": path, "sha": su.git_blob_sha(data)}
                                                 for path, data in REMOTE[revision].items()]}
        return json.dumps(body).encode()

    monkeypatch.setattr(su, "_get", get)
    return latest, calls


def test_entries_follow_known_paths_and_never_guess_between_candidates():
    paths = {ENTRIES["OpenDRIVE:1.8"], "OpenDRIVE_1.8/OpenDRIVE_Core.xsd", "OpenSCENARIOv1.3.xsd",
             "OpenSCENARIOv1.3.1.xsd", "OpenDRIVE_1.9/schema/OpenDRIVE_Core.xsd",
             "OpenDRIVE_1.9/local_schema/OpenDRIVE_Core.xsd", "OpenDRIVE_2.0/a_core.xsd", "OpenDRIVE_2.0/b_core.xsd"}
    entries, unmapped = su.discover_entries(paths)
    assert entries == {"OpenDRIVE:1.8": ENTRIES["OpenDRIVE:1.8"], "OpenSCENARIO:1.3": "OpenSCENARIOv1.3.1.xsd",
                       "OpenDRIVE:1.9": "OpenDRIVE_1.9/local_schema/OpenDRIVE_Core.xsd"}
    assert list(unmapped) == ["OpenDRIVE:2.0"]


def test_install_follows_includes_detects_xsd11_and_reports_what_it_left_out(remote, tmp_path):
    snapshot = su.remote_snapshot(NEW)
    assert snapshot["unmapped"].keys() == {"OpenDRIVE:2.0"}
    registry = su.install(tmp_path / "r", NEW, snapshot["entries"], skipped=snapshot["unmapped"])
    assert registry["entries"] == {"OpenSCENARIO:1.2": "OpenSCENARIOv1.2.xsd",
                                   "OpenDRIVE:1.7": "OpenDRIVE_1.7/local/OpenDRIVE_Core.xsd"}
    assert set(registry["sha256"]) == {"OpenSCENARIOv1.2.xsd", "parts.xsd", "OpenDRIVE_1.7/local/OpenDRIVE_Core.xsd"}
    assert registry["xsd_versions"] == {"OpenDRIVE:1.7": "1.1"}
    assert set(registry["skipped"]) == {"OpenDRIVE:2.0", "OpenSCENARIO:1.3"}
    assert "External" in registry["skipped"]["OpenSCENARIO:1.3"]
    xodr = b'<OpenDRIVE><header revMajor="1" revMinor="7"/></OpenDRIVE>'
    assert validate_xml(xodr, root=tmp_path / "r")["status"] == "valid"


def test_check_compares_file_ids_without_downloading(remote, tmp_path):
    latest, calls = remote
    root = tmp_path / "schemas"
    assert su.check(root)["installed"] is False
    su.install(root, OLD, {"OpenSCENARIO:1.2": "OpenSCENARIOv1.2.xsd"})
    calls.clear()
    assert su.check(root)["up_to_date"] is True
    assert not [url for url in calls if url.startswith("https://raw.")]
    latest["revision"] = NEW
    update = su.check(root)
    assert update["up_to_date"] is False and update["changed"] == ["OpenSCENARIOv1.2.xsd"]
    assert update["new_versions"] == ["OpenDRIVE:1.7", "OpenSCENARIO:1.3"]
    assert list(update["unmapped"]) == ["OpenDRIVE:2.0"]


def _wait(client, job):
    for _ in range(200):
        if job["status"] != "running":
            return job
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").json()
    raise AssertionError("schema preview did not finish")


def test_preview_switch_and_rollback_through_the_api(workbench, remote, tmp_path):
    client, base, version = workbench
    root = tmp_path / "schemas"
    su.install(root, OLD, {"OpenSCENARIO:1.2": "OpenSCENARIOv1.2.xsd"})
    checks = lambda: client.post("/api/search", json=base).json()["results"][0]["standard_checks"]["checks"]
    assert checks()["scenario"]["status"] == "invalid"

    assert client.post("/api/settings/schemas/apply", json={"revision": NEW}).status_code == 400
    job = _wait(client, client.post("/api/settings/schemas/preview", json={"revision": NEW}).json())
    assert job["status"] == "completed", job["error"]
    status = client.get("/api/settings/schemas").json()
    assert status["active"]["revision"] == OLD and status["staged"]["revision"] == NEW
    changes = status["staged"]["preview"]["changes"]
    assert {(c["role"], c["before"]["status"], c["after"]["status"]) for c in changes} == {
        ("scenario", "invalid", "valid"), ("road", "unsupported", "valid")}
    assert checks()["scenario"]["status"] == "invalid"  # previewing never changes a verdict

    assert client.post("/api/settings/schemas/apply", json={"revision": OLD}).status_code == 400
    applied = client.post("/api/settings/schemas/apply", json={"revision": NEW}).json()
    assert applied["active"]["revision"] == NEW and applied["previous"]["revision"] == OLD
    assert applied["staged"] is None
    assert checks()["scenario"]["status"] == "valid"  # the parsed catalog follows the switch

    rolled = client.post("/api/settings/schemas/rollback").json()
    assert rolled["active"]["revision"] == OLD and rolled["previous"]["revision"] == NEW
    assert checks()["scenario"]["status"] == "invalid"


def test_discard_and_refusals(workbench, remote, tmp_path):
    client, _, _ = workbench
    assert client.post("/api/settings/schemas/rollback").status_code == 400
    assert client.post("/api/settings/schemas/preview", json={"revision": "main"}).status_code == 422
    job = _wait(client, client.post("/api/settings/schemas/preview", json={"revision": NEW}).json())
    assert job["status"] == "completed", job["error"]
    assert client.get("/api/settings/schemas").json()["staged"]["preview"]["compared"] == 1
    assert client.delete("/api/settings/schemas/staged").json()["staged"] is None
    assert not su.staging_root(tmp_path / "schemas").exists()
