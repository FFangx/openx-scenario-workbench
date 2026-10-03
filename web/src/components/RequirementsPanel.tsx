import { useMemo, useState } from "react";
import { App, Button, Dropdown, Select, Tabs } from "antd";
import { EllipsisOutlined, ExportOutlined } from "@ant-design/icons";
import { DOCUMENT, SCENES, type Scene } from "../data/mock";
import { docPage, evidenceFigure, pdfPage, sceneThumb } from "../lib/illustrations";

export function RequirementsPanel({ scene, onPick }: { scene: Scene; onPick: (id: number) => void }) {
  const [sort, setSort] = useState<"section" | "page">("section");
  const { message } = App.useApp();
  const ordered = useMemo(
    () => (sort === "section" ? SCENES : [...SCENES].sort((a, b) => b.p0 - a.p0)),
    [sort],
  );

  const list = (
    <div className="scenes" role="listbox" aria-label="Extracted scenes">
      {ordered.map((s) => (
        <button
          key={s.id}
          role="option"
          aria-selected={s.id === scene.id}
          className={`scene${s.id === scene.id ? " sel" : ""}`}
          onClick={() => onPick(s.id)}
        >
          <span className="num">{s.id}</span>
          <img src={sceneThumb(s.kind)} alt="" />
          <span className="tx">
            <div className="t">{s.title}</div>
            <div className="d">
              {s.req} – {s.desc}
            </div>
            <div className="p">
              Pages: <b>{s.pages}</b>
            </div>
          </span>
          <span className="c">
            {s.count} scene{s.count > 1 ? "s" : ""}
          </span>
        </button>
      ))}
    </div>
  );

  return (
    <section className="panel">
      <div className="ph">
        <span className="n">1</span>Requirements and extracted scenes
      </div>

      <div className="box pdfcard">
        <span className="pdf" aria-hidden>PDF</span>
        <div>
          <div className="t">{DOCUMENT.name}</div>
          <div className="m">
            Version {DOCUMENT.version}<i>|</i>{DOCUMENT.size}<i>|</i>{DOCUMENT.pages} pages
          </div>
        </div>
        <Dropdown
          trigger={["click"]}
          menu={{
            items: [
              { key: "replace", label: "Replace document" },
              { key: "rerun", label: "Re-run extraction" },
              { key: "history", label: "Revision history" },
            ],
            onClick: () => message.info("Wired to the extraction pipeline in phase 2"),
          }}
        >
          <Button className="more" type="text" icon={<EllipsisOutlined />} aria-label="Document actions" />
        </Dropdown>
      </div>

      <Tabs
        className="left-tabs"
        size="small"
        items={[
          { key: "scenes", label: `Extracted scenes (${SCENES.length})`, children: list },
          {
            key: "doc",
            label: "Document view",
            children: (
              <div className="docview">
                <img src={docPage(scene.sec, scene.id)} alt={`Page ${scene.p0}`} />
              </div>
            ),
          },
        ]}
        tabBarExtraContent={
          <Select
            size="small"
            value={sort}
            onChange={setSort}
            style={{ width: 106 }}
            options={[
              { value: "section", label: "Sort by section" },
              { value: "page", label: "Sort by page" },
            ]}
          />
        }
      />

      <div className="box evi">
        <div className="hd">
          <b>Selected source evidence</b>
          <a href="#" onClick={(e) => e.preventDefault()}>
            Open in document <ExportOutlined />
          </a>
        </div>
        <div className="pg">
          Pages <b>{scene.pages}</b>
        </div>
        <div className="bd">
          <img src={pdfPage(scene.p0, scene.id)} alt={`Page ${scene.p0}`} />
          <div className="x">
            <b>
              <i>{scene.sec.split(" ")[0]}</i>
              {scene.sec.slice(scene.sec.indexOf(" ") + 1)}
            </b>
            {scene.text}
            <div className="fig">
              Figure {scene.id} – {scene.fig}
            </div>
            <img src={evidenceFigure()} alt="" />
          </div>
        </div>
      </div>
    </section>
  );
}
