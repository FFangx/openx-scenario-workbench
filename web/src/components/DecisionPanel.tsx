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
import { api, basename, categoryLabel, LEVEL, levelLabel, urls, type Candidate, type Difference, type Lang } from "../api";
import { useT } from "../i18n";
import type { SceneRef } from "../App";
import { ArrowUpRight } from "./ArrowUpRight";

const SUB: Record<string, [string, string]> = {
  direct: ["候选场景无需修改即可复用。", "The candidate scenario can be reused without modification."],
  modify: ["按下方列出的修改后即可复用。", "The candidate can be reused after the changes listed below."],
  new_build: ["存在阻断差异，无法复用，需要新建场景。", "Blocking differences prevent reuse. Build a new scenario."],
  standards: ["结构相似，但场景或道路的标准检查未通过或未完成。", "Structure matches, but the scenario or road standard checks have not passed yet."],
  partial: ["已完成部分结构比较；确认未验证项后才能认定复用。", "Part of the structure was compared. Resolve the unverified items before confirming reuse."],
  undecidable: ["参与者交互或主车动作缺少关键结构，无法判断复用。", "Key participant or ego-action facts are missing, so reuse cannot be assessed."],
  recall: ["这是文本检索结果。选择 PDF 场景后才能按结构评估复用。", "Text-only match. Select a PDF scene to assess reuse structurally."],
};

// Review sub-kinds get their own headline, matching the desktop wording.
const REVIEW_TITLE: Record<string, [string, string]> = {
  standards: ["文件标准待复核", "File standards need review"],
  partial: ["部分已验证 · 待复核", "Partially verified · review"],
  undecidable: ["关键结构不足 · 无法判断", "Insufficient structure · undecidable"],
  recall: ["文本召回 · 待结构验证", "Text recall · verify structure"],
};

