"use client";

import { useEffect, useState } from "react";
import { QueryClient, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DashboardSummaryResponse, QuestionMeta } from "@/types/api";

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function useQuestionMetaQuery(
  filters: Record<string, string | string[]>,
  enabled: boolean,
  initialData: QuestionMeta
) {
  const metaFilters: Record<string, string | string[]> = { ...filters };
  delete metaFilters.subtema;
  delete metaFilters.topic;
  const filterKey = JSON.stringify(metaFilters);
  const debouncedKey = useDebouncedValue(filterKey, 250);

  return useQuery<QuestionMeta>({
    queryKey: ["question-meta", debouncedKey],
    queryFn: () => api.questions.getMeta(JSON.parse(debouncedKey) as Record<string, string | string[]>),
    enabled,
    placeholderData: (prev) => prev ?? initialData,
    staleTime: 60_000,
  });
}

export function useDashboardSummaryQuery(enabled = false) {
  return useQuery<DashboardSummaryResponse>({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.stats.getDashboardSummary(),
    enabled,
    staleTime: 45_000,
    retry: 2,
  });
}

export function invalidateStudyCaches(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
  void queryClient.invalidateQueries({ queryKey: ["question-meta"] });
}
