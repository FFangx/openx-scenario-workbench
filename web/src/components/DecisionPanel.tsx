import { useState } from "react";
import { App, Button, Dropdown, Empty, Space, Spin, Tooltip } from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  DownOutlined,
  DownloadOutlined,
  ExclamationCircleFilled,
  LinkOutlined,
  QuestionCircleFilled,
  SafetyCertificateOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { api, basename, categoryLabel, LEVEL, urls, type Candidate, type Difference, type Lang } from "../api";
import type { SceneRef } from "../App";
import { ArrowUpRight } from "./ArrowUpRight";

const SUB: Record<string, string> = {
  direct: "The candidate scenario can be reused without modification.",
  modify: "The candidate can be reused after the changes listed below.",
  new_build: "Blocking differences prevent reuse. Build a new scenario.",
  standards: "Structure matches, but the scenario or road standard checks have not passed yet.",
  partial: "Part of the structure was compared. Resolve the unverified items before confirming reuse.",
  undecidable: "Key participant or ego-action facts are missing, so reuse cannot be assessed.",
  recall: "Text-only match. Select a PDF scene to assess reuse structurally.",
};

const STATUS = (d: Difference) =>
  !d.verified
    ? { label: "Unverified", cls: "warn", icon: <QuestionCircleFilled /> }
    : d.blocking
      ? { label: "Blocking", cls: "bad", icon: <CloseCircleFilled /> }
      : { label: "Change", cls: "warn", icon: <ExclamationCircleFilled /> };

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

const csvCell = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;

interface Props {
  sceneRef: SceneRef | null;
  cand: Candidate | null;
  searching: boolean;
  query: string;
  lang: Lang;
}

