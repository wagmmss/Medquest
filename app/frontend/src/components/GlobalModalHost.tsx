"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { GLOBAL_MODAL_EVENT, GlobalModalKind } from "@/lib/globalModals";

const AccountModal = dynamic(
  () => import("@/components/AccountModal").then((m) => m.AccountModal),
  { ssr: false }
);

const OfflineModal = dynamic(
  () => import("@/components/OfflineModal").then((m) => m.OfflineModal),
  { ssr: false }
);

/**
 * Host único e sob demanda para os modais globais de Conta e Modo Plantão.
 * Os chunks só são baixados na primeira abertura, mantendo AnimatePresence ao fechar.
 */
export function GlobalModalHost() {
  const [accountMounted, setAccountMounted] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [offlineMounted, setOfflineMounted] = useState(false);
  const [offlineOpen, setOfflineOpen] = useState(false);

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const kind = (event as CustomEvent<GlobalModalKind>).detail;
      if (kind === "account") {
        setAccountMounted(true);
        setAccountOpen(true);
      } else if (kind === "offline") {
        setOfflineMounted(true);
        setOfflineOpen(true);
      }
    };
    const handleLegacyOffline = () => {
      setOfflineMounted(true);
      setOfflineOpen(true);
    };

    window.addEventListener(GLOBAL_MODAL_EVENT, handleOpen);
    window.addEventListener("open-offline-modal", handleLegacyOffline);
    return () => {
      window.removeEventListener(GLOBAL_MODAL_EVENT, handleOpen);
      window.removeEventListener("open-offline-modal", handleLegacyOffline);
    };
  }, []);

  return (
    <>
      {accountMounted && (
        <AccountModal isOpen={accountOpen} onClose={() => setAccountOpen(false)} />
      )}
      {offlineMounted && (
        <OfflineModal isOpen={offlineOpen} onClose={() => setOfflineOpen(false)} />
      )}
    </>
  );
}
