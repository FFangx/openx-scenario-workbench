# Roadmap / 开发路线

## v0.1: scenario inspection / 场景检查

Implemented: bilingual web UI, CLI, shared structured representation, selected scenario-element extraction, road metadata, reference checks, JSON export, and a pinned public demo. The repository includes installation instructions, tests, and CI.

已实现：双语网页、CLI、统一结构化表示、部分场景元素提取、道路元数据、引用检查、JSON 导出和固定版本公开示例，并提供安装说明、测试与 CI。

## Next: richer structure / 下一步：完善结构

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
