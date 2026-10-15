import { NextResponse } from "next/server";
import { getJob } from "@/lib/jobs";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const job = getJob((await params).id);
  if (!job) return NextResponse.json({ error: "Unknown job" }, { status: 404 });
  return NextResponse.json(job);
}
