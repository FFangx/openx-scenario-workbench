import { Modal } from "antd";
import { useT } from "../i18n";

export function HelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { lang, t } = useT();
  return (
    <Modal title={t("使用帮助", "Help")} open={open} onCancel={onClose} footer={null} width={600}>
      {lang === "zh" ? (
        <div className="help">
          <h4>从资产到报告</h4>
          <ol>
            <li><b>资产管理</b>：导入 XOSC 与 XODR；带模型、目录等依赖时上传 ZIP。.sim 场景包会展开为多个资产。</li>
            <li><b>新建项目</b>：项目保存 PDF 及需求事实修订。资产库与复用评估结论由所有项目共用。</li>
            <li><b>导入 PDF</b>：提取其中的测试条款，打开后即为该 PDF 的条款复用评估。</li>
            <li><b>生成复用建议</b>：模型对每个条款独立评估 3 次，按直接复用、修改复用、不适用、无法判断四档推荐首选复用素材及修改内容；3 次一致的标为“一致”，否则标为“不一致”。</li>
            <li><b>确认复用结论</b>：先批量采纳一致的“直接复用”建议，再逐条复核不一致的条款；人工确认的结论带绿色对勾，可改为其他档位；无合适素材时使用“手动检索”。</li>
            <li><b>导出评估表</b>：CSV（可用 Excel 打开）或网页。</li>
          </ol>
          <p>播放仿真：esmini 会自动查找，特殊安装位置可在设置 → 本机服务中选择。</p>
          <h4>退出</h4>
          <p>关闭标签页不会停止服务。使用桌面 <b>OpenX - Stop</b> 或托盘的 <b>关闭 OpenX</b>。</p>
        </div>
      ) : (
        <div className="help">
          <h4>From assets to reports</h4>
          <ol>
            <li><b>Asset management</b>: import paired XOSC/XODR files, or a ZIP with dependencies. A .sim package expands into several assets.</li>
            <li><b>Create a project</b> for PDFs and fact revisions. The asset library and the reuse conclusions are shared by all projects.</li>
            <li><b>Import a PDF</b>: its test clauses are extracted, and opening it shows the clause reuse assessment.</li>
            <li><b>Generate suggestions</b>: the model assesses every clause three times independently and recommends a preferred asset on four levels (direct reuse, modify and reuse, not applicable, undetermined) with the changes needed; the same result all three times is “Consistent”, otherwise “Inconsistent”.</li>
            <li><b>Confirm reuse</b>: adopt the consistent “direct reuse” suggestions at once, then review the inconsistent clauses one by one; a person's conclusion carries a green check mark and may take another level; when no asset fits, search manually.</li>
            <li><b>Export the assessment</b> as CSV (opens in Excel) or as a web page.</li>
          </ol>
          <p>Playing a simulation: esmini is detected automatically; choose a custom installation under Settings → Local service.</p>
          <h4>Exit</h4>
          <p>Closing the tab leaves the service running. Use <b>OpenX - Stop</b> on the desktop or the tray's exit command.</p>
        </div>
      )}
    </Modal>
  );
}
