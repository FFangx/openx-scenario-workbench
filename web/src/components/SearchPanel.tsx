import { useState } from "react";
import { Alert, Button, Empty, Form, Image, Input, Select, Table, Tabs, Tag, Tooltip, type TableColumnsType } from "antd";
import { CheckCircleFilled, CloseCircleFilled, CloseOutlined, FileOutlined, FileTextOutlined, SearchOutlined } from "@ant-design/icons";
import { basename, FACET_LABEL, LEVEL, urls, type Candidate, type Level, type Library, type SearchResponse } from "../api";
import { ArrowUpRight } from "./ArrowUpRight";

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
  activeKey: string | null;
  onActivate: (key: string) => void;
  checked: string[];
  onChecked: (keys: string[]) => void;
  active: Candidate | null;
}

const listText = (v: string | string[] | undefined) => (Array.isArray(v) ? v.join(", ") : v) || "—";
const metres = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);

export function SearchPanel(p: Props) {
  const [show, setShow] = useState<Show>("all");
  const [tab, setTab] = useState("search");

  const rows = (p.result?.results ?? []).map((c, i) => ({ ...c, idx: i + 1 })).filter((c) => show === "all" || c.level === show);

  const columns: TableColumnsType<Candidate & { idx: number }> = [
    { title: "#", dataIndex: "idx", width: 30, align: "center" },
    Table.SELECTION_COLUMN,
    {
      title: (
        <>
          Scenario pair
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
          <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr} onClick={(e) => e.stopPropagation()}>
            <FileTextOutlined />
            <span className="fn">+ {basename(c.xodr)}</span>
          </a>
        </div>
      ),
    },
    {
      title: "Description",
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
          {{ semantic: "Semantic", scenario: "Scenario", road: "Road" }[k]}
          <br />
          similarity
        </>
      ),
      key: k,
      width: 63,
      render: (_: unknown, c: Candidate) => <span className={`score${c.level === "direct" ? " good" : ""}`}>{c.scores[k].toFixed(2)}</span>,
    })),
    {
      title: (
        <Tooltip title="Relative effort score from the structural comparison, not working hours">
          Estimated
          <br />
          change cost
        </Tooltip>
      ),
      key: "cost",
      width: 78,
      render: (_, c) => <span className="cost-cell">{c.change_cost == null ? "—" : c.change_cost.toFixed(1)}</span>,
    },
    {
      title: "Match",
      key: "match",
      render: (_, c) => <Tag className={`mtag ${LEVEL[c.level].cls}`}>{LEVEL[c.level].label}</Tag>,
    },
  ];

  const facets = p.library?.facets ?? {};
  const filterForm = (
    <Form layout="vertical" size="small" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", columnGap: 12 }}>
      {Object.entries(facets).map(([k, opts]) => (
        <Form.Item key={k} label={FACET_LABEL[k] ?? k} style={{ marginBottom: 8 }}>
          <Select
            allowClear
            placeholder="Any"
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
          placeholder="Add keywords to refine the selected scene"
        />
        <Button type="primary" onClick={p.onSearch} disabled={!p.canSearch} loading={p.searching}>
          Search
        </Button>
        <Button onClick={p.onReset}>Reset</Button>
      </div>
      <div className="chips">
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
              {FACET_LABEL[k] ?? k}
              <b>{v}</b>
            </Tag>
          ))
        ) : (
          <span className="chips-empty">
            No filters · all {p.library?.asset_count ?? "…"} assets are ranked.{" "}
            <a onClick={() => setTab("filters")}>Add filters</a>
          </span>
        )}
      </div>
    </>
  );

  const c = p.active;
  const scenarioKv = c && (
    <div className="kv">
      <span>File</span><span title={c.xosc}>{basename(c.xosc)}</span>
      <span>Version</span><span>{c.version_number ? `v${c.version_number}` : "—"}</span>
      <span>Description</span><span>{c.description || c.title}</span>
      <span>Entities</span><span>{c.scenario.entities.map((e) => e.category ?? e.kind).join(", ") || "—"}</span>
      <span>Actions</span><span>{c.scenario.actions.join(", ") || "—"}</span>
      <span>Parameterization</span><span>{c.scenario.parameters.join(", ") || "None declared"}</span>
    </div>
  );

  return (
    <section className="panel search">
      <div className="ph">
        <span className="n">2</span>Asset library search and candidate scenarios
        <span className="meta">
          Library status
          {p.online === false ? (
            <span className="online off">
              <CloseCircleFilled /> Offline
            </span>
          ) : (
            <span className="online">
              <CheckCircleFilled /> {p.online ? "Online" : "…"}
            </span>
          )}
          Last import <span className="ts">{p.library?.last_import ? p.library.last_import.slice(0, 16).replace("T", "  ") : "—"}</span>
        </span>
      </div>

      <Tabs
        className="mid-tabs"
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: "search", label: "Search", children: searchTab },
          { key: "filters", label: "Filters", children: filterForm },
          {
            key: "results",
            label: `Results (${p.result?.total ?? 0})`,
            children: (
              <div className="muted results-note">
                {p.result
                  ? `${p.result.total} of ${p.result.library_size} assets match the filters · ranked by blocking differences → change cost → similarity · ${p.result.encoder === "bge" ? "BGE-M3 semantic search" : "offline text search"}`
                  : "Run a search to rank the asset library."}
              </div>
            ),
          },
        ]}
      />

      <div className="cand-head">
        <span className="t">Candidate scenarios</span>
        <span className="muted">Show</span>
        <Select<Show>
          value={show}
          onChange={setShow}
          style={{ width: 106 }}
          popupMatchSelectWidth={false}
          options={[
            { value: "all", label: "All candidates" },
            ...(Object.keys(LEVEL) as Level[]).map((k) => ({ value: k, label: LEVEL[k].label })),
          ]}
        />
        <span className="n">{p.result ? `${p.result.total} results` : "—"}</span>
      </div>

      {p.error && <Alert type="error" showIcon message={p.error} className="search-error" />}
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
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={p.result ? "No candidates for this filter" : "Select a scene to search the asset library"} />
          ),
        }}
        rowSelection={{ selectedRowKeys: p.checked, onChange: (k) => p.onChecked(k as string[]), columnWidth: 47 }}
        rowClassName={(r) => (r.asset_id === p.activeKey ? "row-active" : "")}
        onRow={(r) => ({ onClick: () => p.onActivate(r.asset_id) })}
      />

      <div className="preview">
        <div className="sec-title">Selected asset preview</div>
        {!c ? (
          <div className="pv-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Pick a candidate to preview its scenario and road" />
          </div>
        ) : (
          <div className="grid">
            <div className="pv-main">
              <div className="pv-link">
                <a href={urls.file(c, "scenario")} target="_blank" rel="noreferrer" title={c.xosc}>{basename(c.xosc)}</a>
                <span className="plus">+</span>
                <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr}>{basename(c.xodr)}</a>
              </div>
              <Tabs
                size="small"
                items={[
                  { key: "xosc", label: "Scenario (XOSC)", children: scenarioKv },
                  {
                    key: "xodr",
                    label: "Road (XODR)",
                    children: (
                      <div className="kv">
                        <span>File</span><span title={c.xodr}>{basename(c.xodr)}</span>
                        <span>Length</span><span>{metres(c.road.total_length_m)}</span>
                        <span>Roads</span><span>{c.road.road_count}</span>
                        <span>Lanes</span><span>{c.road.lane_count}</span>
                        <span>Junctions</span><span>{c.road.junction_count}</span>
                        <span>Geometry</span><span>{Object.entries(c.road.geometry_types).map(([k, n]) => `${k} ${n}`).join(", ") || "—"}</span>
                      </div>
                    ),
                  },
                  {
                    key: "sim",
                    label: "Simulation preview",
                    children: (
                      <div className="kv">
                        <span>Frame</span><span>{c.has_frame ? "Cached esmini frame" : "Not generated yet"}</span>
                        <span>Playback</span><span>{c.compatibility === "playable" ? "Playable" : c.compatibility === "failed" ? "Failed" : "Not tested"}</span>
                        <span>Triggers</span><span>{c.scenario.trigger_count}</span>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
            <div className="pv-img">
              {c.has_frame ? (
                <Image src={urls.frame(c)} alt="Simulation frame" />
              ) : (
                <div className="img-empty">
                  <b>No simulation frame</b>
                  <span>Generate one in the classic workbench (tray menu → 打开经典工作台).</span>
                </div>
              )}
              {c.has_frame && (
                <a className="small-link" href={urls.frame(c)} target="_blank" rel="noreferrer">
                  View larger <ArrowUpRight />
                </a>
              )}
            </div>
            <div className="pv-road">
              <div className="hd">
                Associated road: <a href={urls.file(c, "road")} target="_blank" rel="noreferrer" title={c.xodr}>{basename(c.xodr)}</a>
              </div>
              <div className="img-empty road">
                <b>{metres(c.road.total_length_m)}</b>
                <span>{c.road.road_count} roads · {c.road.junction_count} junctions</span>
              </div>
              <div className="kv" style={{ gridTemplateColumns: "72px 1fr", marginTop: 6, paddingLeft: 4, rowGap: 3 }}>
                <span>Function</span><span>{listText(c.classification.function_type)}</span>
                <span>Road type</span><span>{listText(c.classification.label_road_type)}</span>
                <span>Target</span><span>{listText(c.classification.label_target_type)}</span>
              </div>
              <a className="small-link" href={urls.file(c, "road")} target="_blank" rel="noreferrer">
                Open XODR <ArrowUpRight />
              </a>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
