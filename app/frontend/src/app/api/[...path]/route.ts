import { NextRequest, NextResponse } from "next/server";
import { getServerAuthState, getServerCurrentUser } from "@/lib/auth-server";

const BACKEND_URL = process.env.FLASK_API_URL || process.env.NEXT_PUBLIC_FLASK_API_URL ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5050" : "");
const UPSTREAM_TIMEOUT_MS = 120_000;

// These headers describe the browser → Next.js connection, not the new
// Next.js → Flask request.  Forwarding them can make Undici reject streamed
// POST/PUT requests (for example, due to a stale Content-Length or a
// Connection/Transfer-Encoding conflict), which surfaced as "Proxy fetch
// failed" even while GET requests continued to work.
const HOP_BY_HOP_REQUEST_HEADERS = [
  "connection",
  "keep-alive",
  "proxy-connection",
  "transfer-encoding",
  "te",
  "trailer",
  "upgrade",
  "expect",
  "content-length",
];

function extractEmailFromClaims(claims: Record<string, unknown> | null): string | undefined {
  if (!claims) return undefined;
  const raw = claims.email ?? claims.primary_email;
  if (typeof raw === "string" && raw.includes("@")) {
    return raw.trim().toLowerCase();
  }
  return undefined;
}

function routeNeedsVerifiedEmail(method: string, pathSegments: string[]): boolean {
  const rel = pathSegments[0] === "v1" ? pathSegments.slice(1) : pathSegments;
  if (rel.length === 0) return false;
  if (rel[0] === "auth" && rel[1] === "me") return true;
  if (rel[0] === "lessons" || rel[0] === "curation") return true;
  if (rel[0] === "questions" && (rel[2] === "classification" || method.toUpperCase() === "DELETE")) {
    return true;
  }
  return false;
}

