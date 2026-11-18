"use client";

import type { QueryClient } from "@tanstack/react-query";
import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { api } from "@/lib/api";

const prefetchedQueries = new Map<string, number>();
const PREFETCH_COOLDOWN_MS = 30_000;

/**
 * Pré-carrega o chunk da rota e, quando aplicável, os dados leves em cache
 * do TanStack Query no hover/toque para tornar a troca de aba instantânea.
 */
export function prefetchRouteIntent(
  href: string,
  router: AppRouterInstance,
  queryClient: QueryClient
) {
  router.prefetch(href);

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return;
  }

  const now = Date.now();
  const lastAt = prefetchedQueries.get(href) ?? 0;
  if (now - lastAt < PREFETCH_COOLDOWN_MS) {
    return;
  }

  if (href === "/") {
    prefetchedQueries.set(href, now);
    void queryClient.prefetchQuery({
      queryKey: ["dashboard-summary"],
      queryFn: () => api.stats.getDashboardSummary(),
      staleTime: 45_000,
    });
  } else if (href === "/estudar") {
    prefetchedQueries.set(href, now);
    void queryClient.prefetchQuery({
      queryKey: ["question-meta", "{}"],
      queryFn: () => api.questions.getMeta({}),
      staleTime: 60_000,
    });
  }
}
