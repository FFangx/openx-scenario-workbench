# OpenX 场景工作台

[English](README.md) | 中文

**Windows 桌面入口：**配置[桌面启动器](docs/DESKTOP_LAUNCHER.md)后，双击桌面 `OpenX` 即可启动服务并打开网页；双击 `OpenX - Stop` 或使用托盘菜单即可关闭服务和预览进程。

将智驾/辅助驾驶要求转成可追溯的 OpenX 复用判断。本工具从 **PDF** 提取带页码和章节证据的场景包，从独立文件或 ScenarioManager 兼容的 `.sim` 归档构建 **OpenSCENARIO（`.xosc`）+ OpenDRIVE（`.xodr`）** 组合资产，并结合文本、场景结构和道路适配度排序。

**快速体验：**启动应用后点击“加载公开示例”，即可检查固定版本的 esmini cut-in 场景，无需 API Key、模型下载或自备文件。语言切换位于右上角。

![证据、检索和复用判断三栏工作台](docs/images/workbench.png)

## 当前能力

- 提取参与者、部分动作类型、动作所属参与者、触发条件类型和原始位置属性。
- 使用迁移后的 ScenarioManager V2 / scene-first v6 路径识别、分类并提取文字版 PDF 场景，保留章节、页码、原文和复核提示；需先配置模型。
- 核对后的 PDF 场景修订可加入全局需求库；仿真资产支持模型分类、人工修正和分类审计历史。
- 设置中支持服务地址、API Key、获取模型清单、选择或手动输入模型名，以及所选模型的 JSON 可用性测试。
- 将 PDF 场景包转换为参与者、动作、触发器、道路和参数约束。
- 汇总道路 ID、车道元素、路口、信号和静态对象数量。
- 保留道路总长、车道类型数量和 OpenDRIVE 几何类型。
- 按 `LogicFile` 引用将 `.xosc` 与 `.xodr` 配对，构建 OpenX 组合资产。
- 导入 ScenarioManager 兼容的 `.sim` ZIP，将其中的 OpenSCENARIO JSON 转成统一解析输入，并用归档内或额外上传的 `.xodr` 完成道路配对。
- 可用轻量离线编码器或可选 BGE 语义向量，并结合场景结构和道路适配检索资产。
- 输出缺少参与者、动作、触发器或道路特征等有依据的复用差异。
- 检查道路文件名引用是否一致、场景是否缺少参与者、道路文件是否缺少 road 元素。
- 在一个响应式三栏工作台中串起 PDF 证据、资产检索和复用追溯。
- 网页可导出结构化决策追踪；检查与检索 CLI 复用同一套解析和检索核心。
- 一键加载固定上游版本的 esmini 示例，便于复现。
- 全局本机资产库保存不可变版本；命名项目可保存多份 PDF，并导出绑定资产版本的 JSON 与 HTML 决策。
- 可上传保留原始相对目录结构的 `.zip` 包，将 XOSC、XODR、Catalog、模型及纹理一起用于预览。
- 在 Windows 上由用户点击启动本机 esmini，在网页内显示真实运动画面。
- 配置模型密钥后，可按需用所选 PDF 原文和已解析的 OpenX 事实生成带证据编号的解释。

目前不执行完整的 ASAM Schema 或一致性认证。PDF OCR 与表格还原、参数表达式、外部 Catalog 的结构解析、XOSC 触发阈值和事件层级尚未完整支持。界面不会伪造媒体：PDF 缩略图来自上传文档，预览画面来自 esmini。模型解释虽附证据编号，事实准确性仍需人工核对。详见[本机资产与预览](docs/LOCAL_ASSETS_AND_PREVIEW.md)和[架构与当前限制](docs/ARCHITECTURE.md)。

模型配置与完整流程见 [PDF 迁移说明](docs/PDF_MIGRATION.md)。

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

打开 Streamlit 输出的本地地址。“公开示例”需要从 GitHub 下载两个文件；“上传资产”支持 `.sim`、`.xosc`、`.xodr` 和包含依赖的 `.zip`。只有在 `.sim` 内或额外上传文件中能找到所引用的道路时，该 case 才进入资产库；缺失道路会被明确列出，不会静默生成不完整资产。

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

工作台中栏提供同一流程，并展示向量、场景结构和道路适配证据。在左栏上传 ADAS PDF 并选择提取出的场景章节后，其原文、结构化约束和来源证据会直接形成检索查询；右栏解释复用等级、阻塞差异、所需修改和追溯关系。

启用语义检索并保存可复用索引：

```bash
python -m pip install ".[semantic]"
openx-search examples/esmini "目标车辆切入" --encoder bge --index .openx/index.json
```

BGE 模型会在首次使用时由 SentenceTransformers 下载。索引同时记录编码器和有序资产 ID，模型或资产库变化时不会静默复用旧向量。

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

代码与自行编写的测试文件采用 [MIT](LICENSE)。esmini 示例从固定上游版本按需下载，不纳入仓库。来源和许可见[第三方说明](THIRD_PARTY_NOTICES.md)。
