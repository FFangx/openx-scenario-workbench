import { useState } from "react";
import { App, Button, Form, Image, Input, Select, Table, Tabs, Tag, type TableColumnsType } from "antd";
import { CheckCircleFilled, CloseOutlined, FileOutlined, FileTextOutlined, SearchOutlined } from "@ant-design/icons";
import { ArrowUpRight } from "./ArrowUpRight";
import { CANDIDATES, DEFAULT_FILTERS, FILTER_OPTIONS, ROADS, type Candidate, type Match } from "../data/mock";
import { roadPreview, simPreview } from "../lib/illustrations";

export const MATCH_CLASS: Record<Match, "direct" | "modify" | "not"> = {
  "Direct reuse": "direct",
  "Modify and reuse": "modify",
  "Not reusable": "not",
};

type Show = "all" | Match;

interface Props {
  query: string;
  onQuery: (q: string) => void;
  filters: Record<string, string>;
  onFilters: (f: Record<string, string>) => void;
  activeKey: string;
  onActivate: (key: string) => void;
  checked: string[];
  onChecked: (keys: string[]) => void;
  active: Candidate;
}

export function SearchPanel(p: Props) {
  const [show, setShow] = useState<Show>("all");
  const [tab, setTab] = useState("search");
  const { message } = App.useApp();

  const rows = CANDIDATES.map((c, i) => ({ ...c, idx: i + 1 })).filter((c) => show === "all" || c.match === show);

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
          <a onClick={(e) => e.stopPropagation()}>
            <FileOutlined />
            {c.xosc}
          </a>
          <a onClick={(e) => e.stopPropagation()}>
            <FileTextOutlined />+ {c.xodr}
          </a>
        </div>
      ),
    },
    { title: "Description", dataIndex: "desc", width: 120, render: (d: string) => <span className="desc">{d}</span> },
    ...(["sem", "scen", "road"] as const).map((k) => ({
      title: (
        <>
          {{ sem: "Semantic", scen: "Scenario", road: "Road" }[k]}
          <br />
          similarity
        </>
      ),
      dataIndex: k,
      width: 63,
      render: (v: number, c: Candidate) => <span className={`score${c.match === "Direct reuse" ? " good" : ""}`}>{v.toFixed(2)}</span>,
    })),
    {
      title: (
        <>
          Estimated
          <br />
          change cost
        </>
      ),
      dataIndex: "cost",
      width: 78,
      render: (v: string) => <span className={`cost-cell ${v}`}>{v}</span>,
    },
    {
      title: "Match",
      dataIndex: "match",
      render: (m: Match) => <Tag className={`mtag ${MATCH_CLASS[m]}`}>{m}</Tag>,
    },
  ];

  const filterForm = (
    <Form layout="vertical" size="small" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 12 }}>
      {Object.entries(FILTER_OPTIONS).map(([k, opts]) => (
        <Form.Item key={k} label={k} style={{ marginBottom: 8 }}>
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

  const searchTab = (
    <>
      <div className="search-row">
        <Input
          prefix={<SearchOutlined />}
          allowClear
          value={p.query}
          onChange={(e) => p.onQuery(e.target.value)}
          onPressEnter={() => message.success(`Searched 24 assets for “${p.query || "*"}”`)}
          placeholder="Describe the scenario, e.g. cut in lane support"
        />
        <Button type="primary" onClick={() => message.success(`Searched 24 assets for “${p.query || "*"}”`)}>
          Search
        </Button>
        <Button
          onClick={() => {
            p.onQuery("");
            p.onFilters(DEFAULT_FILTERS);
            setShow("all");
          }}
        >
          Reset
        </Button>
      </div>
      <div className="chips">
        {Object.entries(p.filters).map(([k, v]) => (
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
            {k}
            <b>{v}</b>
          </Tag>
        ))}
      </div>
    </>
  );

  const c = p.active;
  const road = ROADS[c.xodr];

  return (
    <section className="panel search">
      <div className="ph">
        <span className="n">2</span>Asset library search and candidate scenarios
        <span className="meta">
          Library status
          <span className="online">
            <CheckCircleFilled /> Online
          </span>
          Last sync <span className="ts">2025-04-28&nbsp; 10:24</span>
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
            label: `Results (24)`,
            children: <div className="muted">24 assets matched · ranked by blocking differences → change cost → relevance</div>,
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
            { value: "Direct reuse", label: "Direct reuse" },
            { value: "Modify and reuse", label: "Modify and reuse" },
            { value: "Not reusable", label: "Not reusable" },
          ]}
        />
        <span className="n">24 results</span>
      </div>

      <Table
        className="cand-table"
        size="small"
        bordered
        pagination={false}
        rowKey="key"
        columns={columns}
        dataSource={rows}
        tableLayout="fixed"
        rowSelection={{ selectedRowKeys: p.checked, onChange: (k) => p.onChecked(k as string[]), columnWidth: 47 }}
        rowClassName={(r) => (r.key === p.activeKey ? "row-active" : "")}
        onRow={(r) => ({ onClick: () => p.onActivate(r.key) })}
      />

      <div className="preview">
        <div className="sec-title">Selected asset preview</div>
        <div className="grid">
          <div className="pv-main">
          <div className="pv-link">
            <a>{c.xosc}</a>
            <span className="plus">+</span>
            <a>{c.xodr}</a>
          </div>
          <Tabs
            size="small"
            items={[
              {
                key: "xosc",
                label: "Scenario (XOSC)",
                children: (
                  <div className="kv">
                    <span>File</span><span>{c.xosc}</span>
                    <span>Version</span><span>{c.ver}</span>
                    <span>Description</span><span>{c.desc}</span>
                    <span>Entities</span><span>Ego, Cut-in vehicle, Other traffic</span>
                    <span>Duration</span><span>{c.dur}</span>
                    <span>Parameterization</span><span>Speed, time gap, lateral offset</span>
                  </div>
                ),
              },
              {
                key: "xodr",
                label: "Road (XODR)",
                children: (
                  <div className="kv">
                    <span>File</span><span>{c.xodr}</span>
                    <span>Length</span><span>{road.length}</span>
                    <span>Lanes</span><span>{road.lanes}</span>
                    <span>Road type</span><span>{road.type}</span>
                    <span>Junctions</span><span>0</span>
                  </div>
                ),
              },
              {
                key: "sim",
                label: "Simulation preview",
                children: (
                  <div className="kv">
                    <span>Engine</span><span>esmini 2.37</span>
                    <span>Frames</span><span>cached · 150</span>
                    <span>Step</span><span>0.1 s</span>
                  </div>
                ),
              },
            ]}
          />
          </div>
          <div className="pv-img">
            <Image src={simPreview()} alt="Simulation preview" preview={{ mask: "View larger" }} />
            <a className="small-link">
              View larger <ArrowUpRight />
            </a>
          </div>
          <div className="pv-road">
            <div className="hd">
              Associated road: <a>{c.xodr}</a>
            </div>
            <div className="pv-img">
              <img src={roadPreview(road.lanesEach, road.rural)} alt="Road" />
            </div>
            <div className="kv" style={{ gridTemplateColumns: "72px 1fr", marginTop: 6, paddingLeft: 4, rowGap: 3 }}>
              <span>Length</span><span>{road.length}</span>
              <span>Lanes</span><span>{road.lanes}</span>
              <span>Road type</span><span>{road.type}</span>
            </div>
            <a className="small-link">
              View in map <ArrowUpRight />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