export function DecisionPanel({ sceneRef, cand, searching, query, lang }: Props) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);

  if (!cand) {
    return (
      <section className="panel decide">
        <div className="ph">
          <span className="n">3</span>Reuse decision and traceability
        </div>
        <div className="box decide-empty">
          {searching ? <Spin /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Search and pick a candidate to see the reuse assessment" />}
        </div>
      </section>
    );
  }

  const level = LEVEL[cand.level];
  const blocking = cand.differences.filter((d) => d.blocking);
  const say = (d: Difference) => (lang === "zh" ? d.text : `${categoryLabel(d, lang)}: ${d.requested_label} → ${d.action}`);
  const scene = sceneRef?.scene;
  const request = {
    project_id: sceneRef?.projectId ?? "",
    document_id: sceneRef?.doc.document_id,
    scene_id: scene?.scene_id,
    revision: scene?.revision,
    text: query,
    lang,
    asset_id: cand.asset_id,
    version_id: cand.version_id ?? "",
  };
  const stem = `reuse_${scene?.section_id || "search"}_${basename(cand.xosc).replace(/\.xosc$/i, "")}`;

  const exportAs = async (fmt: "json" | "csv") => {
    if (fmt === "csv") {
      const lines = [["field", "requirement", "candidate", "status", "action"].join(",")].concat(
        cand.differences.map((d) => [categoryLabel(d, lang), d.requested_label, d.candidate_label, STATUS(d).label, d.action].map(csvCell).join(",")),
      );
      download(`${stem}.csv`, lines.join("\n"), "text/csv");
      return;
    }
    setBusy(true);
    try {
      download(`${stem}.json`, JSON.stringify(await api.trace(request), null, 2), "application/json");
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.saveDecision(request);
      message.success("Decision saved to this project and pinned to the selected asset version.");
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saveBlocked = !scene
    ? "Select a PDF scene before saving a decision."
    : cand.level === "review"
      ? "Resolve the review items before saving. You can still export the assessment."
      : !cand.version_id
        ? "This asset has no stored version."
        : null;

  const DecisionIcon = { direct: CheckCircleFilled, modify: ExclamationCircleFilled, review: QuestionCircleFilled, not: CloseCircleFilled }[level.cls];
  const std = cand.standard_checks;
  const page = scene?.pages?.[0];

  return (
    <section className="panel decide">
      <div className="ph">
        <span className="n">3</span>Reuse decision and traceability
      </div>

      <div className={`decision ${level.cls}`}>
        <div className="hd">
          <DecisionIcon /> Reuse decision
          <Tooltip title="Combined similarity: 55% semantic, 30% scenario structure, 15% road">
            <span className="cf">
              Match score <b>{cand.scores.combined.toFixed(2)}</b>
            </span>
          </Tooltip>
        </div>
        <div className="big">{level.label}</div>
        <div className="sub">{SUB[cand.level === "review" ? cand.review_kind || "partial" : cand.level]}</div>
      </div>

      <div className="box flush sel-item">
        <div className="top">
          <div className="sel-name">
            <div className="sec-title">
              <SafetyCertificateOutlined /> Selected item
            </div>
            <div className="name" title={cand.title}>
              {cand.display_title}
            </div>
          </div>
          <Button href={urls.file(cand, "scenario")} target="_blank">
            <span style={{ color: "var(--link)" }}>
              Open XOSC <ArrowUpRight />
            </span>
          </Button>
        </div>
        <div className="kvt">
          <span>Function</span>
          <span>{[cand.classification.function_type].flat().join(", ") || "—"}</span>
          <span>Road / target</span>
          <span>{[cand.classification.label_road_type, ...[cand.classification.label_target_type].flat()].filter(Boolean).join(" · ") || "—"}</span>
          <span>Source requirement</span>
          <span>{scene ? `${scene.section_id} · pages ${scene.pages?.join("–") ?? "—"}` : "Text search"}</span>
          <span>Estimated change cost</span>
          <span>{cand.change_cost == null ? "—" : `${cand.change_cost.toFixed(1)} (relative)`}</span>
          <span>Standard checks</span>
          <span className={std.passed ? "cost-Low" : "cost-Medium"}>
            {std.passed ? "Passed" : `Pending: ${Object.entries(std.pending).map(([k, v]) => `${k} ${v}`).join(", ")}`}
          </span>
        </div>
      </div>

      <div className="box blocking">
        <div className="card-h">
          {blocking.length ? <CloseCircleFilled className="ic-bad" /> : <CheckCircleFilled className="ic-ok" />}
          Blocking differences ({blocking.length})
        </div>
        <div className="note">
          {blocking.length === 0 ? (
            "No blocking differences found."
          ) : (
            <ul>
              {blocking.slice(0, 2).map((d, i) => (
                <li key={i} title={say(d)}>{say(d)}</li>
              ))}
              {blocking.length > 2 && <li className="muted">+{blocking.length - 2} more in the table below</li>}
            </ul>
          )}
        </div>
      </div>

      <div className="box flush facts-wrap">
        <div className="card-h">
          <SafetyCertificateOutlined /> Requirement vs candidate
          <span className="r">
            {cand.differences.length ? <ExclamationCircleFilled className="ic-warn" /> : <CheckCircleFilled className="ic-ok" />}
            {cand.differences.length ? `${cand.differences.length} differences` : "All checked fields match"}
          </span>
        </div>
        <div className="facts-scroll">
          <table className="facts-t">
            <colgroup>
              <col style={{ width: 96 }} />
              <col />
              <col style={{ width: 82 }} />
              <col style={{ width: 82 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Field</th>
                <th>Requirement</th>
                <th>Candidate</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {cand.differences.map((d, i) => {
                const s = STATUS(d);
                return (
                  <tr key={i} title={say(d)}>
                    <td>{categoryLabel(d, lang)}</td>
                    <td>{d.requested_label}</td>
                    <td>{d.candidate_label}</td>
                    <td>
                      <span className={`st ${s.cls}`}>
                        {s.icon}
                        {s.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {!cand.differences.length && (
                <tr>
                  <td colSpan={4} className="muted">
                    {cand.reasons.map((r) => r.label).join(" · ")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="box flush">
        <div className="card-h">
          <LinkOutlined /> Traceability links <span className="r">{scene ? 3 : 2} links</span>
        </div>
        <div className="trace">
          {scene && sceneRef && (
            <>
              <span>Requirement</span>
              <span className="ell" title={sceneRef.doc.filename}>{sceneRef.doc.filename.replace(/\.pdf$/i, "")} – p.{page} ({scene.section_id})</span>
              <span><a href={urls.pdf(sceneRef.projectId, sceneRef.doc.document_id, page)} target="_blank" rel="noreferrer">Open <ArrowUpRight /></a></span>
            </>
          )}
          <span>Scenario</span>
          <span className="ell" title={cand.xosc}>{basename(cand.xosc)}</span>
          <span><a href={urls.file(cand, "scenario")} target="_blank" rel="noreferrer">Open <ArrowUpRight /></a></span>
          <span>Road</span>
          <span className="ell" title={cand.xodr}>{basename(cand.xodr)}</span>
          <span><a href={urls.file(cand, "road")} target="_blank" rel="noreferrer">Open <ArrowUpRight /></a></span>
        </div>
      </div>

      <div className="actions">
        <Space.Compact>
          <Button type="primary" size="large" icon={<DownloadOutlined />} loading={busy} onClick={() => exportAs("json")}>
            Export reuse result
          </Button>
          <Dropdown
            trigger={["click"]}
            placement="bottomRight"
            menu={{
              items: [
                { key: "json", label: "Export trace as JSON" },
                { key: "csv", label: "Export differences as CSV" },
              ],
              onClick: ({ key }) => exportAs(key as "json" | "csv"),
            }}
          >
            <Button type="primary" size="large" icon={<DownOutlined />} aria-label="More export options" />
          </Dropdown>
        </Space.Compact>
        <Tooltip title={saveBlocked}>
          <Button size="large" icon={<SaveOutlined />} disabled={!!saveBlocked || busy} onClick={save}>
            Save decision
          </Button>
        </Tooltip>
      </div>
    </section>
  );
}
