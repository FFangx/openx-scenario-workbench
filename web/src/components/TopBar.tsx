import { Fragment, useEffect, useState } from "react";
import { App, Button, Dropdown, Empty, Form, Input, Modal, Popover, Tooltip, type MenuProps } from "antd";
import {
  CheckOutlined,
  DownloadOutlined,
  DownOutlined,
  FolderOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { api, urls, type Lang, type PdfDocument, type Project } from "../api";
import { useT } from "../i18n";

export type Page = "workbench" | "overview" | "assets";

interface TopBarProps {
  page: Page;
  onPage: (p: Page) => void;
  onLang: (l: Lang) => void;
  projects: Project[];
  projectId: string | null;
  onProject: (id: string) => void;
  onCreated: (p: Project) => void;
  onHelp: () => void;
  onSettings: () => void;
  /** Back to the workbench start page. */
  onHome: () => void;
}

const check = (on: boolean) => (on ? <CheckOutlined /> : <span style={{ width: 14 }} />);

export function TopBar({ page, onPage, onLang, projects, projectId, onProject, onCreated, onHelp, onSettings, onHome }: TopBarProps) {
  const { t, lang } = useT();
  const [creating, setCreating] = useState(false);
  const project = projects.find((p) => p.project_id === projectId);

  const projectMenu: MenuProps = {
    items: [
      ...projects.map((p) => ({ key: p.project_id, label: p.name, icon: check(p.project_id === projectId) })),
      ...(projects.length ? [{ type: "divider" as const }] : []),
      { key: "__new", label: t("新建项目…", "New project…"), icon: <PlusOutlined /> },
    ],
    onClick: ({ key }) => (key === "__new" ? setCreating(true) : onProject(key)),
  };

  const pages: [Page, string][] = [
    ["workbench", t("工作台", "Workbench")],
    ["overview", t("总览", "Overview")],
    ["assets", t("资产管理", "Asset management")],
  ];

  return (
    <header className="ox-top">
      <button className="ox-home" onClick={onHome} aria-label={t("回到起始页", "Back to start")}>
        <span className="ox-brand" translate="no">
          Open<b>X</b>
        </span>
        <span className="ox-app">{t("场景工作台", "Scenario Workbench")}</span>
      </button>
      <span className="ox-sep" />
      <nav className="ox-nav" aria-label={t("页面", "Pages")}>
        {pages.map(([key, label]) => (
          <button key={key} className={page === key ? "on" : ""} aria-current={page === key ? "page" : undefined} onClick={() => onPage(key)}>
            {label}
          </button>
        ))}
      </nav>
      <div className="right">
        <Dropdown menu={projectMenu} trigger={["click"]}>
          <button className="hbtn">
            {t("项目", "Project")} <b>{project?.name ?? t("尚无项目", "None yet")}</b> <DownOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <Tooltip title={t("数据只保存在本机", "Data is stored on this computer")}>
          <span className="hbtn">
            {t("工作区", "Workspace")} <b>{t("本机", "Local")}</b>
          </span>
        </Tooltip>
        <span className="ox-sep" />
        <Tooltip title={t("使用帮助", "Help")}>
          <button className="hicon" aria-label={t("使用帮助", "Help")} onClick={onHelp}>
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
        <Tooltip title={t("设置", "Settings")}>
          <button className="hicon" aria-label={t("设置", "Settings")} onClick={onSettings}>
            <SettingOutlined />
          </button>
        </Tooltip>
        <span className="ox-sep" />
        <span className="lang">
          <button className={lang === "en" ? "on" : ""} onClick={() => onLang("en")}>EN</button>
          <button className={lang === "zh" ? "on" : ""} onClick={() => onLang("zh")}>中文</button>
        </span>
      </div>
      <NewProject open={creating} onClose={() => setCreating(false)} onCreated={onCreated} />
    </header>
  );
}

function NewProject({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (p: Project) => void }) {
  const { t } = useT();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ name: string }>();
  const [busy, setBusy] = useState(false);

  const submit = async ({ name }: { name: string }) => {
    setBusy(true);
    try {
      const project = await api.createProject(name.trim());
      form.resetFields();
      onCreated(project);
      onClose();
      message.success(t(`已创建项目“${project.name}”`, `Created project “${project.name}”`));
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("新建项目", "New project")}
      open={open}
      onCancel={onClose}
      okText={t("创建项目", "Create project")}
      onOk={() => form.submit()}
      confirmLoading={busy}
      destroyOnHidden
    >
      <p className="muted">{t("项目保存 PDF 及需求事实修订；资产库与复用评估结论由所有项目共用。", "A project keeps PDFs and fact revisions. The asset library and the reuse conclusions are shared by all projects.")}</p>
      <Form form={form} layout="vertical" onFinish={submit} preserve={false}>
        <Form.Item
          name="name"
          label={t("项目名称", "Project name")}
          rules={[{ required: true, whitespace: true, message: t("请输入项目名称", "Enter a project name") }, { max: 120 }]}
        >
          <Input autoFocus maxLength={120} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

interface StepBarProps {
  /** The step in progress; earlier steps show as done. */
  active: number;
  projectId: string | null;
  docs: PdfDocument[];
  /** PDFs shown now, marked in the project files list. */
  current: string[];
  onDoc: (id: string) => void;
}

/** Where the PDF's reuse assessment stands: imported, suggested by the model, confirmed, exported. */
export function StepBar({ active, projectId, docs, current, onDoc }: StepBarProps) {
  const { t } = useT();
  // Links start empty and fill up to the active step after the first paint, so entering the workflow animates them.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  const steps = [t("导入 PDF", "Import PDF"), t("生成复用建议", "Generate suggestions"), t("确认复用结论", "Confirm reuse"), t("导出评估表", "Export assessment")];

  const files = docs.length ? (
    <div className="pop-list">
      {docs.map((d) => (
        <div key={d.document_id} className={`file-row${current.includes(d.document_id) ? " on" : ""}`}>
          <button onClick={() => onDoc(d.document_id)}>
            <b>{d.filename}</b>
            <span>
              {t(`${d.page_count} 页 · ${d.scene_count} 个场景 · 导入于 ${d.imported_at.slice(0, 10)}`,
                `${d.page_count} pages · ${d.scene_count} scenes · imported ${d.imported_at.slice(0, 10)}`)}
            </span>
          </button>
          {projectId && (
            <Tooltip title={t("下载 PDF", "Download PDF")}>
              <Button type="text" size="small" icon={<DownloadOutlined />} href={urls.pdf(projectId, d.document_id)} download={d.filename}
                aria-label={t("下载 PDF", "Download PDF")} />
            </Tooltip>
          )}
        </div>
      ))}
    </div>
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("当前项目还没有 PDF", "No PDFs in this project yet")} />
  );

  return (
    <nav className="ox-steps">
      {steps.map((s, i) => (
        <Fragment key={i}>
          {i > 0 && <span className={`ox-step-link${i <= active && filled ? " done" : ""}`} style={{ "--i": i } as React.CSSProperties}><i /></span>}
          <span className={`ox-step${i === active ? " on" : i < active ? " done" : ""}`}>
            <span className="n">{i < active ? <CheckOutlined /> : i + 1}</span>
            {s}
          </span>
        </Fragment>
      ))}
      <div className="tools">
        <Popover title={t("项目文件", "Project files")} content={files} trigger="click" placement="bottomRight">
          <button>
            <FolderOutlined /> {t("项目文件", "Project files")}
          </button>
        </Popover>
      </div>
    </nav>
  );
}
