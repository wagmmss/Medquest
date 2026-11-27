import { existsSync } from "node:fs";
import { join } from "node:path";
import { auth, currentUser } from "@clerk/nextjs/server";
import { E2E_USER_ID, isE2EAuthBypassEnabled } from "./e2e-auth";

/**
 * Indica se o Clerk está ativo no servidor.
 * Em produção, é sempre obrigatório. Em desenvolvimento, exige chaves explícitas
 * ou o arquivo local de modo keyless (.clerk/.tmp/keyless.json).
 */
export function isClerkServerEnabled(): boolean {
  if (process.env.NODE_ENV === "production") {
    return true;
  }

  if (process.env.MEDQUEST_PREVIEW_NO_CLERK === "1") {
    return false;
  }

  const hasExplicitKeys = Boolean(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() &&
      process.env.CLERK_SECRET_KEY?.trim()
  );
  if (hasExplicitKeys) {
    return true;
  }

  const keylessCandidates = [
    join(process.cwd(), ".clerk", ".tmp", "keyless.json"),
    join(process.cwd(), "app", "frontend", ".clerk", ".tmp", "keyless.json"),
  ];

  try {
    return keylessCandidates.some((candidate) => existsSync(candidate));
  } catch {
    return false;
  }
}

/**
 * Retorna o estado de autenticação no servidor.
 * No modo E2E explicitamente compilado e ativado, devolve a identidade sintética de teste.
 */
export async function getServerAuthState(): Promise<{
  userId: string | null;
  sessionClaims: Record<string, unknown> | null;
  getToken: () => Promise<string | null>;
}> {
  if (isE2EAuthBypassEnabled()) {
    return { userId: E2E_USER_ID, sessionClaims: null, getToken: async () => null };
  }

  if (!isClerkServerEnabled()) {
    return { userId: null, sessionClaims: null, getToken: async () => null };
  }

  const session = await auth();
  return {
    userId: session.userId ?? null,
    sessionClaims: (session.sessionClaims as Record<string, unknown> | undefined) ?? null,
    getToken: () => session.getToken(),
  };
}

/**
 * Retorna o usuário atual do Clerk no servidor ou null quando indisponível.
 */
export async function getServerCurrentUser() {
  if (isE2EAuthBypassEnabled() || !isClerkServerEnabled()) {
    return null;
  }
  return currentUser();
}
