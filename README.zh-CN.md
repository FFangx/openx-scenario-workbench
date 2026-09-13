# OpenX 场景工作台

[English](README.md) | 中文

将智驾/辅助驾驶要求转成可追溯的 OpenX 复用判断。本工具从 **PDF** 提取带页码和章节证据的场景包，构建 **OpenSCENARIO（`.xosc`）+ OpenDRIVE（`.xodr`）** 组合资产，并结合文本、场景结构和道路适配度排序。

**快速体验：**启动应用后点击“加载公开示例”，即可检查固定版本的 esmini cut-in 场景，无需 API Key、模型下载或自备文件。语言切换位于右上角。

![英文界面中的公开 cut-in 示例](docs/images/workbench-en.png)

## 当前能力

- 提取参与者、部分动作类型、动作所属参与者、触发条件类型和原始位置属性。
- 从文本型 PDF 提取候选场景章节，保留文件名、章节、页码范围和原文。
- 将 PDF 场景包转换为参与者、动作、触发器、道路和参数约束。
- 汇总道路 ID、车道元素、路口、信号和静态对象数量。
- 保留道路总长、车道类型数量和 OpenDRIVE 几何类型。
- 按 `LogicFile` 引用将 `.xosc` 与 `.xodr` 配对，构建 OpenX 组合资产。
- 用本地文本向量、场景结构和道路适配联合检索资产。
- 输出缺少参与者、动作、触发器或道路特征等有依据的复用差异。
- 检查道路文件名引用是否一致、场景是否缺少参与者、道路文件是否缺少 road 元素。
- 通过概览、参与者、动作、触发条件、道路网络、检查提示六个视图展示结果。
- 网页和 CLI 输出相同的结构化 JSON。
- 一键加载固定上游版本的 esmini 示例，便于复现。

当前 MVP 地基不运行仿真，也不执行完整的 ASAM Schema 或一致性认证。PDF OCR 与表格还原、参数表达式、外部 Catalog、XOSC 触发阈值和事件层级尚未完整支持。详见[架构与当前限制](docs/ARCHITECTURE.md)。

## 安装与启动

需要 **Python 3.10 或更新版本**。以下命令在仓库根目录运行。

```bash
git clone https://github.com/FFangx/openx-scenario-workbench.git
cd openx-scenario-workbench
python -m venv .venv
```

激活环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

安装并启动：

```bash
python -m pip install ".[dev]"
python -m streamlit run src/openx_workbench/app.py
```

打开 Streamlit 输出的本地地址。“公开示例”需要从 GitHub 下载两个文件；“上传文件”使用本地文件对。

## CLI 与离线示例

以下最小文件由本项目编写，供解析测试和离线检查使用，并非可直接运行的仿真场景：

```bash
openx-inspect tests/fixtures/minimal.xosc tests/fixtures/minimal.xodr
```

输出顶层字段为 `scenario`、`road`、`warnings`，可在[英文首页](README.md#cli-and-offline-sample)查看节选。标准输出只含 JSON，文字警告输出到标准错误流。检查完成时退出码为 0（可能包含警告）；输入无效时退出码为 2。

下载真实公开示例：

```bash
python scripts/fetch_esmini_demo.py
openx-inspect examples/esmini/cut-in.xosc examples/esmini/e6mini.xodr
```

固定示例当前可提取 **2 个参与者、6 个动作、5 个触发条件和 1 条道路**。这些是结构提取数量，不是仿真行为测量。文件下载到 Git 忽略的 `examples/esmini/`，并保留上游许可证。

构建并检索一个目录中的 OpenX 资产：

```bash
openx-search examples/esmini "目标车切入 SpeedAction 相对距离"
```

网页中的“资产检索”提供同一流程，并分别展示向量、场景结构和道路适配得分。也可以上传 ADAS PDF，选择提取出的场景章节，以其原文、结构化约束和来源证据直接发起检索。

## 设计与开发

修改 Python 源码后，用 `python -m pip install ".[dev]"` 重新安装。也可使用 `-e` 可编辑安装，但普通安装可避免部分 Windows 环境下含中文目录的可编辑路径编码问题。

解析器和统一数据表示独立于 Streamlit。网页和 CLI 共享输入校验及检查流程，后续检索或比较工具可直接消费结构化结果。

[架构说明](docs/ARCHITECTURE.md) · [开发路线](DEVELOPMENT_PLAN.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

运行测试：

```bash
python -m pytest -q
```

CI 在 Windows / Linux、Python 3.10 / 3.12 上测试并构建分发包。自动测试使用本地文件与模拟下载；真实公开示例单独验证。

## 许可证

代码与自行编写的测试文件采用 [MIT](LICENSE)。esmini 示例从固定上游版本按需下载，不纳入仓库；截图展示该示例的检查结果。来源和许可见[第三方说明](THIRD_PARTY_NOTICES.md)。
