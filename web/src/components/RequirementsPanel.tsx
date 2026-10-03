import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Dropdown, Empty, Select, Spin, Tabs } from "antd";
import { EllipsisOutlined, ExportOutlined } from "@ant-design/icons";
import { urls, type PdfDocument, type Scene } from "../api";

interface Props {
  projectId: string | null;
  doc: PdfDocument | null;
  scenes: Scene[];
  scene: Scene | null;
  onPick: (id: string) => void;
}

const pagesText = (p: Scene["pages"]) => (!p ? "—" : p[0] === p[1] ? `${p[0]}` : `${p[0]} – ${p[1]}`);
const sizeText = (b: number | null) => (b == null ? "—" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} KB`);
const sectionKey = (s: Scene) => s.section_id.split(".").map((n) => n.padStart(4, "0")).join(".");

export function RequirementsPanel({ projectId, doc, scenes, scene, onPick }: Props) {
  const [sort, setSort] = useState<"section" | "page">("section");
  const listRef = useRef<HTMLDivElement>(null);
  const ordered = useMemo(
    () =>
      [...scenes].sort((a, b) =>
        sort === "section" ? sectionKey(a).localeCompare(sectionKey(b)) : (a.pages?.[0] ?? 0) - (b.pages?.[0] ?? 0),
      ),
    [scenes, sort],
  );
  const number = useMemo(() => new Map(scenes.map((s, i) => [s.scene_id, i + 1])), [scenes]);

  useEffect(() => {
    listRef.current?.querySelector(".scene.sel")?.scrollIntoView({ block: "nearest" });
  }, [scene?.scene_id]);

  const thumb = (s: Scene) =>
    projectId && doc && s.source_region
      ? urls.page(projectId, doc.document_id, s.source_region.page, 220, s.source_region.clip)
      : undefined;

  const list = !doc ? (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No PDF in this project yet" />
  ) : !scenes.length ? (
    <div className="center-pad"><Spin /></div>
  ) : (
    <div className="scenes" role="listbox" aria-label="Extracted scenes" ref={listRef}>
      {ordered.map((s) => (
        <button
          key={s.scene_id}
          role="option"
          aria-selected={s.scene_id === scene?.scene_id}
          className={`scene${s.scene_id === scene?.scene_id ? " sel" : ""}`}
          onClick={() => onPick(s.scene_id)}
        >
          <span className="num">{number.get(s.scene_id)}</span>
          {thumb(s) ? <img src={thumb(s)} alt="" loading="lazy" /> : <span className="thumb-empty" />}
          <span className="tx">
            <div className="t">{s.title}</div>
            <div className="d">
              {s.section_id && `${s.section_id} – `}
              {s.preferred_text}
            </div>
            <div className="p">
              Pages: <b>{pagesText(s.pages)}</b>
            </div>
          </span>
          <span className={`c ${s.review_status}`}>{s.review_status === "confirmed" ? "Confirmed" : "To review"}</span>
        </button>
      ))}
    </div>
  );

  const page = scene?.pages?.[0];

  return (
    <section className="panel req">
      <div className="ph">
        <span className="n">1</span>Requirements and extracted scenes
      </div>

      <div className="box pdfcard">
        <span className="pdf" aria-hidden>PDF</span>
        <div className="pdf-meta">
          <div className="t" title={doc?.filename}>{doc?.filename ?? "No document"}</div>
          <div className="m">
            {doc ? (
              <>
                Imported {doc.imported_at.slice(0, 10)}<i>|</i>{sizeText(doc.size_bytes)}<i>|</i>{doc.page_count} pages
              </>
            ) : (
              "Import a PDF in the classic workbench (tray menu)"
            )}
          </div>
        </div>
        <Dropdown
          trigger={["click"]}
          disabled={!doc || !projectId}
          menu={{
            items: [{ key: "open", label: "Open PDF" }],
            onClick: () => projectId && doc && window.open(urls.pdf(projectId, doc.document_id), "_blank"),
          }}
        >
          <Button className="more" type="text" icon={<EllipsisOutlined />} aria-label="Document actions" />
        </Dropdown>
      </div>

      <Tabs
        className="left-tabs"
        size="small"
        items={[
          { key: "scenes", label: `Extracted scenes (${scenes.length})`, children: list },
          {
            key: "doc",
            label: "Document view",
            children:
              projectId && doc && page ? (
                <div className="docview">
                  <img src={urls.page(projectId, doc.document_id, page, 800)} alt={`Page ${page}`} />
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Select a scene" />
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
          {projectId && doc && page && (
            <a href={urls.pdf(projectId, doc.document_id, page)} target="_blank" rel="noreferrer">
              Open in document <ExportOutlined />
            </a>
          )}
        </div>
        <div className="pg">
          Pages <b>{pagesText(scene?.pages ?? null)}</b>
        </div>
        <div className="bd">
          {projectId && doc && page ? <img src={urls.page(projectId, doc.document_id, page, 260)} alt={`Page ${page}`} /> : <span className="page-empty" />}
          <div className="x">
            {scene ? (
              <>
                <b>
                  <i>{scene.section_id}</i>
                  {scene.title}
                </b>
                {scene.evidence.map((e, i) => (
                  <p key={i} className="src">
                    {e.source_text}
                  </p>
                ))}
              </>
            ) : (
              <span className="muted">Select a scene to see the cited source text.</span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
