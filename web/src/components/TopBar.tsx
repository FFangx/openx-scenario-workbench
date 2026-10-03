import { Fragment, useState } from "react";
import { App, Dropdown, Tooltip, type MenuProps } from "antd";
import {
  CheckOutlined,
  DownOutlined,
  FolderOutlined,
  HistoryOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";

export type Appearance = "light" | "dark" | "system";

const PROJECTS = ["Euro NCAP 2025 LSS", "GB/T ADAS 2024", "UN R157 ALKS"];
const WORKSPACES = ["Default", "Local machine"];

export function TopBar({ appearance, onAppearance }: { appearance: Appearance; onAppearance: (a: Appearance) => void }) {
  const [project, setProject] = useState(PROJECTS[0]);
  const [workspace, setWorkspace] = useState(WORKSPACES[0]);
  const [lang, setLang] = useState<"en" | "zh">("en");
  const { message } = App.useApp();

  const pick = (list: string[], cur: string, set: (v: string) => void): MenuProps => ({
    items: list.map((v) => ({ key: v, label: v, icon: v === cur ? <CheckOutlined /> : <span style={{ width: 14 }} /> })),
    onClick: ({ key }) => set(key),
  });

  const settings: MenuProps = {
    items: [
      {
        key: "appearance",
        type: "group",
        label: "Appearance",
        children: (["light", "dark", "system"] as const).map((a) => ({
          key: a,
          label: { light: "Light", dark: "Dark", system: "Follow system" }[a],
          icon: a === appearance ? <CheckOutlined /> : <span style={{ width: 14 }} />,
        })),
      },
      { type: "divider" },
      { key: "models", label: "Model & encoder settings" },
      { key: "schemas", label: "Schema registry" },
    ],
    onClick: ({ key }) => {
      if (key === "light" || key === "dark" || key === "system") onAppearance(key);
      else message.info("Opens in phase 2");
    },
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
        <Dropdown menu={pick(PROJECTS, project, setProject)} trigger={["click"]}>
          <button className="hbtn">
            Project <b>{project}</b> <DownOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <Dropdown menu={pick(WORKSPACES, workspace, setWorkspace)} trigger={["click"]}>
          <button className="hbtn">
            Workspace <b>{workspace}</b> <DownOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <Tooltip title="Help">
          <button className="hicon" aria-label="Help">
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
          <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
          <button className={lang === "zh" ? "on" : ""} onClick={() => setLang("zh")}>中文</button>
        </span>
      </div>
    </header>
  );
}

const STEPS = ["Extract from PDF", "Search asset library", "Assess reuse", "Export & trace"];

export function StepBar() {
  const [active, setActive] = useState(0);
  return (
    <nav className="ox-steps">
      {STEPS.map((s, i) => (
        <Fragment key={s}>
          {i === 1 && <span className="ox-step-gap" />}
          {i > 1 && <span className="ox-step-arrow" />}
          <button className={`ox-step${i === active ? " on" : ""}`} onClick={() => setActive(i)}>
            <span className="n">{i + 1}</span>
            {s}
          </button>
        </Fragment>
      ))}
      <div className="tools">
        <button>
          <FolderOutlined /> Project files
        </button>
        <i />
        <button>
          <HistoryOutlined /> Recent activity
        </button>
      </div>
    </nav>
  );
}
