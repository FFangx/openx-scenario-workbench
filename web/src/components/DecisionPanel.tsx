import type { ReactNode } from "react";
import { App, Button, Dropdown, Space } from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  DownOutlined,
  DownloadOutlined,
  ExclamationCircleFilled,
  LinkOutlined,
  PlusCircleOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { REQ_FACTS, type Candidate, type FactStatus, type Scene } from "../data/mock";
import { MATCH_CLASS } from "./SearchPanel";
import { ArrowUpRight } from "./ArrowUpRight";

const STATUS: Record<FactStatus, { label: string; icon: ReactNode }> = {
  ok: { label: "Matched", icon: <CheckCircleFilled /> },
  warn: { label: "Adjust", icon: <ExclamationCircleFilled /> },
  bad: { label: "Conflict", icon: <CloseCircleFilled /> },
};

const SUB = {
  direct: "The candidate scenario can be reused without modification.",
  modify: "The candidate can be reused after the adjustments listed below.",
  not: "Blocking differences prevent reuse. Build a new scenario.",
};

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function DecisionPanel({ scene, cand }: { scene: Scene; cand: Candidate }) {
  const { message } = App.useApp();
  const kind = MATCH_CLASS[cand.match];
  const facts = REQ_FACTS.map((r, i) => ({ key: r, req: r, cand: cand.facts[i][0], st: cand.facts[i][1] }));
  const okCount = facts.filter((f) => f.st === "ok").length;
  const blocking = facts.filter((f) => f.st === "bad");
  const adjust = facts.filter((f) => f.st === "warn");

  const result = {
    requirement: scene.req,
    pages: scene.pages,
    scenario: cand.xosc,
    road: cand.xodr,
    decision: cand.match,
    confidence: cand.conf,
    change_cost: cand.cost,
    facts: facts.map(({ req, cand: c, st }) => ({ requirement: req, candidate: c, status: st })),
  };
  const exportAs = (fmt: "json" | "csv") => {
    if (fmt === "json") download(`reuse_${scene.req}_${cand.xosc}.json`, JSON.stringify(result, null, 2), "application/json");
    else
      download(
        `reuse_${scene.req}_${cand.xosc}.csv`,
        "requirement,candidate,status\n" + result.facts.map((f) => `"${f.requirement}","${f.candidate}",${f.status}`).join("\n"),
        "text/csv",
      );
  };

  const DecisionIcon = { direct: CheckCircleFilled, modify: ExclamationCircleFilled, not: CloseCircleFilled }[kind];

  return (
    <section className="panel decide">
      <div className="ph">
        <span className="n">3</span>Reuse decision and traceability
      </div>

      <div className={`decision ${kind}`}>
        <div className="hd">
          <DecisionIcon /> Reuse decision
          <span className="cf">
            Confidence <b>{cand.conf.toFixed(2)}</b>
          </span>
        </div>
        <div className="big">{cand.match}</div>
        <div className="sub">{SUB[kind]}</div>
      </div>

      <div className="box flush sel-item">
        <div className="top">
          <div>
            <div className="sec-title">
              <SafetyCertificateOutlined /> Selected item
            </div>
            <div className="name">
              <a>{cand.xosc}</a>
              <span className="plus">+</span>
              <a>{cand.xodr}</a>
            </div>
          </div>
          <Button onClick={() => message.info(`Opens ${cand.xosc} in the scenario editor`)}>
            <span style={{ color: "var(--link)" }}>
              Open in editor <ArrowUpRight />
            </span>
          </Button>
        </div>
        <div className="kvt">
          <span>Scenario type</span>
          <span>Lane support – Cut-in</span>
          <span>Standard</span>
          <span>Euro NCAP 2025</span>
          <span>Source requirement</span>
          <span>
            Pages {scene.pages} ({scene.req})
          </span>
          <span>Estimated change cost</span>
          <span className={`cost-${cand.cost}`}>{cand.cost}</span>
          <span>Rationale</span>
          <span>{cand.rationale}</span>
        </div>
      </div>

      <div className="box blocking">
        <div className="card-h">
          {blocking.length ? <CloseCircleFilled className="ic-bad" /> : <CheckCircleFilled className="ic-ok" />}
          Blocking differences ({blocking.length})
        </div>
        <div className="note">
          {blocking.length === 0 && "No blocking differences found."}
          {(blocking.length > 0 || adjust.length > 0) && (
            <ul>
              {blocking.map((f) => (
                <li key={f.req}>
                  <b>{f.req}</b> → {f.cand}
                </li>
              ))}
              {adjust.map((f) => (
                <li key={f.req}>
                  Adjust <b>{f.req}</b> → {f.cand}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="box flush facts-wrap">
        <div className="card-h">
          <SafetyCertificateOutlined /> Key matched facts
          <span className="r">
            {okCount === 5 ? <CheckCircleFilled className="ic-ok" /> : <ExclamationCircleFilled className="ic-warn" />}
            {okCount} / 5 matched
          </span>
        </div>
        <table className="facts-t">
          <colgroup>
            <col style={{ width: 137 }} />
            <col />
            <col style={{ width: 82 }} />
          </colgroup>
          <thead>
            <tr>
              <th>Requirement fact</th>
              <th>Candidate fact</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {facts.map((f) => (
              <tr key={f.key}>
                <td title={f.req}>{f.req}</td>
                <td title={f.cand}>{f.cand}</td>
                <td>
                  <span className={`st ${f.st}`}>
                    {STATUS[f.st].icon}
                    {STATUS[f.st].label}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="box flush">
        <div className="card-h">
          <LinkOutlined /> Traceability links <span className="r">3 links</span>
        </div>
        <div className="trace">
          <span>Requirement</span>
          <span><a>Euro NCAP 2025 – p.{scene.p0} ({scene.req})</a></span>
          <span><a>Open <ArrowUpRight /></a></span>
          <span>Scenario</span>
          <span><a>{cand.xosc}</a></span>
          <span><a>Open <ArrowUpRight /></a></span>
          <span>Road</span>
          <span><a>{cand.xodr}</a></span>
          <span><a>Open <ArrowUpRight /></a></span>
        </div>
      </div>

      <div className="actions">
        <Space.Compact>
          <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={() => exportAs("json")}>
            Export reuse result
          </Button>
          <Dropdown
            trigger={["click"]}
            placement="bottomRight"
            menu={{
              items: [
                { key: "json", label: "Export as JSON" },
                { key: "csv", label: "Export facts as CSV" },
              ],
              onClick: ({ key }) => exportAs(key as "json" | "csv"),
            }}
          >
            <Button type="primary" size="large" icon={<DownOutlined />} aria-label="More export options" />
          </Dropdown>
        </Space.Compact>
        <Button size="large" icon={<PlusCircleOutlined />} onClick={() => message.success(`Added ${cand.xosc} → ${scene.req} to worklist`)}>
          Add to worklist
        </Button>
      </div>
    </section>
  );
}
