"""Authored conversion/authorization cases; no private SIM content."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from lxml import etree
import pytest

from openx_workbench.standard_export import build_standard_export
from openx_workbench.dependency_package import package_files
from openx_workbench.catalog import AssetFile
from openx_workbench.asset_store import AssetStore


def source(monkeypatch, *, extension=False, collision=False, dependency=False):
    fixtures = Path(__file__).parent / "fixtures"
    root = etree.fromstring((fixtures / "minimal.xosc").read_bytes())
    declarations = etree.SubElement(root, "ParameterDeclarations")
    etree.SubElement(declarations, "ParameterDeclaration", name="$speed", parameterType="double", value="12.5")
    if collision:
        etree.SubElement(declarations, "ParameterDeclaration", name="speed", parameterType="double", value="99")
    speed = root.find(".//AbsoluteTargetSpeed")
    speed.set("value", "$speed")
    root.find(".//PrivateAction").set("name", "editor-label")
    actions = root.find(".//Init/Actions")
    command = etree.SubElement(etree.SubElement(actions, "UserDefinedAction"), "CustomCommandAction",
                              type="custom", content='command < 1 & ready')
    if extension:
        etree.SubElement(root, "FittedClothoid", curvature="0.5")
    if dependency:
        etree.SubElement(root, "Directory", path="missing/catalog")
    road = etree.fromstring((fixtures / "minimal.xodr").read_bytes())
    section = road.find(".//laneSection")
    etree.SubElement(section, "left")
    originals = {"scenario": etree.tostring(root), "road": etree.tostring(road), "source": b"authored SIM source"}
    store = SimpleNamespace(file_bytes=lambda version, role: originals[role])
    version = SimpleNamespace(source_name="authored.sim", asset_id="asset", version_id="version", content_sha256="content")
    # Isolates authorization and conversion behavior, not ASAM conformance.
    # Real pinned-ASAM checks run against the separate private L2 corpus.
    monkeypatch.setattr("openx_workbench.standard_export.validate_xml", lambda data: {
        "status": "invalid" if b"FittedClothoid" in data else "valid", "issues": [], "source_revision": "authored"})
    return store, version, originals, command


def test_export_keeps_originals_and_audits_complete_converted_copy(monkeypatch):
    store, version, originals, _ = source(monkeypatch)
    export = build_standard_export(store, version)
    assert export.ready
    with zipfile.ZipFile(io.BytesIO(export.package())) as archive:
        for role, filename in (("scenario", "scenario.xosc"), ("road", "road.xodr"), ("source", "source.sim")):
            assert archive.read("original/" + filename) == originals[role]
        root = etree.fromstring(archive.read("standard/scenario.xosc"))
        assert root.find(".//ParameterDeclaration").get("name") == "speed"
        assert root.find(".//AbsoluteTargetSpeed").get("value") == "$speed"
        assert root.find(".//CustomCommandAction").text == 'command < 1 & ready'
        assert root.find(".//PrivateAction").get("name") is None
        assert root.find(".//RoadNetwork/LogicFile").get("filepath") == "road.xodr"
        assert root.find(".//Action").get("name") == "Accelerate"
        audit = json.loads(archive.read("audit.json"))
        assert audit["version_id"] == version.version_id
        assert any(c["before"] == "editor-label" for c in audit["changes"])
        assert audit["original_sha256"]["scenario"] == hashlib.sha256(originals["scenario"]).hexdigest()
    assert store.file_bytes(version, "scenario") == originals["scenario"]


@pytest.mark.parametrize("reason", ["extension", "collision", "dependency"])
def test_unresolved_export_remains_diagnostic_and_retains_evidence(monkeypatch, reason):
    store, version, originals, _ = source(monkeypatch, **{reason: True})
    export = build_standard_export(store, version)
    assert not export.ready
    with pytest.raises(ValueError, match="diagnostic"):
        export.package()
    with zipfile.ZipFile(io.BytesIO(export.package(diagnostic=True))) as archive:
        assert "standard/scenario.xosc" not in archive.namelist()
        assert archive.read("original/scenario.xosc") == originals["scenario"]
        if reason == "extension":
            assert b"FittedClothoid" in archive.read("candidate/scenario.xosc")
        if reason == "collision":
            assert export.audit["parameter_issues"]
        if reason == "dependency":
            assert export.audit["external_dependencies"]


def test_conflicting_command_and_referenced_editor_action_are_not_silently_rewritten(monkeypatch):
    store, version, originals, _ = source(monkeypatch)
    root = etree.fromstring(originals["scenario"])
    root.find(".//CustomCommandAction").text = "different command"
    etree.SubElement(root, "StoryboardElementStateCondition", storyboardElementRef="editor-label")
    originals["scenario"] = etree.tostring(root)
    export = build_standard_export(store, version)
    assert not export.ready
    assert {item["reason"] for item in export.audit["unresolved"]} == {
        "conflicting_command_content", "referenced_private_action_label"}
    assert etree.fromstring(export.scenario).find(".//PrivateAction").get("name") == "editor-label"


def test_unknown_schema_never_enables_standard_download(monkeypatch):
    store, version, _, _ = source(monkeypatch)
    monkeypatch.setattr("openx_workbench.standard_export.validate_xml", lambda data: {"status": "unavailable"})
    export = build_standard_export(store, version)
    assert not export.ready


def test_visual_model_and_road_surface_dependencies_require_review(monkeypatch):
    store, version, originals, _ = source(monkeypatch)
    scenario = etree.fromstring(originals["scenario"])
    scenario.find(".//Vehicle").set("model3d", "models/car.osgb")
    road = etree.fromstring(originals["road"])
    etree.SubElement(etree.SubElement(road.find("road"), "surface"), "CRG", file="surfaces/road.crg")
    originals.update(scenario=etree.tostring(scenario), road=etree.tostring(road))
    export = build_standard_export(store, version)
    assert not export.ready
    assert {(item["role"], item["reference"]) for item in export.audit["external_dependencies"]} == {
        ("scenario", "models/car.osgb"), ("road", "surfaces/road.crg")}


def test_export_package_reimports_only_the_checked_pair_with_original_archive_retained(monkeypatch, tmp_path):
    store, version, _, _ = source(monkeypatch)
    export = build_standard_export(store, version)
    data = export.package()
    files = package_files(data)
    assert {file.name for file in files} == {"audit.json", "standard/scenario.xosc", "standard/road.xodr"}
    assets = AssetStore(tmp_path)
    imported = assets.import_files([AssetFile("standard.zip", data)])
    assert len(imported) == 1
    assert imported[0].xodr_name == "standard/road.xodr"
    assert assets.file_bytes(imported[0], "road") == export.road
    assert assets.file_bytes(imported[0], "source") == data
    with pytest.raises(ValueError, match="Diagnostic"):
        bad_store, bad_version, _, _ = source(monkeypatch, extension=True)
        package_files(build_standard_export(bad_store, bad_version).package(diagnostic=True))


def test_standard_package_integrity_is_checked_independently_of_audit_ready_flag(monkeypatch):
    store, version, _, _ = source(monkeypatch)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_standard_export(store, version).package())) as original, zipfile.ZipFile(output, "w") as changed:
        for name in original.namelist():
            data = original.read(name)
            changed.writestr(name, data + b"tampered" if name == "standard/road.xodr" else data)
    with pytest.raises(ValueError, match="integrity"):
        package_files(output.getvalue())
