import { test, expect } from "@playwright/test";
import { readBoundedJson } from "../src/lib/bounded-json";

test.describe("Onda 2 Security Helpers", () => {

  test("readBoundedJson enforces real stream byte limits without trusting Content-Length", async () => {
    const encoder = new TextEncoder();
    const oversizedPayload = JSON.stringify({ error: "x".repeat(9000) });
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        // Split across multiple chunks without setting Content-Length
        const bytes = encoder.encode(oversizedPayload);
        controller.enqueue(bytes.subarray(0, 4096));
        controller.enqueue(bytes.subarray(4096));
        controller.close();
      },
    });
    const req = new Request("http://localhost/api/logs/error", {
      method: "POST",
      body: stream,
      // @ts-expect-error duplex is required by Node fetch Request streams
      duplex: "half",
    });
    const res = await readBoundedJson(req, 8 * 1024);
    expect(res).toEqual({ ok: false, status: 413, error: "Payload too large" });
  });
});
