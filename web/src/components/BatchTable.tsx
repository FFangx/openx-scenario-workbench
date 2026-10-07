import { Table, Tag, type TableColumnsType } from "antd";
import { verdictClass, verdictLabel, type Trace } from "../api";
import { useT } from "../i18n";

type Entry = NonNullable<Trace["entries"]>[number] & { key: number };

export const encoderName = (id: string | null | undefined, lang: string) =>
  !id ? "—" : id.includes("bge-m3") ? (lang === "zh" ? "BGE-M3 语义检索" : "BGE-M3 semantic retrieval")
    : id.startsWith("hashing-") ? (lang === "zh" ? "轻量离线检索" : "Lightweight offline retrieval") : id;

/** One row per requirement of a whole-PDF assessment: verdict, scene, pages, the top candidates with theirs. */
export function BatchTable({ trace, target, onTarget, height = 200 }: { trace: Trace; target?: number; onTarget?: (i: number) => void; height?: number }) {
  const { t, lang } = useT();
  const entries: Entry[] = (trace.entries ?? []).map((e, i) => ({ ...e, key: i }));
  const grouped = (trace.source?.documents?.length ?? 0) > 1;  // one summary of several PDFs names each row's
  const columns: TableColumnsType<Entry> = [
    {
      title: t("结论", "Verdict"), key: "v", width: 136,
      render: (_, e) => <Tag className={`mtag ${verdictClass(e.assessment.level)}`}>{verdictLabel(e.assessment.level, e.assessment.review_kind, lang)}</Tag>,
    },
    ...(grouped ? [{ title: t("文档", "PDF"), key: "d", width: "16%", ellipsis: true, render: (_: unknown, e: Entry) => e.source.filename ?? "—" }] : []),
    { title: t("需求场景", "Scene"), key: "s", width: "26%", ellipsis: true, render: (_, e) => e.source.title },
    { title: t("页码", "Pages"), key: "p", width: 64, render: (_, e) => (e.source.evidence ?? []).map((x) => `${x.page_start}–${x.page_end}`).join(", ") || "—" },
    {
      title: t("候选（前三）", "Top candidates"), key: "c",
      render: (_, e) => e.candidates.length ? e.candidates.slice(0, 3).map((c, i) => (
        <div key={i} className="batch-cand" title={c.candidate.title ?? ""}>
          <Tag className={`mtag ${verdictClass(c.reuse.level)}`}>{verdictLabel(c.reuse.level, c.reuse.review_kind, lang)}</Tag>
          <span>{c.candidate.title ?? "—"}</span>
        </div>
      )) : "—",
    },
    { title: t("修订", "Rev."), key: "r", width: 50, render: (_, e) => e.source.revision },
    {
      title: t("修改成本", "Cost"), key: "cost", width: 72, align: "right",
      render: (_, e) => (e.assessment.estimated_change_cost == null ? "—" : e.assessment.estimated_change_cost.toFixed(1)),
    },
  ];
  return (
    <Table<Entry>
      className="ov-table batch-table"
      size="small"
      rowKey="key"
      columns={columns}
      dataSource={entries}
      pagination={false}
      tableLayout="fixed"
      scroll={{ y: height }}
      rowClassName={(e) => (onTarget && e.key === target ? "row-active" : "")}
      onRow={(e) => ({ onClick: () => onTarget?.(e.key) })}
    />
  );
}

export function BatchCounts({ trace }: { trace: Trace }) {
  const { lang } = useT();
  return <>{Object.entries(trace.counts ?? {}).map(([k, n]) => `${verdictLabel(k, k, lang)}: ${n}`).join(" · ")}</>;
}
