from pathlib import Path

import pymupdf
from streamlit.testing.v1 import AppTest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report


def _open_management(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_asset_management").click().run()
    assert not app.exception
    return app


def _select_asset(app, version):
    # AppTest has no dataframe row-selection API. Set the explicit selection
    # consumed by the detail panel; browser acceptance covers the row click.
    app.session_state["managed_asset_key"] = f"{version.asset_id}:{version.version_id}"
    return app.run(timeout=10)


def _authored_assets(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    scenario = (fixtures / "minimal.xosc").read_bytes()
    road = (fixtures / "minimal.xodr").read_bytes()
    store = AssetStore(tmp_path)
    versions = []
    for name, title in (("urban_aeb.xosc", "Urban AEB pedestrian"),
                        ("highway_acc.xosc", "Highway ACC lead vehicle")):
        versions.append(store.import_files([
            AssetFile(name, scenario.replace(b"Minimal cut-in", title.encode())),
            AssetFile("minimal.xodr", road),
        ])[0])
    return store, versions, scenario, road


def test_streamlit_navigation_starts_without_exceptions(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert app.session_state["active_page"] == "home"
    app.text_input(key="new_project_name").set_value("Test project").run()
    app.button(key="create_project").click().run()
    assert not app.exception
    assert app.selectbox(key="active_project_id").value
    for page in ("text_search", "asset_management", "pdf_workflow"):
        app.button(key="nav_" + page).click().run()
        assert not app.exception


def test_asset_management_opens_a_saved_version(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    fixtures = Path(__file__).parent / "fixtures"
    version = AssetStore(tmp_path).import_files([
        AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
        AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
    ])[0]
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_" + "asset_management").click().run()
    assert not app.exception
    assert app.session_state["managed_asset_key"] is None
    _select_asset(app, version)
    assert not app.exception
    assert app.button(key="run_esmini_preview")


def test_empty_asset_management_has_import_access_without_details(tmp_path, monkeypatch):
    app = _open_management(tmp_path, monkeypatch)
    assert app.session_state["managed_asset_key"] is None
    assert not any(button.key == "classify_asset" for button in app.button)
    assert not any(button.key == "delete_managed_version" for button in app.button)
    app.button(key="open_asset_import").click().run()
    assert not app.exception
    assert app.session_state["asset_import_open"] is True
    app.radio(key="asset_source").set_value("upload").run()
    assert not app.exception
    assert app.get("file_uploader")


def test_asset_table_search_latest_scope_and_historical_inspection(tmp_path, monkeypatch):
    store, versions, scenario, road = _authored_assets(tmp_path)
    original = versions[0]
    latest = store.import_files([
        AssetFile("urban_aeb.xosc", scenario.replace(b"Minimal cut-in", b"Urban AEB revised")),
        AssetFile("minimal.xodr", road),
    ])[0]
    app = _open_management(tmp_path, monkeypatch)
    assert app.checkbox(key="asset_latest_only").value is True
    assert len(app.dataframe[0].value) == 2
    app.text_input(key="asset_library_search").set_value("HIGHWAY").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    assert "Highway ACC" in str(app.dataframe[0].value)
    app.text_input(key="asset_library_search").set_value("").run()
    app.checkbox(key="asset_latest_only").uncheck().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 3
    _select_asset(app, latest)
    assert not app.exception
    app.selectbox(key="managed_history_version").set_value(f"{original.asset_id}:{original.version_id}").run()
    app.button(key="inspect_asset_history").click().run()
    assert not app.exception
    assert app.session_state["managed_asset_key"] == f"{original.asset_id}:{original.version_id}"
    assert store.file_bytes(original, "scenario") == scenario.replace(b"Minimal cut-in", b"Urban AEB pedestrian")
    app.button(key="close_asset_detail").click().run()
    assert not app.exception
    assert app.session_state["managed_asset_key"] is None


def test_asset_filters_clear_detail_and_use_saved_classification(tmp_path, monkeypatch):
    from openx_workbench.classification import classify_asset, confirm_classification
    from openx_workbench.llm_service import ModelClient

    store, versions, _, _ = _authored_assets(tmp_path)
    classified = classify_asset(store, versions[0])
    confirm_classification(store, versions[0], {**classified["final"], "label_road_type": "直道"})
    classified = classify_asset(store, versions[1])
    confirm_classification(store, versions[1], {**classified["final"], "label_road_type": "弯道"})
    before = {path: path.read_bytes() for path in (tmp_path / "assets").glob("*/*/classification.json")}
    calls = []
    monkeypatch.setattr(ModelClient, "complete", lambda *args: calls.append(args))
    app = _open_management(tmp_path, monkeypatch)
    _select_asset(app, versions[0])
    assert not app.exception
    app.selectbox(key="asset_function_filter").set_value("ACC").run()
    assert not app.exception
    assert app.session_state["managed_asset_key"] is None
    assert len(app.dataframe[0].value) == 1
    assert "Highway ACC" in str(app.dataframe[0].value)
    app.selectbox(key="asset_road_filter").set_value("直道").run()
    assert not app.exception
    assert not app.dataframe
    assert any("没有符合筛选条件" in info.value for info in app.info)
    assert not calls
    assert all(path.read_bytes() == contents for path, contents in before.items())


def test_asset_row_selection_signature_tracks_order_and_filter_context(tmp_path):
    from openx_workbench.asset_management import asset_rows, selection_signature

    store, versions, _, _ = _authored_assets(tmp_path)
    rows = asset_rows(store, versions, "zh")
    assert [row["classification"] for row in rows] == ["pending", "pending"]
    assert selection_signature(rows) == selection_signature(asset_rows(store, versions, "en"))
    assert selection_signature(rows) != selection_signature(list(reversed(rows)))
    assert selection_signature(rows) != selection_signature(rows, ("ACC",))
    assert not list((tmp_path / "assets").glob("*/*/classification.json"))


def test_import_status_survives_new_ui_session(tmp_path, monkeypatch):
    from openx_workbench.import_jobs import ImportJob
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    fixtures = Path(__file__).parent / "fixtures"
    store = AssetStore(tmp_path)
    store.import_files([AssetFile(name, (fixtures / name).read_bytes())
                        for name in ("minimal.xosc", "minimal.xodr")])
    job = ImportJob(store)
    job.update(status="completed", stage="classifying", saved=1, done=1, total=1)
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_asset_management").click().run()
    assert not app.exception
    assert len(app.session_state["catalog"]) == 1
    assert any("可配对资产已入库" in element.value for element in app.caption)
    assert app.button(key="resume_asset_classification")
    app.button(key="open_asset_import").click().run()
    assert not app.exception
    assert app.session_state["asset_import_open"] is True
    app.button(key="open_asset_import").click().run()
    assert not app.exception
    assert app.session_state["asset_import_open"] is False
    assert any("可配对资产已入库" in element.value for element in app.caption)
    assert app.button(key="resume_asset_classification")


def test_partial_import_reports_skipped_cases_and_preserves_assets(tmp_path, monkeypatch):
    from openx_workbench.import_jobs import ImportJob

    store, versions, _, _ = _authored_assets(tmp_path)
    ImportJob(store).update(
        status="completed", stage="classifying", saved=2, done=2, total=2,
        reports=[{"source_name": "authored.sim", "case_count": 3,
                  "imported_count": 2, "missing_road_references": ["missing-authored-road.xodr"]}],
    )
    app = _open_management(tmp_path, monkeypatch)
    assert any("来源 3 个场景 · 跳过 1" in item.value for item in app.caption)
    assert any("部分场景未入库" in item.value for item in app.warning)
    assert any("missing-authored-road.xodr" in item.value for item in app.text)
    assert not any("可配对资产已入库" in item.value for item in app.caption)
    assert len(app.dataframe[0].value) == 2
    assert store.versions() == sorted(versions, key=lambda v: (v.asset_id, v.version_number))


def test_classification_and_deletion_locked_during_background_import(tmp_path, monkeypatch):
    from threading import Event
    from openx_workbench.import_jobs import start_import
    from openx_workbench.llm_service import ModelConfig
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    entered, release = Event(), Event()
    class Client:
        config = ModelConfig()
        def complete(self, body):
            entered.set()
            assert release.wait(30)
            raise ValueError("Mock timeout")
    fixtures = Path(__file__).parent / "fixtures"
    job = start_import(AssetStore(tmp_path), [AssetFile(name, (fixtures / name).read_bytes())
                       for name in ("minimal.xosc", "minimal.xodr")], classify=True, client=Client())
    try:
        assert entered.wait(5)
        app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
        app = AppTest.from_file(str(app_path)).run(timeout=10)
        app.button(key="nav_asset_management").click().run()
        assert not app.exception
        assert len(app.session_state["catalog"]) == 1
        _select_asset(app, AssetStore(tmp_path).latest()[0])
        assert not app.exception
        assert app.button(key="classify_asset").disabled
        assert app.button(key="delete_managed_version").disabled
        assert app.button(key="stop_asset_import")
    finally:
        job.cancel.set()
        release.set()


def test_pdf_workflow_opens_saved_scene_only_after_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("PDF review")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "7.4.1 Cut-in scenario\nTarget vehicle cuts in on a straight road. TTC = 3.0 s.")
    record = PdfStore(assets).import_pdf(project.project_id, "rules.pdf", document.tobytes(), engine="legacy")
    document.close()
    other = pymupdf.open()
    other.new_page().insert_text((72, 72), "7.4.2 Braking scenario\nTarget vehicle brakes on a straight road. TTC = 2.0 s.")
    other_record = PdfStore(assets).import_pdf(project.project_id, "other.pdf", other.tobytes(), engine="legacy")
    other.close()
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_" + "pdf_workflow").click().run()
    assert not app.exception
    app.selectbox(key="current_document_id").set_value(record.document_id).run()
    assert app.button(key=f"scene_{record.document_id}_scene-0001")
    app.button(key=f"scene_{record.document_id}_scene-0001").click().run()
    assert not app.exception
    assert app.session_state["selected_stored_scene"].revision == 1
    app.selectbox(key="current_document_id").set_value(other_record.document_id).run()
    assert not app.exception
    assert app.session_state["selected_stored_scene"] is None


def test_pdf_decision_survives_revision_asset_update_and_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Acceptance review")
    fixtures = Path(__file__).parent / "fixtures"
    scenario = (fixtures / "minimal.xosc").read_bytes()
    road = (fixtures / "minimal.xodr").read_bytes()
    version = assets.import_files([AssetFile("minimal.xosc", scenario), AssetFile("minimal.xodr", road)])[0]
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "7.4.1 Cut-in scenario\nTarget vehicle cuts in on a straight road.")
        document.new_page().insert_text((72, 72), "Test vehicle approaches the target vehicle. TTC = 3.0 s.")
        record = PdfStore(assets).import_pdf(project.project_id, "authored-acceptance.pdf", document.tobytes(), engine="legacy")
    original = PdfStore(assets).scenes(project.project_id, record.document_id)[0].package.evidence
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_" + "pdf_workflow").click().run()
    app.button(key=f"scene_{record.document_id}_scene-0001").click().run()
    next(item for item in app.text_input if item.label == "场景标题").set_value("Reviewed cut-in")
    next(item for item in app.button if item.label == "保存事实修订").click().run()
    assert not app.exception
    assert app.session_state["selected_stored_scene"].revision == 2
    app.button(key="pdf_search_button").click().run()
    assert not app.exception
    app.button(key="view_source_files").click().run()
    assert not app.exception
    assert any("OpenSCENARIO" in item.value for item in app.code)
    app.button(key="explain_structural").click().run()
    app.button(key="save_reuse_decision").click().run()
    assert not app.exception
    report = projects.reports(project.project_id)[0]
    trace = report["trace"]
    assert trace["source"]["revision"] == 2
    assert trace["source"]["title"] == "Reviewed cut-in"
    assert trace["source"]["evidence"][0]["page_end"] == 2
    assert trace["candidate"]["version_id"] == version.version_id
    assert trace["explanation"]["method"] == "structural"
    assert "authored-acceptance.pdf" in render_report(trace)
    assert PdfStore(assets).scenes(project.project_id, record.document_id)[0].package.evidence == original
    newer = assets.import_files([AssetFile("minimal.xosc", scenario.replace(b"Minimal cut-in", b"Updated cut-in")),
                                AssetFile("minimal.xodr", road)])[0]
    PdfStore(assets).revise_scene(project.project_id, record.document_id, "scene-0001", {"title": "Later revision"})
    reopened = AppTest.from_file(str(app_path)).run(timeout=10)
    assert not reopened.exception
    assert reopened.selectbox(key=f"saved_report_{project.project_id}").value == report["report_id"]
    assert any(version.version_id in item.value for item in reopened.caption)
    assert newer.version_id != version.version_id
    assert projects.reports(project.project_id)[0] == report
    assert assets.references(version)


def test_workspace_language_help_and_settings_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="toggle_language").click().run()
    assert app.button(key="nav_home").label == "Overview"
    app.button(key="workspace_help").click().run()
    assert not app.exception
    assert any("From assets to reports" in item.value for item in app.markdown)
    app.button(key="workspace_settings").click().run()
    app.text_input(key="settings_esmini").set_value("Z:/missing/esmini.exe")
    app.button(key="workspace_settings").click()
    app.button(key="save_settings").click().run()
    assert app.error
    app.text_input(key="settings_esmini").set_value("")
    app.button(key="workspace_settings").click()
    app.button(key="save_settings").click().run()
    assert not app.exception
    reopened = AppTest.from_file(str(app_path)).run(timeout=10)
    assert reopened.button(key="nav_home").label == "Overview"
    assert reopened.session_state["esmini_path"] == ""


def test_appearance_choices_persist_without_changing_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    assert app.session_state["appearance"] == "system"
    app.button(key="nav_text_search").click().run()
    for mode in ("dark", "light", "system"):
        app.button(key=f"theme_{mode}").click().run()
        assert not app.exception
        assert app.session_state["active_page"] == "text_search"
        restarted = AppTest.from_file(str(app_path)).run(timeout=10)
        assert restarted.session_state["appearance"] == mode
        scheme = "light dark" if mode == "system" else mode
        assert any(f"color-scheme:{scheme}!important" in item.value for item in restarted.markdown)


def test_model_settings_list_manual_selection_test_and_save(tmp_path, monkeypatch):
    from openx_workbench.llm_service import ModelClient, load_config
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(ModelClient, "models", lambda self: ["first-model", "second-model"])
    monkeypatch.setattr(ModelClient, "probe", lambda self: calls.append(self.config.model) or self.config.model)
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="workspace_settings").click().run()
    app.text_input(key="model_api_key").set_value("ui-authored-key")
    app.text_input(key="model_base_url").set_value("https://example.org/v1")
    app.button(key="workspace_settings").click()
    app.button(key="fetch_models").click().run()
    assert app.selectbox(key="model_choice").options[1:] == ["first-model", "second-model"]
    app.selectbox(key="model_choice").select("second-model")
    app.button(key="workspace_settings").click().run()
    assert app.text_input(key="model_name").value == "second-model"
    app.text_input(key="model_name").set_value("manual-model")
    app.button(key="workspace_settings").click()
    app.button(key="test_model").click().run()
    assert calls == ["manual-model"]
    app.button(key="workspace_settings").click()
    app.button(key="save_model").click().run()
    assert not app.exception
    assert load_config(tmp_path).model == "manual-model"
    assert load_config(tmp_path).api_key == "ui-authored-key"


def test_v2_scene_review_library_and_return_to_source(tmp_path, monkeypatch):
    from test_pdf_v2_migration import authored_pdf, fake_client
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("V2 review")
    client, _ = fake_client()
    record = PdfStore(assets).import_pdf(project.project_id, "authored.pdf", authored_pdf(), client=client)
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    app.button(key="nav_pdf_workflow").click().run()
    app.button(key=f"scene_{record.document_id}_scene-0001").click().run()
    assert not app.exception
    app.button(key="publish_pdf_scene").click().run()
    assert len(PdfStore(assets).library()) == 1
    app.button(key="nav_asset_management").click().run()
    assert any(tab.label == "PDF 需求场景" for tab in app.tabs)
    assert not app.exception
    next(button for button in app.button if button.label == "打开源文档").click().run()
    assert not app.exception
    assert app.session_state["selected_scene_key"] == (project.project_id, record.document_id, "scene-0001")
