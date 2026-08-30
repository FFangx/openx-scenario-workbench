# Development Plan / 后续开发大纲

[中文](#中文) | [English](#english)

## 中文

### 1. 项目目标

将当前 MVP 发展为一个可公开展示、可复现的 OpenX 场景检查与检索工具：读取 OpenSCENARIO XML 和 OpenDRIVE，生成统一场景表示，提供可解释的规则检查，并为后续自然语言检索与 Agent 工具调用准备稳定接口。

项目应保持轻量。优先完成能在毕业论文申请和作品集演示中直接体现价值的功能，不追求一次覆盖完整标准或实现仿真器。

### 2. 当前状态（2026-08-30）

- 独立私人仓库与全新 Git 历史
- Streamlit 双语界面，语言选择位于页面右上角
- 支持上传 `.xosc` 与 `.xodr`
- 提取场景头、道路引用、参与者、动作、触发条件和位置
- 汇总道路、车道、路口、信号和静态对象
- 检查道路文件名引用是否一致
- 支持 JSON 下载和命令行解析
- 提供 esmini 官方公开示例下载脚本与第三方许可说明
- 4 项自动测试通过

### 3. 不可突破的边界

- 不复制旧仓库的 Git 历史
- 不提交公司资产、内部数据、客户或供应商信息
- 不引入私有文件格式、内部字段名称或由内部资产衍生的结果
- 只迁移本人拥有著作权的通用算法、架构思路和 UI 逻辑
- 第三方场景、代码和素材必须保留来源与许可证
- 中文和 English 必须同步维护；语言切换不得占据独立页面或主导航项

### 4. 开发阶段

#### Phase 1 — 完成可演示的核心流程（最高优先级）

- 在界面中增加“使用公开示例 / Load public demo”入口，避免用户手工制作场景
- 明确显示已上传文件、标准版本和引用关系
- 将结果拆分为概览、参与者、动作、触发条件、道路网络和检查提示
- 为 XML 错误、缺失文件、错误扩展名和引用不一致提供双语错误信息
- 保留原始结构化 JSON 下载
- 补充界面级测试或最小启动测试

验收标准：首次访问者无需阅读代码，能在两分钟内加载公开示例并理解该场景的主要参与者、行为和道路信息。

#### Phase 2 — 提升解析与质量检查

- 识别参数声明及参数引用，区分数值和表达式
- 支持 CatalogReference、Controller、Environment 与 Routing 等常用结构
- 改善 ManeuverGroup、Actor 和 Action 的归属关系
- 对触发条件保留 entity reference、rule、threshold 和 duration 等关键字段
- 建立来源位置或 evidence 字段，让每个摘要可追溯到 XML 元素
- 增加确定性 QA：缺少 Ego、空 Storyboard、无触发器、道路引用缺失等
- 用多个公开场景建立回归测试集

验收标准：对选定公开样例的关键元素提取稳定，错误与警告具有明确证据，不把规则检查描述成完整标准认证。

#### Phase 3 — 可视化与比较

- 绘制轻量道路几何预览；不实现完整仿真渲染
- 用时间线或事件树呈现 Story → Act → ManeuverGroup → Event → Action
- 高亮参与者初始位置和动作归属
- 支持两个场景摘要的结构化比较

验收标准：截图或短视频能清楚展示“文件输入 → 场景理解 → 问题定位”的完整流程。

#### Phase 4 — AI / Agent 能力

- 先实现本地、确定性的场景筛选接口，再接入模型
- 支持自然语言查询，例如筛选 cut-in、特定速度区间或特定触发条件
- 将解析、筛选、QA 和比较封装为小型工具接口
- 模型输出必须引用结构化字段或 XML 证据
- 模型不可用时，基础解析和规则检查仍须工作

验收标准：Agent 负责组合工具和解释结果，而不是替代解析器或虚构场景事实。

#### Phase 5 — 公开发布准备

- 检查仓库历史、文件和演示视频中的敏感信息
- 完善架构图、截图、示例输出和限制说明
- 增加 CI：测试、格式检查和敏感关键词检查
- 确认第三方许可证及演示素材归属
- 在最终检查后再将仓库从 Private 改为 Public

### 5. 建议的下一次开发任务

下一次 session 只做 Phase 1，不开始 Agent 或复杂道路渲染：

1. 阅读本文件、`README.md`、`src/openx_workbench/app.py` 和 `parser.py`。
2. 设计无需手工制作场景的公开示例加载流程。
3. 重构结果页面的信息层级，同时维持右上角语言切换。
4. 为新增流程增加测试并运行全部测试。
5. 扫描敏感信息，记录结果；未经明确要求不要把仓库改为 Public。

### 6. 新 session 可直接使用的提示词

> 继续开发 `FFangx/openx-scenario-workbench`。先阅读 `DEVELOPMENT_PLAN.md` 和 README，检查当前 Git 状态。只完成 Phase 1：加入无需手工制作场景的公开示例加载流程，改善双语结果页和错误提示，补充测试。保留右上角语言切换，不修改旧项目，不引入任何公司资产、内部数据或私有格式，也不要开始 Agent、完整仿真或复杂道路渲染。完成后运行全部测试和敏感信息扫描，汇报变更；未经我明确要求不要将仓库改为 Public。

---

## English

### Objective

Turn the MVP into a reproducible, portfolio-ready OpenX scenario inspection and retrieval tool. It should parse OpenSCENARIO XML and OpenDRIVE, produce a shared scenario representation, run explainable deterministic checks, and expose stable interfaces for later natural-language retrieval and agent tooling.

Keep the project focused. Features that improve thesis applications and demonstrations take priority over complete standard coverage or simulator development.

### Roadmap

1. **Demo-ready workflow:** load a licensed public example without hand-authoring a scenario, improve bilingual result hierarchy and error handling, and retain JSON export.
2. **Parsing and QA:** resolve parameters, improve actor/action ownership, retain condition details and evidence, and build a public regression corpus.
3. **Visualization and comparison:** add a lightweight road preview, event timeline, actor positioning, and structured scenario comparison.
4. **AI and agent layer:** build deterministic query tools first, then add evidence-grounded natural-language retrieval and tool orchestration.
5. **Public release:** audit history and media, add CI and architecture documentation, verify licenses, and only then change repository visibility.

The constraints and acceptance criteria in the Chinese section are normative and must be followed during implementation.
