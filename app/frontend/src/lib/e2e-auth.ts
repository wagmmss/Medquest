/**
 * Porta de autenticação exclusiva para suíte E2E (Playwright).
 *
 * Exige travamento triplo:
 * 1. Flag de compile-time `MEDQUEST_E2E_BUILD=1` inlinada via `next.config.ts`
 *    (ausente no Dockerfile de produção, eliminando o branch em tempo de compilação).
 * 2. Variável de runtime `PLAYWRIGHT_TEST=true`.
 * 3. Recusa explícita caso `CLERK_SECRET_KEY` seja uma chave live (`sk_live_`).
 */
export function isE2EAuthBypassEnabled(
  env: Record<string, string | undefined> = process.env,
  buildFlag: string | undefined = process.env.MEDQUEST_E2E_BUILD
): boolean {
  if (buildFlag !== "1") return false;
  if (env.PLAYWRIGHT_TEST !== "true") return false;
  if (String(env.CLERK_SECRET_KEY || "").trim().startsWith("sk_live_")) return false;
  return true;
}

export const E2E_USER_ID = "user_e2e_test";
