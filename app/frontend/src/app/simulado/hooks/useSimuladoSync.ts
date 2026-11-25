"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { AttemptPayload, OfflineQueuedError } from "@/lib/api";
import { removeLearningSession } from "@/lib/sessionState";
import { AttemptResult, BatchAttemptItem, BatchAttemptResultItem } from "@/types/api";

export interface PracticeAttemptEntry {
  status: "inflight" | "queued" | "failed";
  key: string;
  body: AttemptPayload;
  queueItemId?: string;
}

export interface PendingSimuladoBatch {
  key: string;
  attempts: BatchAttemptItem[];
}

export type SyncResolutionState =
  | "idle"
  | "pending"
  | "confirmed_results"
  | "synced_without_results"
  | "terminal_failed";

interface UseSimuladoSyncParams {
  state: string;
  answers: Record<number, string>;
  queueId: string | undefined;
  practiceByQid: Record<number, PracticeAttemptEntry>;
  failedPracticeQueueIds: Record<string, string>;
  practiceByQidRef: React.MutableRefObject<Record<number, PracticeAttemptEntry>>;
  pendingBatchRef: React.MutableRefObject<PendingSimuladoBatch | null>;
  resultsMapRef: React.MutableRefObject<Record<number, BatchAttemptResultItem>>;
  syncResolutionRef: React.MutableRefObject<SyncResolutionState>;
  submitSimuladoRef: React.MutableRefObject<() => Promise<void>>;
  updatePracticeByQid: (
    updater: (prev: Record<number, PracticeAttemptEntry>) => Record<number, PracticeAttemptEntry>
  ) => Record<number, PracticeAttemptEntry>;
  setResultsMap: React.Dispatch<React.SetStateAction<Record<number, BatchAttemptResultItem>>>;
  setFailedPracticeQueueIds: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setHasSavedState: React.Dispatch<React.SetStateAction<boolean>>;
  setState: (next: "START" | "LOADING" | "PLAYING" | "AWAITING_PRACTICE_SYNC" | "SUBMITTING" | "RESULTS" | "OFFLINE_SUBMITTED") => void;
  setShowResultsSummary: React.Dispatch<React.SetStateAction<boolean>>;
  setCurrentIndex: React.Dispatch<React.SetStateAction<number>>;
  setQueueId: React.Dispatch<React.SetStateAction<string | undefined>>;
  sendPracticeAttempt: (qid: number, key: string, body: AttemptPayload) => Promise<void>;
}

/**
 * Gerencia a máquina de sincronização offline e retries do Simulado (modo exame em lote e modo treino).
 */
