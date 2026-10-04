// Polls a background job until it leaves "running"; the server owns the work, the page only watches.
import { useEffect, useRef, useState } from "react";
import { api, type Job } from "./api";

export function useJob(initial: Job | null, onFinish?: (job: Job) => void, interval = 1000) {
  const [job, setJob] = useState<Job | null>(initial);
  const finish = useRef(onFinish);
  finish.current = onFinish;

  useEffect(() => setJob(initial), [initial]);

  const id = job?.status === "running" ? job.id : null;
  useEffect(() => {
    if (!id) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      api.job(id).then((next) => {
        if (stopped) return;
        setJob(next);
        if (next.status !== "running") finish.current?.(next);
      }).catch(() => undefined);
    }, interval);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [id, interval]);

  const cancel = () => job && api.cancelJob(job.id).then(setJob).catch(() => undefined);
  return { job, setJob, cancel };
}
