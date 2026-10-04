"""Functional navigation and workspace controls for the local workbench."""
import html
from pathlib import Path
from subprocess import TimeoutExpired

import streamlit as st

from .atomic_write import write_json
from .asset_store import AssetStore
from .esmini_preview import find_esmini
from .local_folders import choose_folder, open_folder
from .matching import known_encoder, read_preferences as preferences
from .pdf_store import PdfStore
from .project_store import ProjectStore


def save_preferences(**values):
    path = AssetStore().root / "preferences.json"
    data = {**preferences(), **values}
    write_json(path, data, ensure_ascii=False)


def initialize():
    prefs = preferences()
    st.session_state.setdefault("language", prefs.get("language", "中文"))
    st.session_state.setdefault("esmini_path", prefs.get("esmini_path", ""))
    st.session_state.setdefault("active_page", "home")
    st.session_state.setdefault("retrieval_encoder", known_encoder(prefs.get("encoder")))
    mode = prefs.get("appearance", "system")
    st.session_state.setdefault("appearance", mode if mode in {"light", "dark", "system"} else "system")


def set_appearance(mode):
    save_preferences(appearance=mode)
    st.session_state.appearance = mode


def toggle_language():
    label = "English" if st.session_state.language == "中文" else "中文"
    save_preferences(language=label)
    st.session_state.language = label


def _folder_location(path, language, *, key):
    st.markdown(f'<div class="ox-location">{html.escape(str(path))}</div>', unsafe_allow_html=True)
    if st.button("打开文件夹" if language == "zh" else "Open folder", key=key, icon=":material/folder_open:"):
        try:
            open_folder(Path(path))
        except OSError:
            st.error("无法打开此文件夹，请检查它是否仍然存在。" if language == "zh" else "Could not open this folder. Check that it still exists.")


def preview_settings(language, *, input_key="preview_esmini_folder", save_key="save_preview_settings"):
    """One setup flow shared by the selected asset and workspace settings."""
    zh = language == "zh"
    configured = st.session_state.get("esmini_path", "")
    detected = find_esmini(configured)
    if detected:
        st.success("仿真预览已就绪，已找到 esmini。" if zh else "Simulation preview ready. esmini was found.")
    else:
        st.info("尚未找到 esmini。已自动检查常用安装位置；如果已安装，请选择安装文件夹。" if zh else
                "esmini was not found in common installation locations. If installed, browse to its folder.")
    with st.expander("预览高级设置" if zh else "Advanced preview settings", expanded=detected is None):
        if detected:
            st.caption("安装位置" if zh else "Installation")
            _folder_location(detected.parent, language, key=f"{input_key}_open")
        browse, automatic = st.columns(2)
        with browse:
            if st.button("浏览安装文件夹" if zh else "Browse installation folder", key=save_key,
                         icon=":material/folder_open:", width="stretch"):
                try:
                    folder = choose_folder("选择 esmini 安装文件夹" if zh else "Select esmini installation folder",
                                           detected.parent if detected else Path.home())
                    if folder is not None:
                        resolved = find_esmini(str(folder))
                        if resolved is None:
                            st.error("此文件夹没有完整的 esmini。请选择含 esmini.exe 和 esminiLib.dll 的 bin 文件夹，或安装根目录。" if zh else
                                     "Choose the esmini installation or bin folder containing esmini.exe and esminiLib.dll.")
                        else:
                            save_preferences(esmini_path=str(resolved))
                            st.session_state.esmini_path = str(resolved)
                            st.rerun()
                except (OSError, ValueError, TimeoutExpired):
                    st.error("无法打开文件夹选择窗口，请在本机桌面使用工作台。" if zh else
                             "Could not open the folder browser. Use the workbench on this computer's desktop.")
        with automatic:
            if st.button("自动查找" if zh else "Detect automatically", key=f"{save_key}_detect",
                         icon=":material/search:", width="stretch"):
                save_preferences(esmini_path="")
                st.session_state.esmini_path = ""
                st.rerun()
    return detected


