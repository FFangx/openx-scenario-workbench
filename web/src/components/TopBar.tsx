import { Fragment, useState } from "react";
import { App, Dropdown, Empty, Popover, Tooltip, type MenuProps } from "antd";
import {
  CheckOutlined,
  DownOutlined,
  FolderOutlined,
  HistoryOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { api, LEVEL, type Lang, type PdfDocument, type Project, type Report } from "../api";

export type Appearance = "light" | "dark" | "system";

interface TopBarProps {
  appearance: Appearance;
  onAppearance: (a: Appearance) => void;
  lang: Lang;
  onLang: (l: Lang) => void;
  projects: Project[];
  projectId: string | null;
  onProject: (id: string) => void;
}

const check = (on: boolean) => (on ? <CheckOutlined /> : <span style={{ width: 14 }} />);

export function TopBar({ appearance, onAppearance, lang, onLang, projects, projectId, onProject }: TopBarProps) {
  const { message } = App.useApp();
  const project = projects.find((p) => p.project_id === projectId);

  const projectMenu: MenuProps = {
    items: projects.map((p) => ({ key: p.project_id, label: p.name, icon: check(p.project_id === projectId) })),
    onClick: ({ key }) => onProject(key),
  };

  const settings: MenuProps = {
    items: [
      {
        key: "appearance",
        type: "group",
        label: "Appearance",
        children: (["light", "dark", "system"] as const).map((a) => ({
          key: a,
          label: { light: "Light", dark: "Dark", system: "Follow system" }[a],
          icon: check(a === appearance),
        })),
      },
    ],
    onClick: ({ key }) => onAppearance(key as Appearance),
  };

  return (
    <header className="ox-top">
      <span className="ox-brand">
        Open<b>X</b>
      </span>
      <span className="ox-app">Scenario Workbench</span>
      <span className="ox-sep" />
      <span className="ox-tagline">From requirements to reusable scenarios</span>
      <div className="right">
        <Dropdown menu={projectMenu} trigger={["click"]} disabled={!projects.length}>
          <button className="hbtn">
            Project <b>{project?.name ?? "—"}</b> <DownOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <Tooltip title="Data is stored on this machine">
          <span className="hbtn">
            Workspace <b>Local</b>
          </span>
        </Tooltip>
        <span className="ox-sep" />
        <Tooltip title="Help">
          <button
            className="hicon"
            aria-label="Help"
            onClick={() =>
              message.info("Pick a requirement scene on the left. Candidates are ranked by blocking differences, then change cost, then similarity.")
            }
          >
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
        <Dropdown menu={settings} trigger={["click"]} placement="bottomRight">
          <button className="hicon" aria-label="Settings">
            <SettingOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <span className="lang">
          <button className={lang === "en" ? "on" : ""} onClick={() => onLang("en")}>EN</button>
          <Tooltip title="Shows assessment vocabulary in Chinese">
            <button className={lang === "zh" ? "on" : ""} onClick={() => onLang("zh")}>中文</button>
          </Tooltip>
        </span>
      </div>
    </header>
  );
}

const STEPS = ["Extract from PDF", "Search asset library", "Assess reuse", "Export & trace"];

interface StepBarProps {
  active: number;
  projectId: string | null;
  docs: PdfDocument[];
  docId: string | null;
  onDoc: (id: string) => void;
}

export function StepBar({ active, projectId, docs, docId, onDoc }: StepBarProps) {
  const [reports, setReports] = useState<Report[] | null>(null);
  const loadReports = (open: boolean) => {
    if (open && projectId) api.reports(projectId).then(setReports).catch(() => setReports([]));
  };

  const files = docs.length ? (
    <div className="pop-list">
      {docs.map((d) => (
        <button key={d.document_id} className={d.document_id === docId ? "on" : ""} onClick={() => onDoc(d.document_id)}>
          <b>{d.filename}</b>
          <span>
            {d.page_count} pages · {d.scene_count} scenes · imported {d.imported_at.slice(0, 10)}
          </span>
        </button>
      ))}
    </div>
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No PDFs imported in this project" />
  );

  const activity =
    reports === null ? (
      <div className="muted">Loading…</div>
    ) : reports.length ? (
      <div className="pop-list">
        {reports.slice(0, 12).map((r) => (
          <div key={r.report_id} className="row">
            <b>{r.scene.title ?? "Text search"}</b>
            <span>
              {r.level ? LEVEL[r.level].label : "—"} · saved {r.saved_at.slice(0, 16).replace("T", " ")}
            </span>
          </div>
        ))}
      </div>
    ) : (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No reuse decisions saved yet" />
    );

  return (
    <nav className="ox-steps">
      {STEPS.map((s, i) => (
        <Fragment key={s}>
          {i === 1 && <span className="ox-step-gap" />}
          {i > 1 && <span className="ox-step-arrow" />}
          <span className={`ox-step${i === active ? " on" : ""}`}>
            <span className="n">{i + 1}</span>
            {s}
          </span>
        </Fragment>
      ))}
      <div className="tools">
        <Popover title="Project files" content={files} trigger="click" placement="bottomRight">
          <button>
            <FolderOutlined /> Project files
          </button>
        </Popover>
        <i />
        <Popover title="Saved reuse decisions" content={activity} trigger="click" placement="bottomRight" onOpenChange={loadReports}>
          <button>
            <HistoryOutlined /> Recent activity
          </button>
        </Popover>
      </div>
    </nav>
  );
}
