export type BoundedJsonResult =
  | { ok: true; data: unknown }
  | { ok: false; status: 400 | 413; error: string };

/**
 * Lê o corpo JSON de uma Request respeitando o teto real de bytes no stream,
 * impedindo bypass de Content-Length via Transfer-Encoding: chunked.
 */
export async function readBoundedJson(
  request: Request,
  maxBytes: number,
): Promise<BoundedJsonResult> {
  const contentLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    return { ok: false, status: 413, error: "Payload too large" };
  }

  let rawText = "";
  if (request.body && typeof request.body.getReader === "function") {
    const reader = request.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: false });
    let totalBytes = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          totalBytes += value.byteLength;
          if (totalBytes > maxBytes) {
            await reader.cancel().catch(() => {});
            return { ok: false, status: 413, error: "Payload too large" };
          }
          rawText += decoder.decode(value, { stream: true });
        }
      }
      rawText += decoder.decode();
    } catch {
      return { ok: false, status: 400, error: "Invalid request body" };
    }
  } else {
    rawText = await request.text().catch(() => "");
    if (new TextEncoder().encode(rawText).byteLength > maxBytes) {
      return { ok: false, status: 413, error: "Payload too large" };
    }
  }

  try {
    const parsed: unknown = JSON.parse(rawText);
    if (!parsed || typeof parsed !== "object") {
      return { ok: false, status: 400, error: "Invalid JSON body" };
    }
    return { ok: true, data: parsed };
  } catch {
    return { ok: false, status: 400, error: "Invalid JSON body" };
  }
}
