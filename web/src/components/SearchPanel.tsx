import { useState } from "react";
import { Alert, Button, Empty, Form, Input, Select, Table, Tabs, Tag, Tooltip, type TableColumnsType } from "antd";
import { CheckCircleFilled, CloseCircleFilled, CloseOutlined, FileOutlined, FileTextOutlined, SearchOutlined } from "@ant-design/icons";
import { basename, facetLabel, LEVEL, levelLabel, urls, type Candidate, type Level, type Lang, type Library, type Scene, type SearchResponse } from "../api";
import { roadFeatureLabel, valueLabel } from "../vocab";
import { dateTime, useT } from "../i18n";
import { ArrowUpRight } from "./ArrowUpRight";
import { PreviewPlayer } from "./PreviewPlayer";

type Show = "all" | Level;

interface Props {
  query: string;
  onQuery: (q: string) => void;
  onSearch: () => void;
  onReset: () => void;
  filters: Record<string, string>;
  onFilters: (f: Record<string, string>) => void;
  library: Library | null;
  online: boolean | null;
  result: SearchResponse | null;
  searching: boolean;
  error: string | null;
  canSearch: boolean;
  scene: Scene | null;
  onClearScene: () => void;
  esmini: boolean;
  onSettings: () => void;
  activeKey: string | null;
  onActivate: (key: string) => void;
  checked: string[];
  onChecked: (keys: string[]) => void;
  active: Candidate | null;
}

const listText = (v: string | string[] | undefined, lang: Lang) => [v ?? []].flat().filter(Boolean).map((x) => valueLabel(x, lang)).join(", ") || "—";
const metres = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);

