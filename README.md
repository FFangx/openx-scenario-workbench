# OpenX Scenario Workbench

[English](README.en.md) | 中文

一个轻量、可公开复现的 ASAM OpenSCENARIO XML（`.xosc`）与 OpenDRIVE（`.xodr`）检查工具。它将场景中的参与者、动作、触发条件、位置和道路网络摘要整理为统一的结构化结果，并提供中文 / English 界面切换。

## 当前能力

- 同时导入 `.xosc` 和 `.xodr`
- 提取场景头信息、道路引用、参与者、动作、触发条件和位置
- 汇总道路、车道、路口、信号及静态对象数量
- 检查场景引用的道路文件是否与上传文件一致
- 在网页中查看摘要及可下载的 JSON
- 命令行解析，便于后续接入检索或 Agent 流程

这是一个有意保持较小的 MVP。它不承诺执行完整的 ASAM 标准验证，也不包含任何私有格式、公司资产或内部数据。

## 快速开始

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
streamlit run src/openx_workbench/app.py
```

命令行使用：

```bash
openx-inspect scenario.xosc road.xodr --language zh
```

## 获取公开示例

仓库不直接复制第三方场景。下面的命令会从 esmini 官方仓库下载公开示例，并保留其许可证文件：

```bash
python scripts/fetch_esmini_demo.py
```

下载内容位于 `examples/esmini/`，不会被 Git 跟踪。第三方许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 项目定位

当前版本主要用于“可解释地读取和检查 OpenX 场景”。后续可以在这个统一数据层上增加语义搜索、自然语言筛选、质量检查和 Agent 工具调用，而不需要把 UI、解析器与模型逻辑绑在一起。

## License

本项目代码采用 MIT License。下载的第三方示例遵循其各自许可证。