@st.dialog("OpenX · 工作区设置 / Workspace settings", width="large")
def settings(language):
    zh = language == "zh"
    st.caption("设置保存在本机，重启后仍然有效。" if zh else "Settings are saved on this computer.")
    model_tab, service_tab = st.tabs(["大模型" if zh else "Language model", "本机服务" if zh else "Local service"])
    with model_tab:
        from .model_ui import model_settings
        model_settings(language)
    with service_tab:
        preview_settings(language, input_key="settings_esmini", save_key="save_settings")
        st.write("数据位置" if zh else "Data location")
        _folder_location(AssetStore().root, language, key="open_data_folder")


@st.dialog("OpenX · 使用帮助 / Help")
def help_panel(language):
    if language == "zh":
        st.markdown("""### 从资产到报告
1. **资产管理**：导入 XOSC 与 XODR；带模型、目录等依赖时上传 ZIP。
2. **新建项目**：项目用于保存 PDF、场景修订和决策。资产库由所有项目共用。
3. **PDF 工作流**：上传规程，选择场景，核对原文和提取事实，再检索候选。
4. **播放仿真**：选择资产后直接播放。工具会自动查找，特殊安装位置可在预览高级设置中调整。
5. **保存复用决策**：报告固定当前场景修订和资产版本，可在总览重新下载。

文本检索只寻找相似资产，不作复用结论。模型解释需另行点击才会发送所列证据。

### 退出
关闭标签页不会停止服务。使用桌面 **OpenX - Stop** 或托盘的 **关闭 OpenX**。""")
    else:
        st.markdown("""### From assets to reports
1. **Asset management**: import paired XOSC/XODR files, or ZIP with dependencies.
2. **Create a project** for PDFs, scene revisions and decisions. Assets are shared globally.
3. **PDF workflow**: upload a protocol, select a scene, review the facts, then search.
4. **Play simulation** from the selected asset. Tools are detected automatically; use Advanced preview settings for a custom installation.
5. **Save decision** to pin the scene revision and asset version. Reopen reports in Overview.

Text search finds similar assets only. Model explanations send the listed evidence only when requested.

### Exit
Closing a tab leaves the service running. Use **OpenX - Stop** or the tray's exit command.""")


@st.dialog("OpenX · 源文件 / Source files", width="large")
def source_files(version, language):
    store = AssetStore()
    st.caption(f"{version.asset_id} · v{version.version_number} · {version.version_id}")
    st.caption("只读查看保存的版本。修改文件后，可在资产管理导入新版本。" if language == "zh" else
               "Read-only stored version. Import edited files in Asset management to create a new version.")
    for tab, kind, name in zip(st.tabs(["OpenSCENARIO", "OpenDRIVE"]),
                               ("scenario", "road"), (version.xosc_name, version.xodr_name)):
        with tab:
            data = store.file_bytes(version, kind)
            st.download_button("下载 " + Path(name).name if language == "zh" else "Download " + Path(name).name,
                               data, Path(name).name, "application/xml", key=f"source_{kind}")
            if len(data) <= 1_000_000:
                st.code(data.decode("utf-8", errors="replace"), language="xml", height=380)
            else:
                st.info("文件较大，请下载查看。" if language == "zh" else "Download this large file to inspect it.")


