import { test, expect } from "@playwright/test";
import { signGuestCookieValue, verifyGuestCookieValue } from "../src/lib/guest-cookie";
import { readBoundedJson } from "../src/lib/bounded-json";

test.describe("Onda 2 Security Helpers", () => {
  test("guest-cookie signs, verifies, and rejects tampered or unsigned cookies when secret is set", async () => {
    const prevSecret = process.env.FLASK_API_PROXY_SECRET;
    process.env.FLASK_API_PROXY_SECRET = "unit-test-guest-secret-key";
    try {
      const validUuid = "11111111-2222-4333-8444-555555555555";
      const signed = await signGuestCookieValue(validUuid);
      expect(signed.startsWith(`${validUuid}.`)).toBe(true);

      const verified = await verifyGuestCookieValue(signed);
      expect(verified).toEqual({ guestId: validUuid, needsResign: false });

      // Signature tampering must be rejected
      const tampered = `${signed.slice(0, -1)}${signed.endsWith("a") ? "b" : "a"}`;
      expect(await verifyGuestCookieValue(tampered)).toBeNull();

      // Raw unsigned UUIDv4 must be rejected when signing secret is active
      expect(await verifyGuestCookieValue(validUuid)).toBeNull();
    } finally {
      if (prevSecret === undefined) delete process.env.FLASK_API_PROXY_SECRET;
      else process.env.FLASK_API_PROXY_SECRET = prevSecret;
    }
  });

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
