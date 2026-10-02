# OpenX 场景工作台

[English](README.md) | 中文

**Windows 桌面入口**：配置[桌面启动器](docs/DESKTOP_LAUNCHER.md)后，双击桌面 `OpenX` 即可启动服务并打开网页；双击 `OpenX - Stop` 或使用托盘菜单即可关闭服务和预览进程。

将智驾/辅助驾驶要求转成可追溯的 OpenX 复用判断。本工具从 **PDF** 提取带页码和章节证据的场景包，从独立文件或 ScenarioManager 兼容的 `.sim` 归档构建 **OpenSCENARIO（`.xosc`）+ OpenDRIVE（`.xodr`）** 组合资产，并结合文本、场景结构和道路适配度排序。

**快速体验**：启动应用后进入**资产管理 → 导入资产 → 公开示例 → 加载公开示例**，即可导入并检查固定版本的 esmini cut-in 场景，无需 API Key、模型下载或自备文件。语言切换位于右上角；语义检索和仿真预览的依赖见下文。

![当前 PDF 工作流：项目导航、已复核需求、候选资产与复用判断](docs/images/workbench.jpg)

*当前应用的真实运行截图，使用自行编写的 PDF 和解析测试资产，需求事实经人工复核；展示检索与判断流程，不作为模型提取或仿真执行示例。*

## 使用流程

| 页面或操作 | 用法 |
| --- | --- |
| **资产管理** | 导入 `.sim`、配对的 `.xosc` / `.xodr` 或依赖 `.zip`；点击一行查看分类、源文件、标准检查和版本历史。 |
| **播放仿真** | 选中资产后点击**播放仿真**。自动查找已安装的 Windows esmini；特殊位置在**预览高级设置**中调整。 |
| **文本检索** | 用 BGE-M3 寻找相似资产，此页面不作复用结论。 |
| **PDF 工作流** | 创建项目，在**设置**中配置模型，导入 PDF，选中场景并复核证据与事实，再检索候选。选中场景后进入证据、候选、判断三栏工作区。 |
| **整份 PDF 匹配与汇总** | 匹配当前文档全部场景，导出或保存绑定版本的 JSON/HTML 汇总。 |
| **总览** | 查看资产统计，重新打开已保存的项目报告。 |

资产版本在项目间共享；PDF 原文、场景修订和决策属于当前项目。

## 当前能力

- 提取参与者、部分动作类型、动作所属参与者、触发条件类型和原始位置属性。
- 使用迁移后的 ScenarioManager V2 / scene-first v6 路径识别、分类并提取文字或扫描 PDF 场景，保留表格单元格、章节、页码、原文和复核提示；扫描页需安装本机 OCR，提取前需配置语言模型。
- 核对后的 PDF 场景修订可加入全局需求库；仿真资产支持模型分类、人工修正和分类审计历史。
- 设置中支持服务地址、API Key、获取模型清单、选择或手动输入模型名，以及所选模型的 JSON 可用性测试。
- 将 PDF 场景包转换为参与者、动作、触发器、道路和参数约束。
- 汇总道路 ID、车道元素、路口、信号和静态对象数量。
- 保留道路总长、车道类型数量和 OpenDRIVE 几何类型。
- 按 `LogicFile` 引用将 `.xosc` 与 `.xodr` 配对，构建 OpenX 组合资产。
- 导入 ScenarioManager 兼容的 `.sim` ZIP，将其中的 OpenSCENARIO JSON 转成统一解析输入，并用归档内或额外上传的 `.xodr` 完成道路配对。
- 语义检索使用 BGE-M3；也可显式选择离线哈希基线，并结合场景结构和道路适配检索资产。
- 输出缺少参与者、动作、触发器或道路特征等有依据的复用差异。
- 检查道路文件名引用是否一致、场景是否缺少参与者、道路文件是否缺少 road 元素。
- 提供总览、文本检索、PDF 工作流和资产管理；选中 PDF 场景后进入证据、候选与复用追溯三栏工作区。
- 网页可导出结构化决策追踪；检查与检索 CLI 复用同一套解析和检索核心。
- 一键加载固定上游版本的 esmini 示例，便于复现。
- 全局本机资产库保存不可变版本；命名项目可保存多份 PDF，并导出绑定资产版本的 JSON 与 HTML 决策。
- 可上传保留原始相对目录结构的 `.zip` 包，将 XOSC、XODR、Catalog、模型及纹理一起用于预览。
- 在 Windows 上自动查找本机 esmini；点击“播放仿真”后在网页内显示真实画面，支持停止、重播并保留失败详情。
- 配置模型密钥后，可按需用所选 PDF 原文和已解析的 OpenX 事实生成带证据编号的解释。
- 直接复用确认要求场景与道路均通过 XSD 检查；保存单场景或批量决策时重新核对实际资产文件。
- 在**资产管理 → 来源**中生成有转换与校验记录的 SIM 标准副本；未通过检查时只提供诊断包，保留原文件和不支持的扩展内容。