def workspace_navigation(tx):
    """Keep global navigation above the task, leaving the queue its full width."""
    language = "zh" if st.session_state.language == "中文" else "en"
    projects = ProjectStore()
    header_controls(language)
    with st.container(key="workspace_navigation"):
        columns = st.columns([1, 1.25, 1.45, 1.25, 1.7, 1.9, 1.2], vertical_alignment="center")
        for column, (page, symbol) in zip(columns, (("home", "space_dashboard"), ("text_search", "search"),
                                                   ("pdf_workflow", "description"), ("asset_management", "inventory_2"))):
            with column:
                st.button(tx(language, page), key=f"nav_{page}", icon=f":material/{symbol}:",
                          type="primary" if st.session_state.active_page == page else "tertiary",
                          width="stretch", on_click=lambda value=page: st.session_state.update(active_page=value))
        with columns[4]:
            st.markdown(f'<div class="ox-workspace-location" lang="{language}">' +
                        ("本机工作区" if language == "zh" else "Local workspace") + '</div>', unsafe_allow_html=True)
        project_list = projects.projects()
        with columns[5]:
            if project_list:
                ids = [item.project_id for item in project_list]
                if st.session_state.get("active_project_id") not in ids:
                    st.session_state.active_project_id = ids[-1]
                selected_id = st.selectbox("当前项目" if language == "zh" else "Current project", ids,
                                          format_func=lambda item: next(p.name for p in project_list if p.project_id == item),
                                          key="active_project_id", label_visibility="collapsed")
                if not projects.last() or projects.last().project_id != selected_id:
                    projects.set_last(selected_id)
            else:
                st.caption("尚无项目" if language == "zh" else "No projects")
        with columns[6]:
            with st.popover("新建项目" if language == "zh" else "New project", icon=":material/add:", width="stretch"):
                name = st.text_input("项目名称" if language == "zh" else "Project name", key="new_project_name")
                if st.button("创建项目" if language == "zh" else "Create project", key="create_project", type="primary"):
                    if not name.strip():
                        st.warning("请输入项目名称。" if language == "zh" else "Enter a project name.")
                    else:
                        project = projects.create(name)
                        st.session_state.project_to_select = project.project_id
                        st.rerun()
    return st.session_state.active_page


def header_controls(language):
    zh = language == "zh"
    project = next((p for p in ProjectStore().projects() if p.project_id == st.session_state.get("active_project_id")), None)
    with st.container(key="workspace_header"):
        context, files, history, help_col, settings_col, appearance, locale = st.columns([4, 1.2, 1.2, 1, 1, 1, .9])
        with context:
            st.markdown('<div class="ox-product-brand"><strong class="notranslate" translate="no">Open<span>X</span></strong><span>' +
                        ("场景工作台" if zh else "Scenario Workbench") + '</span></div>', unsafe_allow_html=True)
        with files:
            with st.popover("文件" if zh else "Files", icon=":material/folder_open:", use_container_width=True):
                documents = PdfStore().documents(project.project_id) if project else []
                if not documents:
                    st.caption("当前项目还没有 PDF。" if zh else "No PDFs in this project yet.")
                for document in documents:
                    st.download_button(document.filename, PdfStore().pdf_bytes(document), document.filename,
                                       "application/pdf", key=f"header_pdf_{document.document_id}")
        with history:
            with st.popover("记录" if zh else "History", icon=":material/history:", use_container_width=True):
                reports = ProjectStore().reports(project.project_id) if project else []
                if not reports:
                    st.caption("尚无已保存的决策。" if zh else "No saved decisions yet.")
                for report in reports[:5]:
                    st.write(report["trace"]["source"]["title"])
                    st.caption(report["saved_at"][:19])
                st.button("查看全部决策" if zh else "View all decisions", key="open_history",
                          on_click=lambda: st.session_state.update(active_page="home"))
        with help_col:
            if st.button("帮助" if zh else "Help", key="workspace_help", icon=":material/help_outline:", use_container_width=True):
                help_panel(language)
        with settings_col:
            if st.button("设置" if zh else "Settings", key="workspace_settings", icon=":material/settings:", use_container_width=True):
                settings(language)
        with appearance:
            mode = st.session_state.appearance
            symbols = {"light": "light_mode", "dark": "dark_mode", "system": "contrast"}
            with st.popover("外观" if zh else "Theme", icon=f":material/{symbols[mode]}:", use_container_width=True):
                st.caption("外观模式" if zh else "Appearance")
                for value, name in (("light", "亮色" if zh else "Light"),
                                    ("dark", "暗色" if zh else "Dark"),
                                    ("system", "跟随系统" if zh else "System")):
                    st.button(name, icon=f":material/{symbols[value]}:", key=f"theme_{value}",
                              type="primary" if mode == value else "secondary", use_container_width=True,
                              on_click=set_appearance, args=(value,))
                st.caption("跟随系统会自动响应系统外观变化。" if zh else "System mode updates automatically with your device.")
        with locale:
            st.button("EN" if zh else "中文", key="toggle_language", on_click=toggle_language,
                      icon=":material/translate:", help="Switch to English" if zh else "切换为中文", use_container_width=True)
