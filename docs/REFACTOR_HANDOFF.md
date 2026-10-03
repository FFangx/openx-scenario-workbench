# 交接：后端去重重构（4 步）

## 背景
- 分支 `feature/react-workbench`。React 工作台（`web/`）已接真实数据，后端是 `src/openx_workbench/api.py`；桌面启动器默认打开它，Streamlit 版（`app.py`）作为"经典工作台"保留，负责导入和仿真预览。
- 产品约束：**没有账号系统**（不加头像、登录、用户菜单、鉴权）；界面不造假，缺失数据显示为空状态。

## 目标
只去重、理清职责，**不改任何行为**：存储格式、检索排序、复用结论、API 返回字段、界面都保持不变。

### 第 1 步：抽共享服务层（优先，修掉 api.py 带来的重复）
`api.py` 抄了 `app.py` 的几段非界面逻辑，现在两份实现并存：
- 检索索引缓存：`app.py` `_index_for`（约 157 行）与 `api.py` `_index`（约 71 行）——同一路径规则 `indexes/<encoder>/<fingerprint[:24]>.json`、同一加载失败后重建的逻辑
- 编码器缓存：`app.py` `_encoder` 与 `api.py` `_encoder`
- 偏好读取：`ui_shell.py` `preferences()` 与 `api.py` `_preferred_encoder`（旧偏好文件存的是显示文字，两边都把非 `bge`/`hashing` 的值当 `bge`）
- "按场景检索"：`app.py` `_asset_panel` 里 `scene_package_to_query` + 追加关键词 + `search`，与 `api.py` `_run`
- 带出处的评估记录：`app.py` `_trace` 与 `api.py` `_trace_for`（都给 `build_trace` 拼 document_id / pdf_sha256 / scene_id / revision）

做法：新建一个不依赖 Streamlit 的模块（例如 `matching.py`），放这几件事；`app.py` 只保留 `st.session_state` / `st.cache_resource` 这层薄包装，`api.py` 直接调用。注意 `ui_shell.py` 导入了 streamlit，新模块不能从它导入。

### 第 2 步：机械去重
- 原子写 JSON/bytes（临时文件 + `replace`）在 10 个模块各写一遍：`asset_store`、`llm_service`、`ocr_setup`、`pdf_extraction`、`pdf_ocr`、`pdf_store`、`preview_frames`、`project_store`、`schema_validation`、`ui_shell`。收成一个公共函数；各处的 `ensure_ascii`、`indent`、`newline` 参数要逐一对齐，不能改变写出的字节。
- `pdf_store.py` 读取场景修订的代码重复 3 次（`scenes`、`revisions`、`revise_scene` 里 `EvidenceRef(**item)` 重建）。
- `parser.py` 与 `road_geometry.py` 各有一份 `_local`、`_float`（`_float` 的默认值不同，合并时保留差异）。

### 第 3 步：拆 `reuse.py`（1068 行）
把约 300 行几何辅助函数（`_bearing`、`_relative_facing`、`_heading_on_road`、`_relative_offset`、`_road_coordinates`、`_lane_position_fallback`、`_adjacent_lane` 等，约 600–910 行一带）**原样**搬到独立模块（例如 `reuse_geometry.py`），`reuse.py` 改为导入。只搬位置，不改逻辑；`tests/test_structured_reuse.py` 等测试必须原样通过。

### 第 4 步：按页面拆 `app.py`（1519 行）
用户已确认要做。第 1 步把业务逻辑搬走后，再把 Streamlit 界面按页面拆成一个子包（例如 `ui/`：PDF 场景库与需求编辑、资产面板与预览、复用评估面板、导入进度、文本检索页、资产管理页），`app.py` 只留入口、页面路由和共用的小部件。注意：
- `launcher.py` 用 `streamlit run app.py` 启动，入口文件路径不能变
- `st.session_state` 的键名不要改，否则用户已打开的会话会丢状态
- 超长函数（`_pdf_scene_library` 168 行、`_decision_panel` 119 行、`_import_progress` 111 行、`_asset_panel` 101 行）拆分时保持界面输出不变
- 拆完用经典工作台手动走一遍：选场景 → 检索 → 评估 → 下载评估数据（不要在真实数据上点保存）

## 验证（每步做完都跑）
1. `.venv\Scripts\python.exe -m pytest -q` —— 当前基线 262 passed
   第 4 步还要实际打开 Streamlit 版检查（例如 `streamlit run src/openx_workbench/app.py`，再用 Playwright 截图对比拆分前后）
2. 启动后端和前端：`$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m openx_workbench.api`，另开 `cd web; npm run dev`
3. `cd web; npm run verify:ui` —— 17 项界面交互检查，只读，不会点保存，可以对真实数据跑
4. 需要截图时：`$env:LIVE=1; npm run screenshot -- <名字>`，输出在 `web/.verify-out/`
5. 写入路径（保存决策）由 `tests/test_api.py` 用临时数据覆盖；不要对 `%LOCALAPPDATA%\OpenXScenarioWorkbench` 里的真实数据做写入测试
