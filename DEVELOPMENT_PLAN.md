# Roadmap / 开发路线

## v0.1: scenario inspection / 场景检查

Implemented: bilingual web UI, CLI, shared structured representation, selected scenario-element extraction, road metadata, reference checks, JSON export, and a pinned public demo. The repository includes installation instructions, tests, and CI.

已实现：双语网页、CLI、统一结构化表示、部分场景元素提取、道路元数据、引用检查、JSON 导出和固定版本公开示例，并提供安装说明、测试与 CI。

## v0.2 in progress: OpenX asset retrieval / OpenX 资产检索

Implemented locally: XOSC/XODR pairing, road length/lane/geometry features, a dependency-free vector index, scenario and road reranking, reuse-level output, web retrieval UI, and `openx-search` CLI.

本地已实现：XOSC/XODR 配对、道路长度/车道/几何特征、本地向量索引、场景与道路重排、复用等级、网页检索入口和 `openx-search` CLI。

Implemented locally: a public `ScenePackage` contract, page/section/source evidence, deterministic PDF scene-section extraction, structured retrieval queries, and grounded scenario/road reuse differences. No private PDF, `.sim` adapter, customer configuration, or internal evaluation data is included.

本地新增：公开版 `ScenePackage` 契约、页码/章节/原文证据、确定性 PDF 场景章节提取、结构化检索查询，以及有依据的场景与道路复用差异。仓库不包含私有 PDF、`.sim` 适配器、客户配置或内部评测数据。

Next: replace the baseline hashing encoder with an optional semantic embedding backend and persist the asset index; then validate the complete PDF-to-OpenX path against a small licensed public corpus.

下一步：增加可选语义向量后端和持久化资产索引，再用一组有明确许可的公开 PDF 与 OpenX 资产验证完整链路。

## Parser enrichment / 解析完善

- Preserve parameter declarations and resolve simple references.
- Retain trigger thresholds, entity references, and event/action ownership.
- Attach XML source paths to extracted fields.
- Expand regression coverage with a small, documented set of public scenarios.

保留参数声明并处理简单引用；补齐触发阈值、实体引用与事件/动作归属；增加 XML 来源路径；用一组有明确来源的公开场景扩展回归测试。

## Later: comparison and retrieval / 后续：比较与检索

- Compare two scene representations and highlight parameter differences.
- Add a lightweight event-tree or timeline view.
- Expose deterministic query interfaces before adding optional natural-language retrieval.

比较场景表示及参数差异，增加轻量事件树或时间线；先提供确定性查询接口，再考虑可选的自然语言检索。

Future work is listed here as planned work, not as current functionality. The focus remains a small, reproducible inspection tool; full simulation and complete standard coverage are separate projects.

以上后续功能尚未实现。项目保持小型、可复现的检查工具定位；完整仿真和全面标准支持不属于当前范围。
