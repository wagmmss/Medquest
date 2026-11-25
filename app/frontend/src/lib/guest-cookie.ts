const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ZERO_UUID = "00000000-0000-0000-0000-000000000000";

export function isValidUuidV4(value: string | undefined | null): value is string {
  return Boolean(value && UUID_V4_REGEX.test(value) && value.toLowerCase() !== ZERO_UUID);
}

function getGuestSigningSecret(): string {
  return (process.env.GUEST_SESSION_SECRET || process.env.FLASK_API_PROXY_SECRET || "").trim();
}

function bytesToHex(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i++) {
    out += bytes[i].toString(16).padStart(2, "0");
  }
  return out;
}

function constantTimeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length || a.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

async function computeHmacHex(guestId: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await globalThis.crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBuf = await globalThis.crypto.subtle.sign(
    "HMAC",
    key,
    enc.encode(`medquest-guest-v1:${guestId.toLowerCase()}`),
  );
  return bytesToHex(new Uint8Array(sigBuf)).slice(0, 32);
}

export async function signGuestCookieValue(guestId: string): Promise<string> {
  const normalized = guestId.toLowerCase();
  const secret = getGuestSigningSecret();
  if (!secret || typeof globalThis.crypto?.subtle === "undefined") {
    return normalized;
  }
  const sig = await computeHmacHex(normalized, secret);
  return `${normalized}.${sig}`;
}

export async function verifyGuestCookieValue(
  rawCookie: string | undefined | null,
): Promise<{ guestId: string; needsResign: boolean } | null> {
  const trimmed = (rawCookie || "").trim();
  if (!trimmed) return null;

  const secret = getGuestSigningSecret();
  const dotIdx = trimmed.indexOf(".");

  if (dotIdx === -1) {
    if (!isValidUuidV4(trimmed)) return null;
    // Sem segredo configurado (ex.: build local sem .env), aceita UUIDv4 simples
    if (!secret) {
      return { guestId: trimmed.toLowerCase(), needsResign: false };
    }
    // Com segredo configurado, rejeita cookie não assinado para impedir fixação/forjamento
    return null;
  }

  const candidateId = trimmed.slice(0, dotIdx);
  const candidateSig = trimmed.slice(dotIdx + 1).toLowerCase();
  if (!isValidUuidV4(candidateId) || !/^[0-9a-f]{32}$/.test(candidateSig)) {
    return null;
  }

  const normalizedId = candidateId.toLowerCase();
  if (!secret) {
    return { guestId: normalizedId, needsResign: false };
  }

  try {
    const expectedSig = await computeHmacHex(normalizedId, secret);
    if (!constantTimeEqualHex(candidateSig, expectedSig)) {
      return null;
    }
    return { guestId: normalizedId, needsResign: false };
  } catch {
    return null;
  }
}
