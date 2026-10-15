import { NextResponse } from "next/server";
import { hasRunningJob, startJob } from "@/lib/jobs";
import { MAX_PROMPT_LENGTH } from "@/lib/settings";

export async function POST(request: Request) {
  const { topic } = await request.json().catch(() => ({ topic: "" }));
  const trimmedTopic = typeof topic === "string" ? topic.trim() : "";

  if (trimmedTopic.length < 3 || trimmedTopic.length > MAX_PROMPT_LENGTH) {
    return NextResponse.json(
      { error: `Prompt must be 3-${MAX_PROMPT_LENGTH} characters` },
      { status: 400 },
    );
  }
  if (hasRunningJob()) {
    return NextResponse.json({ error: "A video is already being generated" }, { status: 409 });
  }
  return NextResponse.json({ id: startJob(trimmedTopic).id });
}
