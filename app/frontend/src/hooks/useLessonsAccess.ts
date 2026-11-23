"use client";

import { useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAppAuth } from "@/lib/auth-client";

const LESSONS_ACCESS_HINT_KEY = "medquest_lessons_access_hint";
const LESSONS_ACCESS_HINT_EVENT = "medquest-lessons-access-hint-change";

interface LessonsAccessHint {
  userId: string;
  allowed: boolean;
}

function subscribeHint(callback: () => void) {
  window.addEventListener(LESSONS_ACCESS_HINT_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(LESSONS_ACCESS_HINT_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getHintSnapshot(): string {
  try {
    return localStorage.getItem(LESSONS_ACCESS_HINT_KEY) || "";
  } catch {
    return "";
  }
}

function getServerHintSnapshot(): string {
  return "";
}

function parseHint(raw: string): LessonsAccessHint | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<LessonsAccessHint>;
    if (typeof parsed.userId === "string" && typeof parsed.allowed === "boolean") {
      return { userId: parsed.userId, allowed: parsed.allowed };
    }
  } catch {
    // Ignora valor legado ou corrompido no armazenamento local
  }
  return null;
}

function writeHint(userId: string, allowed: boolean): void {
  try {
    const nextRaw = allowed ? JSON.stringify({ userId, allowed: true }) : "";
    const prevRaw = localStorage.getItem(LESSONS_ACCESS_HINT_KEY) || "";
    if (prevRaw === nextRaw) return;
    if (nextRaw) {
      localStorage.setItem(LESSONS_ACCESS_HINT_KEY, nextRaw);
    } else {
      localStorage.removeItem(LESSONS_ACCESS_HINT_KEY);
    }
    window.dispatchEvent(new Event(LESSONS_ACCESS_HINT_EVENT));
  } catch {
    // Storage indisponível (ex: modo privado restrito)
  }
}

export function useLessonsAccess() {
  const { userId, isLoaded } = useAppAuth();
  const sessionKey = isLoaded ? (userId ?? "anon") : "loading";
  const rawHint = useSyncExternalStore(
    subscribeHint,
    getHintSnapshot,
    getServerHintSnapshot
  );

  const parsedHint = useMemo(() => parseHint(rawHint), [rawHint]);

  const { data, isLoading } = useQuery({
    queryKey: ["auth-me", sessionKey],
    queryFn: async ({ signal }) => {
      const res = await api.auth.getMe(signal);
      writeHint(userId ?? "anon", Boolean(res?.can_access_lessons));
      return res;
    },
    enabled: isLoaded,
    staleTime: 60_000,
    retry: false,
  });

  const optimisticAccess = useMemo(() => {
    if (!parsedHint?.allowed) return false;
    // Enquanto o Clerk ainda carrega no reload, assume o hint local do mesmo navegador;
    // após carregar, exige que a identidade atual corresponda ao hint salvo.
    if (!isLoaded) return true;
    return parsedHint.userId === (userId ?? "anon");
  }, [parsedHint, isLoaded, userId]);

  const canAccessLessons =
    data !== undefined ? Boolean(data.can_access_lessons) : optimisticAccess;

  return {
    canAccessLessons,
    isLoading: canAccessLessons ? false : !isLoaded || isLoading,
  };
}
