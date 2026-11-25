/**
 * Barramento leve de eventos para abertura dos modais globais (Conta e Modo Plantão Offline).
 * Evita carregar modais pesados (framer-motion / Dexie UI) na árvore inicial de navegação.
 */

export type GlobalModalKind = "account" | "offline";

export const GLOBAL_MODAL_EVENT = "medquest:open-global-modal";

export function openAccountModal(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<GlobalModalKind>(GLOBAL_MODAL_EVENT, { detail: "account" }));
}

export function openOfflineModal(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<GlobalModalKind>(GLOBAL_MODAL_EVENT, { detail: "offline" }));
}