安装本机 Schema 库后，可离线按文件声明的版本检查 XSD，并显示具体诊断；这不代表完整 ASAM 语义认证或仿真通过。原生表格与可选 PP-StructureV3 OCR 接入同一场景流程；跨页、合并单元格表格、图示、不支持的参数表达式、未解析的外部 Catalog 和事件层级仍需复核。界面不会伪造媒体：PDF 缩略图来自上传文档，预览画面来自 esmini。模型解释虽附证据编号，事实准确性仍需人工核对。详见[本机资产与预览](docs/LOCAL_ASSETS_AND_PREVIEW.md)和[架构与当前限制](docs/ARCHITECTURE.md)。

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

打开 Streamlit 输出的本地地址，在**资产管理 → 导入资产**选择公开示例或上传文件。公开示例从 GitHub 下载场景和道路；上传支持 `.sim`、`.xosc`、`.xodr` 和包含依赖的 `.zip`。只有在 `.sim` 内或额外上传文件中能找到所引用的道路时，该 case 才进入资产库；任务详情列出缺失道路文件名，补充后重新导入即可。

### 按需启用

- **BGE-M3 检索**：执行 `python -m pip install ".[semantic]"`。界面默认 BGE-M3，未缓存时首次使用下载权重，仓库不自带模型；无权重的离线检查需显式选择哈希基线。
- **PDF 提取**：在**设置**中配置服务地址、密钥和模型。导入会将文档文字发送给该服务；扫描 PDF 还需按 [PDF 迁移说明](docs/PDF_MIGRATION.md)安装并配置本机 OCR。
- **标准检查**：先执行 `openx-validate --install-schemas` 下载固定版本的 Schema 库，之后可本机检查。场景和道路都通过检查后，才能确认直接复用。
- **仿真预览**：在 Windows 上单独安装 esmini。自动检测支持 `OPENX_ESMINI_PATH`、PATH 和 `%LOCALAPPDATA%/OpenXScenarioWorkbench/tools/esmini`；自定义设置可填安装目录、`bin` 目录或 `esmini.exe`。仓库不自带 esmini，部分扩展或缺少依赖会导致无法播放。
- **Windows 桌面入口**：按[桌面启动器说明](docs/DESKTOP_LAUNCHER.md)配置快捷方式和托盘，日常使用无需终端。

## CLI 与离线示例

以下最小文件由本项目编写，供解析测试和离线检查使用，并非可直接运行的仿真场景：

```bash
openx-inspect tests/fixtures/minimal.xosc tests/fixtures/minimal.xodr
```

输出顶层字段为 `scenario`、`road`、`warnings`、`validation`，可在[英文首页](README.md#cli-and-offline-sample)查看节选；`validation` 保存按版本检查的 XSD 结果。标准输出只含 JSON，文字警告输出到标准错误流。解析成功时退出码为 0，包括带警告或 XSD 无效、不可用的结果；输入无效或解析失败时退出码为 2。需要退出码反映 XSD 有效性时，使用 `openx-validate`。

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

**文本检索**使用同一检索核心。基于需求作判断时，进入 **PDF 工作流**，选中已导入的场景并复核事实；其原文、结构化约束和来源证据形成检索查询，候选与判断栏展示匹配依据、阻塞差异、所需修改和追溯关系。

启用语义检索并保存可复用索引：

```bash
python -m pip install ".[semantic]"
openx-search examples/esmini "目标车辆切入" --encoder bge --index .openx/index.json
```

工作台的 PDF 与文本检索默认使用 BGE-M3；显式选择本地哈希基线后，设置会保留。
PDF 工作流中的“整份 PDF 匹配与汇总”可一次匹配本文档全部场景，导出 JSON/HTML，
并保存含来源修订、候选资产版本和待复核状态的快照。总览可重新打开已保存报告。

语义模型固定为 BAAI/bge-m3，不会自动换成小模型。首次使用时由 SentenceTransformers 下载。索引记录编码器、资产内容和已确认分类的指纹；模型、分类或资产库变化时不会静默复用旧向量。

## 设计与开发

修改 Python 源码后，用 `python -m pip install ".[dev]"` 重新安装。也可使用 `-e` 可编辑安装，但普通安装可避免部分 Windows 环境下含中文目录的可编辑路径编码问题。

解析器和统一数据表示独立于 Streamlit。网页和 CLI 共享输入校验及检查流程，后续检索或比较工具可直接消费结构化结果。

![OpenX 工作台架构：BGE-M3、结构比较、标准确认与四类判断](docs/images/architecture-overview.svg)

[架构说明](docs/ARCHITECTURE.md) · [开发路线](DEVELOPMENT_PLAN.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

运行测试：

```bash
python -m pytest -q
```

CI 在 Windows / Linux、Python 3.10 / 3.12 上测试并构建分发包。自动测试使用本地文件与模拟下载；真实公开示例单独验证。

## 许可证

代码与自行编写的测试文件采用 [MIT](LICENSE)。esmini 示例从固定上游版本按需下载，不纳入仓库。来源和许可见[第三方说明](THIRD_PARTY_NOTICES.md)。
