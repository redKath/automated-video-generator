export type Job = {
  id: string;
  topic: string;
  status: "running" | "done" | "error";
  log: string[];
  videoSlug?: string;
  error?: string;
};

// Line prefixes printed by ../make_video.py that the web app parses.
export const SCENE_LOG_PREFIX = "scene ";
export const DONE_LOG_PREFIX = "done: ";
