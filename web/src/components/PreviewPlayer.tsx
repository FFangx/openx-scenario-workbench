import { useEffect, useRef, useState } from "react";
import { Alert, Button, Collapse, Image, Tooltip } from "antd";
import { CameraOutlined, CaretRightOutlined, StopOutlined } from "@ant-design/icons";
import { api, urls, type Candidate, type PreviewStatus } from "../api";
import { useT } from "../i18n";
import { ArrowUpRight } from "./ArrowUpRight";

const ACTIVE = new Set(["starting", "running"]);

/** Real esmini frames only: a live MJPEG stream while playing, otherwise the saved still frame of this exact version. */
export function PreviewPlayer({ cand, esmini, onSettings }: { cand: Candidate; esmini: boolean; onSettings: () => void }) {
  const { t } = useT();
  const [status, setStatus] = useState<PreviewStatus>({ state: "idle" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [frameStamp, setFrameStamp] = useState(0);
  const [hasFrame, setHasFrame] = useState(cand.has_frame);
  const mine = status.asset_id === cand.asset_id && status.version_id === cand.version_id;
  const live = mine && ACTIVE.has(status.state);
  const wasLive = useRef(false);

  useEffect(() => {
    setHasFrame(cand.has_frame);
    setError(null);
    api.previewStatus().then(setStatus).catch(() => undefined);
  }, [cand.asset_id, cand.version_id, cand.has_frame]);

  // Poll while this candidate plays; when it stops, show the still frame it saved.
  useEffect(() => {
    if (!live) {
      if (wasLive.current && mine && (status.frames ?? 0) > 0) {
        setHasFrame(true);
        setFrameStamp(Date.now());
      }
      wasLive.current = false;
      return;
    }
    wasLive.current = true;
    const timer = window.setInterval(() => api.previewStatus().then(setStatus).catch(() => undefined), 1000);
    return () => window.clearInterval(timer);
  }, [live, mine, status.frames]);

  const start = async (duration: number) => {
    if (!cand.version_id) return;
    setBusy(true);
    setError(null);
    try {
      setStatus(await api.previewStart(cand.asset_id, cand.version_id, duration));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const stop = () => api.previewStop().then(setStatus).catch(() => undefined);

  const disabledReason = !esmini ? t("尚未找到 esmini，可在设置 → 本机服务中选择安装位置。", "esmini was not found; choose it under Settings → Local service.")
    : !cand.version_id ? t("此资产没有已保存的版本。", "This asset has no stored version.") : null;

  return (
    <div className="player">
      {live && status.stream_url ? (
        <img className="live" src={status.stream_url} alt={t("实时仿真画面", "Live esmini simulation")} />
      ) : hasFrame ? (
        <Image src={urls.frame(cand, frameStamp)} alt={t("仿真画面", "Simulation frame")} />
      ) : (
        <div className="img-empty">
          <b>{t("尚无仿真画面", "No simulation frame")}</b>
          <span>{t("播放仿真或生成缩略图后会保存这个版本的真实画面。", "Play the simulation or capture a frame to save a real image of this version.")}</span>
        </div>
      )}
      <div className="player-bar">
        <Tooltip title={disabledReason}>
          <Button size="small" type="primary" icon={<CaretRightOutlined />} loading={busy} disabled={!!disabledReason || live} onClick={() => start(30)}>{t("播放仿真", "Play")}</Button>
        </Tooltip>
        <Button size="small" icon={<StopOutlined />} disabled={!live} onClick={stop} aria-label={t("停止", "Stop")}>{t("停止", "Stop")}</Button>
        <Tooltip title={disabledReason ?? t("渲染约 2 秒，保存一张真实画面", "Renders about 2 s and saves a real frame")}>
          <Button size="small" icon={<CameraOutlined />} disabled={!!disabledReason || live || busy} onClick={() => start(2)} aria-label={t("生成缩略图", "Capture frame")} />
        </Tooltip>
        {!esmini && <a className="small-link" onClick={onSettings}>{t("设置", "Settings")}</a>}
        {hasFrame && !live && <a className="small-link" href={urls.frame(cand, frameStamp)} target="_blank" rel="noreferrer">{t("大图", "Larger")} <ArrowUpRight /></a>}
      </div>
      {live && <div className="muted player-note">{t(`正在播放 · 已生成 ${status.frames ?? 0} 帧真实画面`, `Playing · ${status.frames ?? 0} rendered frames`)}</div>}
      {mine && status.state === "finished" && !live && (
        <div className="muted player-note">{(status.frames ?? 0) > 0 ? t("预览已结束，可以重新播放。", "Preview finished. You can play it again.") : t("预览结束，但没有生成画面。", "Preview ended without producing a frame.")}</div>
      )}
      {mine && status.snapshot_error && <Alert type="warning" showIcon title={t("仿真画面已生成，但缩略图未能保存。请检查数据目录的写入权限。", "Simulation rendered, but its still frame could not be saved. Check data-folder write access.")} />}
      {(error || (mine && status.state === "failed")) && (
        <Collapse size="small" className="player-error" items={[{
          key: "e",
          label: <span className="st bad">{t("这个场景暂时无法播放", "This scenario could not play")}</span>,
          children: <pre className="json-view">{[error ?? status.error, status.log].filter(Boolean).join("\n\n")}</pre>,
        }]} />
      )}
    </div>
  );
}
