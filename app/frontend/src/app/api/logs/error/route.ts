import { NextResponse } from "next/server";
import { readBoundedJson } from "@/lib/bounded-json";

export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 8 * 1024;

function safePath(value: unknown): string {
  if (typeof value !== "string") return "unknown";
  try {
    return new URL(value.slice(0, 2048)).pathname.slice(0, 512) || "/";
  } catch {
    return "unknown";
  }
}

export async function POST(request: Request) {
  const body = await readBoundedJson(request, MAX_BODY_BYTES);
  if (!body.ok) {
    return NextResponse.json({ error: body.error }, { status: body.status });
  }
  const data = body.data;

  const { error, info, url } = data as Record<string, unknown>;
  if (typeof error !== "string" || !error.trim()) {
    return NextResponse.json({ error: "error is required" }, { status: 400 });
  }

  const digest = info && typeof info === "object" && typeof (info as Record<string, unknown>).digest === "string"
    ? ((info as Record<string, unknown>).digest as string).slice(0, 128)
    : "";

  // Keep client telemetry on Vercel. Forwarding it to the study-data backend
  // made error reporting compete with requests that render the dashboard.
  console.error(JSON.stringify({
    event: "frontend_error",
    path: safePath(url),
    message: error.trim().slice(0, 1000),
    digest,
  }));

  return NextResponse.json({ success: true });
}
