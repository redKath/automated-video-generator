import { stat, open } from "node:fs/promises";
import path from "node:path";
import { PROJECT_ROOT } from "@/lib/jobs";

// Serves out/<slug>.mp4 with Range support so the <video> element can seek.
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!/^[a-z0-9-]+$/.test(slug)) return new Response("Not found", { status: 404 });

  const filePath = path.join(PROJECT_ROOT, "out", `${slug}.mp4`);
  const fileSize = await stat(filePath).then((fileStats) => fileStats.size).catch(() => null);
  if (fileSize === null) return new Response("Not found", { status: 404 });

  const rangeMatch = /bytes=(\d*)-(\d*)/.exec(request.headers.get("range") ?? "");
  const start = rangeMatch?.[1] ? Number(rangeMatch[1]) : 0;
  const end = rangeMatch?.[2] ? Number(rangeMatch[2]) : fileSize - 1;

  const handle = await open(filePath);
  const buffer = Buffer.alloc(end - start + 1);
  await handle.read(buffer, 0, buffer.length, start);
  await handle.close();

  return new Response(buffer, {
    status: rangeMatch ? 206 : 200,
    headers: {
      "Content-Type": "video/mp4",
      "Accept-Ranges": "bytes",
      "Content-Length": String(buffer.length),
      ...(rangeMatch && { "Content-Range": `bytes ${start}-${end}/${fileSize}` }),
    },
  });
}
