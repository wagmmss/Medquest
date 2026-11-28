"use client";

import type { QueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const SIX_YEAR_SUMMARY_KEY = ["six-year-summary"] as const;

export function sixYearPreviewKey(from: string, to: string) {
  return ["six-year-preview", from, to] as const;
}

export function fetchSixYearSummary() {
  return api.sixYear.getSummary();
}

export function fetchSixYearPreview(from: string, to: string) {
  return api.sixYear.getPreview(from, to);
}

/**
 * Invalida todas as queries da Central 6º Ano e as queries derivadas do Dashboard / Análise
 * que refletem `daily_target`, `daily_routine` e `learning_profile`.
 */
export async function invalidateSixYearQueries(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["six-year-summary"] }),
    queryClient.invalidateQueries({ queryKey: ["six-year-preview"] }),
    queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
    queryClient.invalidateQueries({ queryKey: ["analysis-summary"] }),
    queryClient.invalidateQueries({ queryKey: ["planner-bundle"] }),
  ]);
}
