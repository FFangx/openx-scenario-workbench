# 交接：React 工作台（阶段 1：静态复刻 comp-a）

## 目标
用 React 19 + Ant Design + Vite + TypeScript，把效果图 1:1 做成可交互前端。
- 效果图：`.impeccable/approved-target.png`（与 `.impeccable/mocks/comp-a.png` 为同一张），尺寸 1586×992
- 本阶段只用假数据：`web/src/data/mock.ts`，照抄效果图。不接后端，不碰 `src/openx_workbench` 下的任何存储
- 效果图是浅色模式；深色模式已经接好（设置 → Appearance），但以浅色为准对齐

## 现状
- `web/` 的代码已经写完（由云端会话完成），**但从未安装、构建或运行过**，一定会有需要修的地方
- 依赖写的是 antd ^6、@ant-design/icons ^6。如果某个 API 在 antd 6 里变了，以安装后的实际版本为准修改
- Streamlit 上限演示在 `prototypes/streamlit-ceiling/`，只作参考，不再继续

## 结构
- `src/App.tsx`：主题切换和全局状态（选中的场景、当前候选、勾选、搜索词、筛选）
- `src/components/TopBar.tsx`：顶部导航和步骤条
- `src/components/RequirementsPanel.tsx`：左栏（PDF 卡片、场景列表、原文证据）
- `src/components/SearchPanel.tsx`：中栏（搜索、筛选标签、候选表、资产预览）
- `src/components/DecisionPanel.tsx`：右栏（复用结论、选中项、阻断差异、事实匹配、追溯链接、导出）
- `src/theme.ts`：antd 主题 token；`src/styles.css`：自定义样式和 CSS 变量（含深色）
- `src/lib/illustrations.ts`：手画的 SVG 占位图（道路、车辆、PDF 页面）

## 步骤
1. `git switch -c feature/react-workbench`（未跟踪的 web/ 会一起带过去）
2. `cd web && npm install && npm run build`，修到 0 报错
3. `npm run dev`，用 Playwright 按 1586×992 视口截图，和效果图逐栏（左 / 中 / 右）并排对比，修改后重新截图，直到差异只剩字体渲染级别
4. 验收要点：
   - 整页一屏装下，不出现页面级滚动
   - 候选表行高约 48px，"Modify and reuse" 标签不被截断
   - 右侧 Key matched facts 每行单行显示
   - 点表格行，右侧结论和预览联动；点左侧场景，搜索词和原文证据联动
   - 筛选标签可删，可从 Filters 页加回；Show 下拉能过滤；导出能下载 JSON 和 CSV
   - 深色模式下不出现白底块或看不清的文字
5. 视觉通过后提交，再进入阶段 2：用 FastAPI 包装现有模块（`retrieval.py`、`reuse.py`、`project_store.py`、`pdf_store.py`），vite 已把 `/api` 代理到 127.0.0.1:8765

## 注意
- 不要自己发挥设计：以效果图为唯一标准，不要套用其他设计规范或审美类 skill
- 不要在界面上造假：接真实数据后，缺失的值（比如未生成的仿真帧）要做成明确的空状态