const STATUS = (d: Difference, lang: Lang) =>
  !d.verified
    ? { label: lang === "zh" ? "未验证" : "Unverified", cls: "warn", icon: <QuestionCircleFilled /> }
    : d.blocking
      ? { label: lang === "zh" ? "阻断" : "Blocking", cls: "bad", icon: <CloseCircleFilled /> }
      : { label: lang === "zh" ? "需修改" : "Change", cls: "warn", icon: <ExclamationCircleFilled /> };

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
  const { t } = useT();
  const [busy, setBusy] = useState(false);

  if (!cand) {
    return (
      <section className="panel decide">
        <div className="ph">
          <span className="n">3</span>{t("复用决策与追溯", "Reuse decision and traceability")}
        </div>
        <div className="box decide-empty">
          {searching ? <Spin /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("检索并选择候选后显示复用评估", "Search and pick a candidate to see the reuse assessment")} />}
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
        cand.differences.map((d) => [categoryLabel(d, lang), d.requested_label, d.candidate_label, STATUS(d, lang).label, d.action].map(csvCell).join(",")),
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
      message.success(t("决策已保存到当前项目，并固定了所选资产版本。", "Decision saved to this project and pinned to the selected asset version."));
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saveBlocked = !scene
    ? t("先选择 PDF 场景才能保存决策。", "Select a PDF scene before saving a decision.")
    : cand.level === "review"
      ? t("处理待复核项后才能保存；仍可导出评估。", "Resolve the review items before saving. You can still export the assessment.")
      : !cand.version_id
        ? t("此资产没有已保存的版本。", "This asset has no stored version.")
        : null;

  const DecisionIcon = { direct: CheckCircleFilled, modify: ExclamationCircleFilled, review: QuestionCircleFilled, not: CloseCircleFilled }[level.cls];
  const std = cand.standard_checks;
  const page = scene?.pages?.[0];

  return (
    <section className="panel decide">
      <div className="ph">
        <span className="n">3</span>{t("复用决策与追溯", "Reuse decision and traceability")}
      </div>

      <div className={`decision ${level.cls}`}>
        <div className="hd">
          <DecisionIcon /> {t("复用结论", "Reuse decision")}
          <Tooltip title={t("综合相似度：语义 55%、场景结构 30%、道路 15%", "Combined similarity: 55% semantic, 30% scenario structure, 15% road")}>
            <span className="cf">
              {t("匹配分", "Match score")} <b>{cand.scores.combined.toFixed(2)}</b>
            </span>
          </Tooltip>
        </div>
        <div className="big">{cand.level === "review" && REVIEW_TITLE[cand.review_kind] ? t(...REVIEW_TITLE[cand.review_kind]) : levelLabel(cand.level, lang)}</div>
        <div className="sub">{t(...SUB[cand.level === "review" ? (SUB[cand.review_kind] ? cand.review_kind : "partial") : cand.level])}</div>
      </div>

      <div className="box flush sel-item">
        <div className="top">
          <div className="sel-name">
            <div className="sec-title">
              <SafetyCertificateOutlined /> {t("所选资产", "Selected item")}
            </div>
            <div className="name" title={cand.title}>
              {cand.display_title}
            </div>
          </div>
          <Button href={urls.file(cand, "scenario")} target="_blank">
            <span style={{ color: "var(--link)" }}>
              {t("打开 XOSC", "Open XOSC")} <ArrowUpRight />
            </span>
          </Button>
        </div>
        <div className="kvt">
          <span>{t("功能", "Function")}</span>
          <span>{[cand.classification.function_type].flat().join(", ") || "—"}</span>
          <span>{t("道路 / 目标", "Road / target")}</span>
          <span>{[cand.classification.label_road_type, ...[cand.classification.label_target_type].flat()].filter(Boolean).join(" · ") || "—"}</span>
          <span>{t("来源需求", "Source requirement")}</span>
          <span>{scene ? `${scene.section_id} · ${t("页", "pages")} ${scene.pages?.join("–") ?? "—"}` : t("文本检索", "Text search")}</span>
          <span>{t("预计修改成本", "Estimated change cost")}</span>
          <span>{cand.change_cost == null ? "—" : `${cand.change_cost.toFixed(1)} ${t("（相对值）", "(relative)")}`}</span>
          <span>{t("标准检查", "Standard checks")}</span>
          <span className={std.passed ? "cost-Low" : "cost-Medium"}>
            {std.passed ? t("已通过", "Passed") : `${t("待完成：", "Pending: ")}${Object.entries(std.pending).map(([k, v]) => `${k} ${v}`).join(", ")}`}
          </span>
        </div>
      </div>

      <div className="box blocking">
        <div className="card-h">
          {blocking.length ? <CloseCircleFilled className="ic-bad" /> : <CheckCircleFilled className="ic-ok" />}
          {t(`阻断差异（${blocking.length}）`, `Blocking differences (${blocking.length})`)}
        </div>
        <div className="note">
          {blocking.length === 0 ? (
            t("没有发现阻断差异。", "No blocking differences found.")
          ) : (
            <ul>
              {blocking.slice(0, 2).map((d, i) => (
                <li key={i} title={say(d)}>{say(d)}</li>
              ))}
              {blocking.length > 2 && <li className="muted">{t(`另有 ${blocking.length - 2} 项见下表`, `+${blocking.length - 2} more in the table below`)}</li>}
            </ul>
          )}
        </div>
      </div>

      <div className="box flush facts-wrap">
        <div className="card-h">
          <SafetyCertificateOutlined /> {t("需求与候选对比", "Requirement vs candidate")}
          <span className="r">
            {cand.differences.length ? <ExclamationCircleFilled className="ic-warn" /> : <CheckCircleFilled className="ic-ok" />}
            {cand.differences.length ? t(`${cand.differences.length} 项差异`, `${cand.differences.length} differences`) : t("检查的字段全部一致", "All checked fields match")}
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
                <th>{t("字段", "Field")}</th>
                <th>{t("需求", "Requirement")}</th>
                <th>{t("候选", "Candidate")}</th>
                <th>{t("状态", "Status")}</th>
              </tr>
            </thead>
            <tbody>
              {cand.differences.map((d, i) => {
                const s = STATUS(d, lang);
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
          <LinkOutlined /> {t("追溯链接", "Traceability links")} <span className="r">{t(`${scene ? 3 : 2} 个链接`, `${scene ? 3 : 2} links`)}</span>
        </div>
        <div className="trace">
          {scene && sceneRef && (
            <>
              <span>{t("需求", "Requirement")}</span>
              <span className="ell" title={sceneRef.doc.filename}>{sceneRef.doc.filename.replace(/\.pdf$/i, "")} – p.{page} ({scene.section_id})</span>
              <span><a href={urls.pdf(sceneRef.projectId, sceneRef.doc.document_id, page)} target="_blank" rel="noreferrer">{t("打开", "Open")} <ArrowUpRight /></a></span>
            </>
          )}
          <span>{t("场景", "Scenario")}</span>
          <span className="ell" title={cand.xosc}>{basename(cand.xosc)}</span>
          <span><a href={urls.file(cand, "scenario")} target="_blank" rel="noreferrer">{t("打开", "Open")} <ArrowUpRight /></a></span>
          <span>{t("道路", "Road")}</span>
          <span className="ell" title={cand.xodr}>{basename(cand.xodr)}</span>
          <span><a href={urls.file(cand, "road")} target="_blank" rel="noreferrer">{t("打开", "Open")} <ArrowUpRight /></a></span>
        </div>
      </div>

      <div className="actions">
        <Space.Compact>
          <Button type="primary" size="large" icon={<DownloadOutlined />} loading={busy} onClick={() => exportAs("json")}>
            {t("导出复用结果", "Export reuse result")}
          </Button>
          <Dropdown
            trigger={["click"]}
            placement="bottomRight"
            menu={{
              items: [
                { key: "json", label: t("导出追溯 JSON", "Export trace as JSON") },
                { key: "csv", label: t("导出差异 CSV", "Export differences as CSV") },
              ],
              onClick: ({ key }) => exportAs(key as "json" | "csv"),
            }}
          >
            <Button type="primary" size="large" icon={<DownOutlined />} aria-label={t("更多导出选项", "More export options")} />
          </Dropdown>
        </Space.Compact>
        <Tooltip title={saveBlocked}>
          <Button size="large" icon={<SaveOutlined />} disabled={!!saveBlocked || busy} onClick={save}>
            {t("保存决策", "Save decision")}
          </Button>
        </Tooltip>
      </div>
    </section>
  );
}
