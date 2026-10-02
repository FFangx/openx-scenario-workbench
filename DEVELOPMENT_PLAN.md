# Roadmap / 开发路线

## v0.1: scenario inspection / 场景检查

Implemented: bilingual web UI, CLI, shared structured representation, selected scenario-element extraction, road metadata, reference checks, JSON export, and a pinned public demo. The repository includes installation instructions, tests, and CI.

已实现：双语网页、CLI、统一结构化表示、部分场景元素提取、道路元数据、引用检查、JSON 导出和固定版本公开示例，并提供安装说明、测试与 CI。

## v0.2: evidence-to-reuse MVP / 证据到复用 MVP

Implemented locally: XOSC/XODR pairing, ScenarioManager-compatible `.sim` ingestion, road length/lane/geometry features, a dependency-free vector index, scenario and road reranking, reuse-level output, a responsive evidence-to-decision workbench, and the `openx-search` CLI.

本地已实现：XOSC/XODR 配对、ScenarioManager 兼容的 `.sim` 导入、道路长度/车道/几何特征、本地向量索引、场景与道路重排、复用等级、响应式证据到决策工作台和 `openx-search` CLI。

Implemented locally: a public typed `ScenePackage` contract, page/section/source evidence, migrated ScenarioManager V2 scene-first extraction/classification, structured retrieval queries, grounded scenario/road reuse differences, and an in-memory `.sim` adapter. No private PDF, customer configuration, or internal evaluation data is included.

本地新增：公开版强类型 `ScenePackage` 契约、页码/章节/原文证据、ScenarioManager V2 场景优先提取与分类、结构化检索查询、有依据的场景与道路复用差异，以及纯内存 `.sim` 适配器。仓库不包含私有 PDF、客户配置或内部评测数据。

Implemented locally: BGE-M3 semantic embeddings, shared name/structure recall, batched encoding and persistent content/classification fingerprints; immutable libraries and reports; real local esmini preview; native tables with verified cell spans and chapter-owned continuation, isolated PP-StructureV3 OCR and quality-gated PP-DocLayoutV2 native chapter rescue; offline version-specific XSD checks. See [reuse alignment](docs/REUSE_ALIGNMENT.md) and [PDF migration](docs/PDF_MIGRATION.md) for measured validation and limits. Next: broaden representative public-corpus evaluation, improve cross-page/merged-table handling, and extend semantic/event coverage.

本地新增：BGE-M3 语义向量、共用模型的名称与结构召回、批量编码和内容/分类指纹缓存；不可变资产库与报告；真实本机 esmini 预览；保留单元格合并关系与跨页章节归属的原生表格、独立 PP-StructureV3 OCR 与按质量门槛启动的 PP-DocLayoutV2 原生章节修复；离线版本专用 XSD 检查。实测和边界见[复用对齐](docs/REUSE_ALIGNMENT.md)与[PDF 迁移](docs/PDF_MIGRATION.md)。下一步扩展代表性公开语料评测、跨页/合并表格处理，以及语义与事件覆盖。

## Parser enrichment / 解析完善

- Implemented locally: lexical parameter aliases and bounded arithmetic, with
  declarations, resolution provenance and unresolved/dynamic-parameter review.
- Implemented locally: trigger attributes, XML paths and event/action ownership.
- Implemented locally: distinct review scopes and whole-PDF matching/reporting,
  sharing individual ranking, snapshots and version-pinned persistence.
- Implemented locally: shared standard gates for direct-reuse confirmation and
  saving; audited, separately checked SIM standard copies and diagnostic packages.
- Next: broader representative public scenarios and execution-aware event semantics.

本地已完成参数作用域、引用与有限算术、原始值与解析记录、事件归属及 XML 路径；
增加部分验证/无法判断状态和整份 PDF 匹配汇总，共用单场景决策和版本固定逻辑。
后续扩展公开样例覆盖与依赖实际执行的事件语义。详见[收口验证](docs/REUSE_ALIGNMENT.md)。

## Later: comparison and retrieval / 后续：比较与检索

- Compare two scene representations and highlight parameter differences.
- Add a lightweight event-tree or timeline view.
- Expose deterministic query interfaces before adding optional natural-language retrieval.

比较场景表示及参数差异，增加轻量事件树或时间线；先提供确定性查询接口，再考虑可选的自然语言检索。

Future work is listed here as planned work, not as current functionality. The focus remains a small, reproducible inspection tool; full simulation and complete standard coverage are separate projects.

以上后续功能尚未实现。项目保持小型、可复现的检查工具定位；完整仿真和全面标准支持不属于当前范围。
