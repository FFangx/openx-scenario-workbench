import { Table, Tag, type TableColumnsType } from "antd";
import { verdictClass, verdictLabel, type Trace } from "../api";
import { useT } from "../i18n";

type Entry = NonNullable<Trace["entries"]>[number] & { key: number };

export const encoderName = (id: string | undefined, lang: string) =>
  !id ? "—" : id.includes("bge-m3") ? (lang === "zh" ? "BGE-M3 语义检索" : "BGE-M3 semantic retrieval")
    : id.startsWith("hashing-") ? (lang === "zh" ? "轻量离线检索" : "Lightweight offline retrieval") : id;

/** One row per requirement of a whole-PDF assessment: verdict, scene, pages, best candidate. */
export function BatchTable({ trace, target, onTarget, height = 200 }: { trace: Trace; target?: number; onTarget?: (i: number) => void; height?: number }) {
  const { t, lang } = useT();
  const entries: Entry[] = (trace.entries ?? []).map((e, i) => ({ ...e, key: i }));
  const columns: TableColumnsType<Entry> = [
    {
      title: t("结论", "Verdict"), key: "v", width: 150,
      render: (_, e) => <Tag className={`mtag ${verdictClass(e.assessment.level)}`}>{verdictLabel(e.assessment.level, e.assessment.review_kind, lang)}</Tag>,
    },
    { title: t("需求场景", "Scene"), key: "s", ellipsis: true, render: (_, e) => e.source.title },
    { title: t("页码", "Pages"), key: "p", width: 70, render: (_, e) => (e.source.evidence ?? []).map((x) => `${x.page_start}–${x.page_end}`).join(", ") || "—" },
    { title: t("首选候选", "Best candidate"), key: "c", ellipsis: true, render: (_, e) => e.candidates[0]?.candidate.title ?? "—" },
    { title: t("修订", "Rev."), key: "r", width: 50, render: (_, e) => e.source.revision },
    {
      title: t("修改成本", "Cost"), key: "cost", width: 80, align: "right",
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
