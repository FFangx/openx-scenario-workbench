import { useEffect, useState } from "react";
import { Alert, Button, Progress } from "antd";
import { StopOutlined } from "@ant-design/icons";
import type { Job } from "../api";
import { useT } from "../i18n";

const STAGES: Record<string, [string, string]> = {
  queued: ["准备中", "Preparing"],
  extracting: ["识别 PDF 场景", "Extracting PDF scenes"],
  expanding: ["展开场景文件", "Expanding archive"],
  parsing: ["解析场景与道路", "Parsing scenarios and roads"],
  saving: ["保存资产", "Saving assets"],
  classifying: ["生成分类标签", "Labelling"],
  downloading: ["下载规范文件", "Downloading schemas"],
  comparing: ["对比场景库检查结论", "Comparing library verdicts"],
  loading: ["读取素材库与检索索引", "Loading the library and search index"],
  ranking: ["找候选素材，模型同步判断", "Finding candidates; the model judges them meanwhile"],
  judging: ["等待模型判断剩余场景", "Waiting for the model on the remaining scenes"],
};

/** Live state of a background job: stage, count, current step, recent messages, stop. */
export function JobProgress({ job, onCancel, unit }: { job: Job; onCancel: () => void; unit: [string, string] }) {
  const { t } = useT();
  const [now, setNow] = useState(() => Date.now() / 1000);
  const running = job.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const stage = STAGES[job.stage] ? t(...STAGES[job.stage]) : job.stage;
  const finished: Record<string, string> = {
    completed: t("已完成", "Completed"), stopped: t("已停止", "Stopped"),
    failed: t("失败", "Failed"), interrupted: t("已中断", "Interrupted"),
  };
  const elapsed = Math.max(0, Math.round((job.finished ?? now) - job.started));
  const waiting = running ? Math.round(now - job.updated) : 0;

  return (
    <div className="job">
      <div className="job-head">
        <b>{running ? stage : finished[job.status]}</b>
        <span className="muted">
          {job.total && job.ranked != null && job.ranked < job.total
            ? t(`候选 ${job.ranked} / ${job.total} · 建议 ${job.done} / ${job.total}`, `Candidates ${job.ranked} / ${job.total} · suggested ${job.done} / ${job.total}`)
            : job.total ? t(`${job.done} / ${job.total} ${unit[0]}`, `${job.done} / ${job.total} ${unit[1]}`) : ""}
          {" · "}{t(`用时 ${elapsed} 秒`, `${elapsed}s`)}
        </span>
        {running && (
          <Button size="small" icon={<StopOutlined />} onClick={onCancel} disabled={job.cancelling}>
            {job.cancelling ? t("正在停止…", "Stopping…") : t("停止任务", "Stop task")}
          </Button>
        )}
      </div>
      {job.total > 0 && (
        <Progress percent={Math.round((job.done / job.total) * 100)} size="small"
          status={job.status === "failed" ? "exception" : running ? "active" : job.status === "completed" ? "success" : "normal"} />
      )}
      {running && job.current && <div className="job-current" title={job.current}>{job.current}</div>}
      {job.cancelling && running && (
        <div className="muted job-note">{t("停止会在当前步骤结束后生效；已保存的内容会保留。", "Stopping takes effect after the current step; saved work is kept.")}</div>
      )}
      {running && waiting >= 20 && (
        <div className="muted job-note">{job.stage === "loading"
          ? t("素材有新增或标签变化后，首次需要重新建立检索索引，可能要一两分钟。", "After assets or labels change, the search index is rebuilt once; this can take a minute or two.")
          : t(`当前步骤已等待 ${waiting} 秒，模型请求可能较慢。`, `The current step has waited ${waiting}s; model requests can be slow.`)}</div>
      )}
      {job.messages.length > 0 && (
        <pre className="job-log" aria-label={t("任务记录", "Job log")}>{job.messages.slice(-12).join("\n")}</pre>
      )}
      {job.error && <Alert type="error" showIcon title={job.error} />}
    </div>
  );
}