function isUpstreamSelfAuthenticated(pathSegments: string[], req: NextRequest): boolean {
  const rel = pathSegments[0] === "v1" ? pathSegments.slice(1) : pathSegments;
  if (rel.length === 0) return false;
  if (rel[0] === "images") return true;
  if (rel[0] === "notifications" && rel[1] === "cron" && rel[2] === "dispatch") return true;
  if (
    rel[0] === "lessons" &&
    rel.length === 3 &&
    rel[2] === "stream" &&
    Boolean(req.nextUrl.searchParams.get("st"))
  ) {
    return true;
  }
  return false;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const EDGE_RATE_WINDOW_MS = 60_000;
const EDGE_MAX_KEYS = 5_000;
const edgeRateBuckets = new Map<string, number[]>();

function isValidProxyPath(pathSegments: string[]): boolean {
  if (!Array.isArray(pathSegments) || pathSegments.length === 0 || pathSegments.length > 16) {
    return false;
  }
  return pathSegments.every((seg) => {
    if (!seg || seg === "." || seg === "..") return false;
    if (seg.includes("/") || seg.includes("\\") || seg.includes("..") || seg.includes("\0")) return false;
    const lower = seg.toLowerCase();
    return !lower.includes("%2e") && !lower.includes("%2f") && !lower.includes("%5c");
  });
}

function isCrossSiteMutation(req: NextRequest): boolean {
  if (!MUTATING_METHODS.has(req.method.toUpperCase())) return false;
  const secFetchSite = req.headers.get("sec-fetch-site");
  if (secFetchSite && secFetchSite.toLowerCase() === "cross-site") {
    return true;
  }
  const origin = req.headers.get("origin");
  if (!origin) return false;
  if (origin === "null") return true;
  const expectedHost = (
    req.headers.get("x-forwarded-host")?.split(",")[0]?.trim() ||
    req.headers.get("host") ||
    req.nextUrl.host
  ).toLowerCase();
  try {
    return new URL(origin).host.toLowerCase() !== expectedHost;
  } catch {
    return true;
  }
}

function resolveEdgeRateBucket(req: NextRequest, pathSegments: string[]): { bucket: string; limit: number } | null {
  const rel = pathSegments[0] === "v1" ? pathSegments.slice(1) : pathSegments;
  const method = req.method.toUpperCase();
  if (method === "POST") {
    if (rel[0] === "questions" && rel[2] === "ask_ai") return { bucket: "ask_ai", limit: 30 };
    if (rel[0] === "ai" && (rel[1] === "preceptor_focus" || rel[1] === "synthesize_explanation")) {
      return { bucket: `ai_${rel[1]}`, limit: 30 };
    }
    if (rel[0] === "plan" && rel[1] === "prescribe") return { bucket: "plan_prescribe", limit: 30 };
    if (
      rel[0] === "osce" &&
      rel[1] === "sessions" &&
      (rel[3] === "interact" || rel[3] === "dispatch_speech" || rel[3] === "finish")
    ) {
      return { bucket: "osce_ai", limit: 35 };
    }
  } else if (method === "GET" && rel[0] === "search" && req.nextUrl.searchParams.get("semantic") === "true") {
    return { bucket: "semantic_search", limit: 45 };
  }
  return null;
}

function checkEdgeRateLimit(req: NextRequest, pathSegments: string[]): number | null {
  const spec = resolveEdgeRateBucket(req, pathSegments);
  if (!spec) return null;
  const clientIp = (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip") ||
    "local"
  ).slice(0, 64);
  const key = `${spec.bucket}:${clientIp}`;
  const now = Date.now();
  const cutoff = now - EDGE_RATE_WINDOW_MS;
  let timestamps = edgeRateBuckets.get(key);
  if (!timestamps) {
    if (edgeRateBuckets.size >= EDGE_MAX_KEYS) {
      const oldestKey = edgeRateBuckets.keys().next().value;
      if (oldestKey !== undefined) edgeRateBuckets.delete(oldestKey);
    }
    timestamps = [];
    edgeRateBuckets.set(key, timestamps);
  }
  while (timestamps.length > 0 && timestamps[0] <= cutoff) {
    timestamps.shift();
  }
  if (timestamps.length >= spec.limit) {
    return Math.max(1, Math.ceil((timestamps[0] + EDGE_RATE_WINDOW_MS - now) / 1000));
  }
  timestamps.push(now);
  return null;
}

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const requestId = crypto.randomUUID();
  const proxySecret = process.env.FLASK_API_PROXY_SECRET;
  if (!BACKEND_URL) {
    console.error("[PROXY] FLASK_API_URL is not configured on the server.");
    return new NextResponse(
      JSON.stringify({ error: "Server configuration error: missing backend URL" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
  if (!proxySecret) {
    console.error("[PROXY] FLASK_API_PROXY_SECRET is not configured on the server.");
    return new NextResponse(
      JSON.stringify({ error: "Server configuration error: missing internal proxy secret" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  const { path } = await params;
  if (!isValidProxyPath(path)) {
    return NextResponse.json({ error: "Invalid API path" }, { status: 400 });
  }
  if (isCrossSiteMutation(req)) {
    return NextResponse.json({ error: "Cross-site request blocked" }, { status: 403 });
  }
  const retryAfterSec = checkEdgeRateLimit(req, path);
  if (retryAfterSec !== null) {
    return NextResponse.json(
      { error: "Muitas requisições em pouco tempo. Tente novamente em instantes.", code: "RATE_LIMIT_EXCEEDED" },
      { status: 429, headers: { "Retry-After": String(retryAfterSec) } }
    );
  }

  const targetUrl = `${BACKEND_URL}/api/${path.join("/")}${req.nextUrl.search}`;

  const selfAuth = isUpstreamSelfAuthenticated(path, req);
  const { getToken, sessionClaims } = await getServerAuthState();
  const token = await getToken();

  if (!token && !selfAuth && req.method.toUpperCase() !== "OPTIONS") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const headers = new Headers(req.headers);
  headers.delete("host");
  for (const header of HOP_BY_HOP_REQUEST_HEADERS) {
    headers.delete(header);
  }
  // Prevent backend from sending compressed data; let Next/Caddy handle compression.
  headers.delete("accept-encoding");

  // Remove untrusted or spoofable client-supplied auth headers
  headers.delete("authorization");
  headers.delete("x-internal-proxy-token");
  headers.delete("x-request-id");
  headers.delete("x-user-email");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
    const claimEmail = extractEmailFromClaims(sessionClaims);
    if (claimEmail) {
      headers.set("X-User-Email", claimEmail);
    } else if (routeNeedsVerifiedEmail(req.method, path)) {
      try {
        const user = await getServerCurrentUser();
        const verifiedPrimary =
          user?.primaryEmailAddress?.verification?.status === "verified"
            ? user.primaryEmailAddress.emailAddress
            : undefined;
        const verifiedFallback = user?.emailAddresses?.find(
          (addr) => addr.verification?.status === "verified"
        )?.emailAddress;
        const email = verifiedPrimary || verifiedFallback;
        if (email) {
          headers.set("X-User-Email", email);
        }
      } catch {
        // Non-blocking if currentUser fails
      }
    }
  }

  headers.set("X-Internal-Proxy-Token", proxySecret);
  headers.set("X-Request-ID", requestId);

  try {
    const requestOptions: RequestInit = {
      method: req.method,
      headers,
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    };
    if (req.method !== "GET" && req.method !== "HEAD" && req.body) {
      requestOptions.body = req.body;
      (requestOptions as RequestInit & { duplex?: string }).duplex = "half";
    }

    const response = await fetch(targetUrl, requestOptions);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");
    responseHeaders.set("X-Request-ID", response.headers.get("X-Request-ID") || requestId);

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    console.error(`[PROXY] request_id=${requestId} upstream failure:`, message);
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return new NextResponse(JSON.stringify({
      error: timedOut ? "Backend request timed out" : "Proxy fetch failed",
      request_id: requestId,
    }), {
      status: timedOut ? 504 : 502,
      headers: { "Content-Type": "application/json", "X-Request-ID": requestId },
    });
  }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