export function SearchPanel(p: Props) {
  const { t, lang } = useT();
  const [show, setShow] = useState<Show>("all");
  const [tab, setTab] = useState("search");

  const rows = (p.result?.results ?? []).map((c, i) => ({ ...c, idx: i + 1 })).filter((c) => show === "all" || c.level === show);

  const columns: TableColumnsType<Candidate & { idx: number }> = [
    { title: "#", dataIndex: "idx", width: 30, align: "center" },
    Table.SELECTION_COLUMN,
    {
      title: (
        <>
          {t("场景组合", "Scenario pair")}
          <br />
          (XOSC / XODR)
        </>
      ),
      key: "pair",
      width: 135,
      render: (_, c) => (
        <div className="pair">
          <a href={urls.file(c, "scenario")} target="_blank" rel="noreferrer" title={c.xosc} onClick={(e) => e.stopPropagation()}>
            <FileOutlined />
            <span className="fn">{basename(c.xosc)}</span>
          </a>
          {c.road.file_missing ? (
            <span className="muted" title={t("道路文件缺失", "Road file missing")}>
              <FileTextOutlined />
              <span className="fn">+ {t("道路缺失", "No road")}</span>
            </span>
          ) : (
            <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr} onClick={(e) => e.stopPropagation()}>
              <FileTextOutlined />
              <span className="fn">+ {basename(c.xodr)}</span>
            </a>
          )}
        </div>
      ),
    },
    {
      title: t("描述", "Description"),
      key: "desc",
      width: 120,
      render: (_, c) => (
        <span className="desc clamp2" title={c.title}>
          {c.display_title}
        </span>
      ),
    },
    ...(["semantic", "scenario", "road"] as const).map((k) => ({
      title: (
        <>
          {{ semantic: t("语义", "Semantic"), scenario: t("场景", "Scenario"), road: t("道路", "Road") }[k]}
          <br />
          {t("相似度", "similarity")}
        </>
      ),
      key: k,
      width: 63,
      render: (_: unknown, c: Candidate) => <span className={`score${c.level === "direct" ? " good" : ""}`}>{c.scores[k].toFixed(2)}</span>,
    })),
    {
      title: (
        <Tooltip title={t("结构比较得出的相对修改量，不是工时", "Relative effort score from the structural comparison, not working hours")}>
          {t("预计", "Estimated")}
          <br />
          {t("修改成本", "change cost")}
        </Tooltip>
      ),
      key: "cost",
      width: 78,
      render: (_, c) => <span className="cost-cell">{c.change_cost == null ? "—" : c.change_cost.toFixed(1)}</span>,
    },
    {
      title: t("结论", "Match"),
      key: "match",
      render: (_, c) => <Tag className={`mtag ${LEVEL[c.level].cls}`}>{levelLabel(c.level, lang)}</Tag>,
    },
  ];

  const facets = p.library?.facets ?? {};
  const filterForm = (
    <Form layout="vertical" size="small" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", columnGap: 12 }}>
      {Object.entries(facets).map(([k, opts]) => (
        <Form.Item key={k} label={facetLabel(k, lang)} style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder={t("不限", "Any")}
            value={p.filters[k]}
            options={opts.map((o) => ({ value: o, label: o }))}
            onChange={(v?: string) => {
              const next = { ...p.filters };
              if (v) next[k] = v;
              else delete next[k];
              p.onFilters(next);
            }}
          />
        </Form.Item>
      ))}
    </Form>
  );

  const chips = Object.entries(p.filters);
  const searchTab = (
    <>
      <div className="search-row">
        <Input
          prefix={<SearchOutlined />}
          allowClear
          value={p.query}
          onChange={(e) => p.onQuery(e.target.value)}
          onPressEnter={() => p.canSearch && p.onSearch()}
          placeholder={p.scene ? t("添加关键词细化当前场景的检索", "Add keywords to refine the selected scene") : t("输入描述，按文本检索相似资产", "Describe a scenario to find similar assets by text")}
        />
        <Button type="primary" onClick={p.onSearch} disabled={!p.canSearch} loading={p.searching}>
          {t("检索", "Search")}
        </Button>
        <Button onClick={p.onReset}>{t("重置", "Reset")}</Button>
      </div>
      <div className="chips">
        {p.scene && (
          <Tooltip title={t("关闭后按文本自由检索；结论只作文本召回，不作复用判断。", "Close to search by free text; results are text recall only, not a reuse decision.")}>
            <Tag className="chip scene-chip" closable closeIcon={<CloseOutlined />} onClose={(e) => { e.preventDefault(); p.onClearScene(); }}>
              {t("场景", "Scene")}
              <b className="ell">{p.scene.title}</b>
            </Tag>
          </Tooltip>
        )}
        {chips.length ? (
          chips.map(([k, v]) => (
            <Tag
              key={k}
              className="chip"
              closable
              closeIcon={<CloseOutlined />}
              onClose={(e) => {
                e.preventDefault();
                const next = { ...p.filters };
                delete next[k];
                p.onFilters(next);
              }}
            >
              {facetLabel(k, lang)}
              <b>{v}</b>
            </Tag>
          ))
        ) : (
          <span className="chips-empty">
            {t(`未筛选 · 对全部 ${p.library?.asset_count ?? "…"} 个资产排序。`, `No filters · all ${p.library?.asset_count ?? "…"} assets are ranked.`)}{" "}
            <a onClick={() => setTab("filters")}>{t("添加筛选", "Add filters")}</a>
          </span>
        )}
      </div>
    </>
  );

  const c = p.active;
  const scenarioKv = c && (
    <div className="kv">
      <span>{t("文件", "File")}</span><span title={c.xosc}>{basename(c.xosc)}</span>
      <span>{t("版本", "Version")}</span><span>{c.version_number ? `v${c.version_number}` : "—"}</span>
      <span>{t("描述", "Description")}</span><span>{c.description || c.title}</span>
      <span>{t("参与者", "Entities")}</span><span>{c.scenario.entities.map((e) => e.category ?? e.kind).join(", ") || "—"}</span>
      <span>{t("动作", "Actions")}</span><span>{c.scenario.actions.join(", ") || "—"}</span>
      <span>{t("参数化", "Parameterization")}</span><span>{c.scenario.parameters.join(", ") || t("未声明", "None declared")}</span>
    </div>
  );

  return (
    <section className="panel search">
      <div className="ph">
        <span className="n">2</span>{t("资产库检索与候选场景", "Asset library search and candidate scenarios")}
        <span className="meta">
          {t("资产库状态", "Library status")}
          {p.online === false ? (
            <span className="online off">
              <CloseCircleFilled /> {t("离线", "Offline")}
            </span>
          ) : (
            <span className="online">
              <CheckCircleFilled /> {p.online ? t("在线", "Online") : "…"}
            </span>
          )}
          {t("最近导入", "Last import")} <span className="ts">{dateTime(p.library?.last_import)}</span>
        </span>
      </div>

      <Tabs
        className="mid-tabs"
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: "search", label: t("检索", "Search"), children: searchTab },
          { key: "filters", label: t("筛选", "Filters"), children: filterForm },
          {
            key: "results",
            label: t(`结果（${p.result?.total ?? 0}）`, `Results (${p.result?.total ?? 0})`),
            children: (
              <div className="muted results-note">
                {p.result
                  ? t(`${p.result.library_size} 个资产中 ${p.result.total} 个符合筛选 · 排序：阻断差异 → 修改成本 → 相似度 · ${p.result.encoder === "bge" ? "BGE-M3 语义检索" : "轻量离线检索"}`,
                      `${p.result.total} of ${p.result.library_size} assets match the filters · ranked by blocking differences → change cost → similarity · ${p.result.encoder === "bge" ? "BGE-M3 semantic search" : "offline text search"}`)
                  : t("运行检索后对资产库排序。", "Run a search to rank the asset library.")}
              </div>
            ),
          },
        ]}
      />

      <div className="cand-head">
        <span className="t">{t("候选场景", "Candidate scenarios")}</span>
        <span className="muted">{t("显示", "Show")}</span>
        <Select<Show>
          value={show}
          onChange={setShow}
          style={{ width: 106 }}
          popupMatchSelectWidth={false}
          options={[
            { value: "all", label: t("全部候选", "All candidates") },
            ...(Object.keys(LEVEL) as Level[]).map((k) => ({ value: k, label: levelLabel(k, lang) })),
          ]}
        />
        <span className="n">{p.result ? t(`${p.result.total} 个结果`, `${p.result.total} results`) : "—"}</span>
      </div>

      {p.error && <Alert type="error" showIcon title={p.error} className="search-error" />}
      <Table
        className="cand-table"
        size="small"
        bordered
        pagination={false}
        rowKey="asset_id"
        columns={columns}
        dataSource={rows}
        loading={p.searching}
        tableLayout="fixed"
        scroll={{ y: 384 }}
        locale={{
          emptyText: p.searching ? " " : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={p.result ? t("此筛选下没有候选", "No candidates for this filter") : t("选择场景或输入描述来检索资产库", "Select a scene or describe a scenario to search the asset library")} />
          ),
        }}
        rowSelection={{ selectedRowKeys: p.checked, onChange: (k) => p.onChecked(k as string[]), columnWidth: 47 }}
        rowClassName={(r) => (r.asset_id === p.activeKey ? "row-active" : "")}
        onRow={(r) => ({ onClick: () => p.onActivate(r.asset_id) })}
      />

      <div className="preview">
        <div className="sec-title">{t("所选资产预览", "Selected asset preview")}</div>
        {!c ? (
          <div className="pv-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("选择候选以预览场景和道路", "Pick a candidate to preview its scenario and road")} />
          </div>
        ) : (
          <div className="grid">
            <div className="pv-main">
              <div className="pv-link">
                <a href={urls.file(c, "scenario")} target="_blank" rel="noreferrer" title={c.xosc}>{basename(c.xosc)}</a>
                <span className="plus">+</span>
                {c.road.file_missing ? <span className="muted">{t("道路文件缺失", "Road file missing")}</span>
                  : <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr}>{basename(c.xodr)}</a>}
              </div>
              <Tabs
                size="small"
                items={[
                  { key: "xosc", label: t("场景（XOSC）", "Scenario (XOSC)"), children: scenarioKv },
                  {
                    key: "xodr",
                    label: t("道路（XODR）", "Road (XODR)"),
                    children: c.road.file_missing ? (
                      <div className="kv">
                        <span>{t("文件", "File")}</span><span>{t("缺失（仿真软件内置道路）", "Missing (simulator built-in road)")}</span>
                        <span>{t("道路类型", "Road type")}</span>
                        <span>{c.road.inferred_features.map((f) => roadFeatureLabel(f, lang)).join(", ") || t("未知", "Unknown")}{t("（由地图名推断）", " (from the map name)")}</span>
                      </div>
                    ) : (
                      <div className="kv">
                        <span>{t("文件", "File")}</span><span title={c.xodr}>{basename(c.xodr)}</span>
                        <span>{t("长度", "Length")}</span><span>{metres(c.road.total_length_m)}</span>
                        <span>{t("道路数", "Roads")}</span><span>{c.road.road_count}</span>
                        <span>{t("车道数", "Lanes")}</span><span>{c.road.lane_count}</span>
                        <span>{t("交叉口", "Junctions")}</span><span>{c.road.junction_count}</span>
                        <span>{t("几何", "Geometry")}</span><span>{Object.entries(c.road.geometry_types).map(([k, n]) => `${k} ${n}`).join(", ") || "—"}</span>
                      </div>
                    ),
                  },
                  {
                    key: "sim",
                    label: t("仿真预览", "Simulation preview"),
                    children: (
                      <div className="kv">
                        <span>{t("画面", "Frame")}</span><span>{c.has_frame ? t("已缓存的 esmini 画面", "Cached esmini frame") : t("尚未生成", "Not generated yet")}</span>
                        <span>{t("播放", "Playback")}</span><span>{c.compatibility === "playable" ? t("可播放", "Playable") : c.compatibility === "failed" ? t("播放失败", "Failed") : c.compatibility === "road_missing" ? t("道路文件缺失", "Road file missing") : t("未检测", "Not tested")}</span>
                        <span>{t("触发器", "Triggers")}</span><span>{c.scenario.trigger_count}</span>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
            <div className="pv-img">
              <PreviewPlayer key={`${c.asset_id}/${c.version_id}`} cand={c} esmini={p.esmini} onSettings={p.onSettings} />
            </div>
            <div className="pv-road">
              <div className="hd">
                {t("关联道路：", "Associated road: ")}{c.road.file_missing ? t("缺失", "missing")
                  : <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr}>{basename(c.xodr)}</a>}
              </div>
              <div className="img-empty road">
                <b>{metres(c.road.total_length_m)}</b>
                <span>{t(`${c.road.road_count} 条道路 · ${c.road.junction_count} 个交叉口`, `${c.road.road_count} roads · ${c.road.junction_count} junctions`)}</span>
              </div>
              <div className="kv" style={{ gridTemplateColumns: "72px 1fr", marginTop: 6, paddingLeft: 4, rowGap: 3 }}>
                <span>{facetLabel("function_type", lang)}</span><span>{listText(c.classification.function_type, lang)}</span>
                <span>{facetLabel("label_road_type", lang)}</span><span>{listText(c.classification.label_road_type, lang)}</span>
                <span>{facetLabel("label_target_type", lang)}</span><span>{listText(c.classification.label_target_type, lang)}</span>
              </div>
              <a className="small-link" href={urls.file(c, "road")} target="_blank" rel="noreferrer">
                {t("打开 XODR", "Open XODR")} <ArrowUpRight />
              </a>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