export function useSimuladoSync({
  state,
  answers,
  queueId,
  practiceByQid,
  failedPracticeQueueIds,
  practiceByQidRef,
  pendingBatchRef,
  resultsMapRef,
  syncResolutionRef,
  submitSimuladoRef,
  updatePracticeByQid,
  setResultsMap,
  setFailedPracticeQueueIds,
  setHasSavedState,
  setState,
  setShowResultsSummary,
  setCurrentIndex,
  setQueueId,
  sendPracticeAttempt,
}: UseSimuladoSyncParams) {
  const [isSyncingOffline, setIsSyncingOffline] = useState(false);

  const handleManualSyncSimulado = useCallback(async () => {
    if (isSyncingOffline) return;
    setIsSyncingOffline(true);
    try {
      const attempts: BatchAttemptItem[] = Object.keys(answers).map((qIdStr) => {
        const qId = parseInt(qIdStr, 10);
        return {
          question_id: qId,
          selected_letter: answers[qId],
          confidence: "duvida",
        };
      });

      if (attempts.length === 0) {
        removeLearningSession("simulado");
        setHasSavedState(false);
        setState("START");
        return;
      }

      const { syncManager } = await import("@/lib/sync");
      await syncManager.sync(true);
      toast.success("Sincronização solicitada.");
    } catch (err) {
      if (err instanceof OfflineQueuedError) {
        toast("Ainda sem conexão com a internet. Suas respostas permanecem salvas com segurança.");
      } else {
        toast.error("Erro ao sincronizar. Verifique sua conexão e tente novamente.");
      }
    } finally {
      setIsSyncingOffline(false);
    }
  }, [answers, isSyncingOffline, setHasSavedState, setState]);

  useEffect(() => {
    if (state !== "PLAYING" && state !== "AWAITING_PRACTICE_SYNC" && state !== "SUBMITTING") return;

    const handlePracticeSyncSuccess = (e: Event) => {
      const customEvent = e as CustomEvent<{
        id: string;
        endpoint: string;
        method: string;
        data: unknown;
        idempotencyKey?: string;
      }>;
      const detail = customEvent.detail;
      if (!detail) return;

      const matchedEntry = Object.entries(practiceByQidRef.current).find(
        ([, entry]) =>
          (entry.queueItemId && entry.queueItemId === detail.id) ||
          (detail.idempotencyKey && entry.key === detail.idempotencyKey)
      );
      if (!matchedEntry) return;

      const [qidStr, entry] = matchedEntry;
      const qid = Number(qidStr);
      const attemptRes = detail.data as AttemptResult | null;
      if (attemptRes && (typeof attemptRes.is_correct === "boolean" || attemptRes.is_correct === null)) {
        const mappedResult: BatchAttemptResultItem = {
          question_id: qid,
          is_correct: Boolean(attemptRes.is_correct),
          correct_letter: attemptRes.correct_letter || "",
          explanation: attemptRes.explanation || null,
          next_review_date: attemptRes.next_review_date || new Date().toISOString(),
          is_discursive: Boolean(attemptRes.is_discursive),
        };
        resultsMapRef.current = { ...resultsMapRef.current, [qid]: mappedResult };
        setResultsMap((prev) => ({ ...prev, [qid]: mappedResult }));
      }
      updatePracticeByQid((prev) => {
        const next = { ...prev };
        delete next[qid];
        return next;
      });
      if (entry.queueItemId) {
        setFailedPracticeQueueIds((prev) => {
          if (!(entry.queueItemId! in prev)) return prev;
          const next = { ...prev };
          delete next[entry.queueItemId!];
          return next;
        });
      }
    };

    window.addEventListener("sync-item-success", handlePracticeSyncSuccess);
    return () => {
      window.removeEventListener("sync-item-success", handlePracticeSyncSuccess);
    };
  }, [state, practiceByQidRef, resultsMapRef, setFailedPracticeQueueIds, setResultsMap, updatePracticeByQid]);

  useEffect(() => {
    if (state !== "AWAITING_PRACTICE_SYNC") return;

    if (Object.keys(practiceByQid).length === 0) {
      const timer = setTimeout(() => {
        void submitSimuladoRef.current();
      }, 0);
      return () => clearTimeout(timer);
    }

    let cancelled = false;
    const checkFailedPracticeItems = async () => {
      try {
        const { syncManager } = await import("@/lib/sync");
        const failedItems = await syncManager.getFailedItems();
        if (cancelled) return;
        const queuedIds = new Set(
          Object.values(practiceByQidRef.current)
            .map((entry) => entry.queueItemId)
            .filter((id): id is string => Boolean(id))
        );
        const nextFailed: Record<string, string> = {};
        for (const item of failedItems) {
          if (queuedIds.has(item.id)) {
            nextFailed[item.id] = item.last_error || "Falha ao sincronizar resposta.";
          }
        }
        setFailedPracticeQueueIds(nextFailed);
      } catch (err) {
        console.error("Erro ao verificar falhas da fila do modo treino:", err);
      }
    };

    void checkFailedPracticeItems();
    const handleQueueUpdate = () => {
      void checkFailedPracticeItems();
    };
    window.addEventListener("sync-queue-updated", handleQueueUpdate);
    const interval = setInterval(() => {
      void checkFailedPracticeItems();
    }, 3000);

    return () => {
      cancelled = true;
      window.removeEventListener("sync-queue-updated", handleQueueUpdate);
      clearInterval(interval);
    };
  }, [state, practiceByQid, practiceByQidRef, setFailedPracticeQueueIds, submitSimuladoRef]);

  const handleSyncPracticeNow = useCallback(async () => {
    if (isSyncingOffline) return;
    setIsSyncingOffline(true);
    try {
      const { syncManager } = await import("@/lib/sync");
      await syncManager.sync(true);
      const failedItems = await syncManager.getFailedItems();
      const queuedIds = new Set(
        Object.values(practiceByQidRef.current)
          .map((entry) => entry.queueItemId)
          .filter((id): id is string => Boolean(id))
      );
      const nextFailed: Record<string, string> = {};
      for (const item of failedItems) {
        if (queuedIds.has(item.id)) {
          nextFailed[item.id] = item.last_error || "Falha ao sincronizar resposta.";
        }
      }
      setFailedPracticeQueueIds(nextFailed);
    } catch {
      toast.error("Não foi possível sincronizar agora. Verifique sua conexão.");
    } finally {
      setIsSyncingOffline(false);
    }
  }, [isSyncingOffline, practiceByQidRef, setFailedPracticeQueueIds]);

  const handleResendFailedPractice = useCallback(async () => {
    if (isSyncingOffline) return;
    setIsSyncingOffline(true);
    try {
      const { syncManager } = await import("@/lib/sync");
      const toResend = Object.entries(practiceByQidRef.current).filter(
        ([, entry]) =>
          entry.status === "failed" ||
          (entry.queueItemId ? entry.queueItemId in failedPracticeQueueIds : false)
      );
      for (const [qidStr, entry] of toResend) {
        if (entry.queueItemId && entry.queueItemId in failedPracticeQueueIds) {
          await syncManager.discardItem(entry.queueItemId);
        }
        await sendPracticeAttempt(Number(qidStr), entry.key, entry.body);
      }
      setFailedPracticeQueueIds({});
    } finally {
      setIsSyncingOffline(false);
    }
  }, [failedPracticeQueueIds, isSyncingOffline, practiceByQidRef, sendPracticeAttempt, setFailedPracticeQueueIds]);

  useEffect(() => {
    if (state !== "OFFLINE_SUBMITTED") return;

    const handleSyncSuccess = (e: Event) => {
      const customEvent = e as CustomEvent<{
        id: string;
        endpoint: string;
        method: string;
        data: unknown;
        idempotencyKey?: string;
      }>;
      const detail = customEvent.detail;
      if (!detail) return;

      const isOwnBatch = Boolean(
        (queueId && detail.id === queueId) ||
          (pendingBatchRef.current?.key && detail.idempotencyKey === pendingBatchRef.current.key)
      );
      if (!isOwnBatch) return;

      const res = detail.data as { results?: BatchAttemptResultItem[] } | null;

      if (res && Array.isArray(res.results) && res.results.length > 0) {
        syncResolutionRef.current = "confirmed_results";
        setResultsMap((prev) => {
          const next = { ...prev };
          res.results!.forEach((r) => {
            next[r.question_id] = r;
          });
          resultsMapRef.current = next;
          return next;
        });
        removeLearningSession("simulado");
        setHasSavedState(false);
        setState("RESULTS");
        setShowResultsSummary(true);
        setCurrentIndex(0);
        toast.success("Simulado sincronizado e corrigido com sucesso!");
      } else {
        syncResolutionRef.current = "synced_without_results";
        removeLearningSession("simulado");
        setHasSavedState(false);
        setQueueId(undefined);
        toast("Simulado sincronizado — confira no histórico");
        setState("START");
      }
    };

    window.addEventListener("sync-item-success", handleSyncSuccess);

    const checkAndSync = async () => {
      if (
        syncResolutionRef.current === "confirmed_results" ||
        syncResolutionRef.current === "synced_without_results"
      ) {
        return;
      }

      try {
        const { syncManager } = await import("@/lib/sync");
        if (navigator.onLine) {
          await syncManager.sync();
        }
        if (queueId) {
          const failed = await syncManager.getFailedItems();
          if (failed.find((i) => i.id === queueId)) {
            syncResolutionRef.current = "terminal_failed";
            toast.error(
              "A sincronização encontrou uma falha terminal. Você pode tentar reenviar as respostas salvas."
            );
            setState("PLAYING");
            setQueueId(undefined);
            return;
          }
        }
      } catch (e) {
        console.error(e);
      }
    };

    const handleOnline = () => {
      void checkAndSync();
    };
    window.addEventListener("online", handleOnline);
    const interval = setInterval(checkAndSync, 5000);

    return () => {
      window.removeEventListener("sync-item-success", handleSyncSuccess);
      window.removeEventListener("online", handleOnline);
      clearInterval(interval);
    };
  }, [
    pendingBatchRef,
    queueId,
    resultsMapRef,
    setCurrentIndex,
    setHasSavedState,
    setQueueId,
    setResultsMap,
    setShowResultsSummary,
    setState,
    state,
    syncResolutionRef,
  ]);

  return {
    isSyncingOffline,
    handleManualSyncSimulado,
    handleSyncPracticeNow,
    handleResendFailedPractice,
  };
}
