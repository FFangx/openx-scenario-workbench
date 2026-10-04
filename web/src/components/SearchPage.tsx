import { useLayoutEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Empty, Input, Select, Skeleton, Tag } from "antd";
import { ArrowLeftOutlined, FileSearchOutlined, PictureOutlined, SearchOutlined } from "@ant-design/icons";
import { facetLabel, urls, type Candidate, type Library } from "../api";
import { useT } from "../i18n";
import type { useMatching } from "../useMatching";
import { valueLabel } from "../vocab";
import { AssetDetail } from "./AssetDetail";

interface Props {
  search: ReturnType<typeof useMatching>;
  library: Library | null;
  /** Where the start page's search box was; the bar here grows out of it. */
  from: DOMRect | null;
  esmini: boolean;
  onBack: () => void;
  onSettings: () => void;
  onLibraryChanged: () => void;
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Free-text search: similar assets only, never a reuse decision. */
export function SearchPage({ search, library, from, esmini, onBack, onSettings, onLibraryChanged }: Props) {
  const { t, lang } = useT();
  const bar = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<Candidate | null>(null);

  useLayoutEffect(() => {
    // FLIP: start the bar where the start page's box was, then let it settle at the top.
    const to = bar.current?.getBoundingClientRect();
    if (!from || !to || !bar.current || reducedMotion()) return;
    bar.current.animate(
      [{ transform: `translate(${from.left - to.left}px, ${from.top - to.top}px)`, width: `${from.width}px` },
        { transform: "none", width: `${to.width}px` }],
      { duration: 480, easing: "cubic-bezier(.2,.75,.25,1)" },
    );
  }, [from]);

  const run = () => search.query.trim() && search.runSearch();
  // Text recall ranks the whole library; an asset sharing nothing with the text is not a result.
  const results = (search.result?.results ?? []).filter((c) => c.scores.semantic > 0.005);
  const facets = library?.facets ?? {};

  return (
    <main className="sresults">
      <div className="sresults-bar" ref={bar}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} aria-label={t("返回起始页", "Back to start")} />
        <Input size="large" allowClear value={search.query} onChange={(e) => search.setQuery(e.target.value)} onPressEnter={run}
          prefix={<SearchOutlined />} aria-label={t("描述场景", "Describe a scenario")} />
        <Button size="large" type="primary" loading={search.searching} disabled={!search.query.trim()} onClick={run}>{t("检索", "Search")}</Button>
      </div>
      <div className="sresults-tools">
        {Object.entries(facets).map(([key, values]) => (
          <Select key={key} size="small" allowClear placeholder={facetLabel(key, lang)} value={search.filters[key]} style={{ minWidth: 130 }}
            options={values.map((v) => ({ value: v, label: valueLabel(v, lang) }))}
            onChange={(v) => {
              const next = { ...search.filters };
              if (v) next[key] = v; else delete next[key];
              search.setFilters(next);
              search.runSearch({ filters: next });
            }} />
        ))}
        <span className="muted">
          {search.result
            ? t(`${results.length} 个相似资产，按文本相似度排序；不作复用结论。`, `${results.length} similar assets, ordered by text similarity; no reuse decision.`)
            : t("按文本相似度检索资产库。", "Searching the library by text similarity.")}
        </span>
      </div>
      {search.error && <Alert type="error" showIcon title={search.error} className="sresults-alert" />}
      <div className="sresults-grid">
        {search.searching && !search.result
          ? Array.from({ length: 6 }, (_, i) => <div key={i} className="rcard"><Skeleton active paragraph={{ rows: 3 }} /></div>)
          : results.map((c, i) => (
            <button key={c.asset_id} className="rcard" style={{ "--i": Math.min(i, 11) } as React.CSSProperties} onClick={() => setOpen(c)}>
              {c.has_frame && c.version_id ? (
                <div className="thumb"><img src={urls.frame(c)} alt="" loading="lazy" /></div>
              ) : (
                <div className="thumb blank" aria-hidden="true">
                  {[c.classification.function_type].flat()[0] && [c.classification.function_type].flat()[0] !== "未知"
                    ? <b>{[c.classification.function_type].flat()[0]}</b> : <PictureOutlined />}
                </div>
              )}
              <b className="title" title={c.title}>{c.display_title}</b>
              <span className="muted file" title={c.xosc}>{c.xosc.split(/[\\/]/).pop()}</span>
              <span className="tags">
                {[c.classification.function_type, c.classification.label_road_type, ...[c.classification.label_target_type].flat()]
                  .filter((v): v is string => !!v && v !== "未知").map((v) => <Tag key={v}>{valueLabel(v, lang)}</Tag>)}
              </span>
              <span className="sim">
                <span className="muted">{t("相似度", "Similarity")}</span>
                <span className="meter"><i style={{ width: `${Math.round(Math.max(0, Math.min(1, c.scores.semantic)) * 100)}%` }} /></span>
                <b>{c.scores.semantic.toFixed(2)}</b>
              </span>
            </button>
          ))}
      </div>
      {search.result && !results.length && (
        <Empty image={<FileSearchOutlined className="empty-ic" />} description={
          search.result.encoder === "hashing"
            ? t("没有相似的资产。当前使用本地哈希检索，只匹配字面相同的词；换个说法，或在设置中改用 BGE-M3 语义检索。",
              "No similar assets. The local hashing search matches literal words only; rephrase, or switch to BGE-M3 semantic search in Settings.")
            : t("没有相似的资产。换个说法，或去掉筛选条件。", "No similar assets. Rephrase, or remove a filter.")} />
      )}
      <Drawer open={!!open} onClose={() => setOpen(null)} size={560} destroyOnHidden title={open?.display_title}>
        {open?.version_id && (
          <AssetDetail version={{ asset_id: open.asset_id, version_id: open.version_id }} busy={false} esmini={esmini} onSettings={onSettings}
            onSelect={() => undefined} onClose={() => setOpen(null)} onChanged={onLibraryChanged}
            onDeleted={() => { setOpen(null); onLibraryChanged(); search.runSearch(); }} onModelClassify={() => undefined} />
        )}
      </Drawer>
    </main>
  );
}
