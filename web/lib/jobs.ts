import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { DONE_LOG_PREFIX, type Job } from "./types";

export const PROJECT_ROOT = path.resolve(process.cwd(), "..");

// Survives dev-server module reloads.
const globalStore = globalThis as unknown as { jobs?: Map<string, Job> };
const jobs = (globalStore.jobs ??= new Map<string, Job>());

export const getJob = (id: string) => jobs.get(id);
export const hasRunningJob = () => [...jobs.values()].some((job) => job.status === "running");

// "done: C:\...\out\my-topic.mp4 (33.2s)" -> "my-topic"
function parseVideoSlug(doneLine: string) {
  const videoPath = doneLine.slice(DONE_LOG_PREFIX.length).split(" (")[0];
  return path.basename(videoPath, ".mp4");
}

export function startJob(topic: string): Job {
  const job: Job = { id: randomUUID(), topic, status: "running", log: [] };
  jobs.set(job.id, job);

  const pythonProcess = spawn("python", ["make_video.py", topic], {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
  });

  const appendOutputLinesToLog = (outputChunk: Buffer) =>
    outputChunk
      .toString()
      .split(/\r?\n/)
      .filter(Boolean)
      .forEach((line) => job.log.push(line));
  pythonProcess.stdout.on("data", appendOutputLinesToLog);
  pythonProcess.stderr.on("data", appendOutputLinesToLog);

  pythonProcess.on("close", (exitCode) => {
    const doneLine = job.log.find((line) => line.startsWith(DONE_LOG_PREFIX));
    if (exitCode === 0 && doneLine) {
      job.videoSlug = parseVideoSlug(doneLine);
      job.status = "done";
    } else {
      job.status = "error";
      job.error = job.log.at(-1) ?? `exited with code ${exitCode}`;
    }
  });
  pythonProcess.on("error", (spawnError) => {
    job.status = "error";
    job.error = spawnError.message;
  });

  return job;
}
