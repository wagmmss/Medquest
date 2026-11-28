"use client";

import { useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchPlannerBundle } from "@/lib/queries/plannerBundle";
import type { PlannerOrganizationMode } from "@/types/api";
import { PlannerWizard } from "./PlannerWizard";
import { PlannerClient } from "./PlannerClient";
import { SixYearPlanTab } from "./sixYear/SixYearPlanTab";
import { R1CurriculumTab } from "./sixYear/R1CurriculumTab";
import clsx from "clsx";

export type PlannerTabId = "cronograma" | "plano-6ano" | "r1";

const PLANNER_TABS: Array<{ id: PlannerTabId; label: string }> = [
  { id: "cronograma", label: "Cronograma" },
  { id: "plano-6ano", label: "Plano 6º Ano" },
  { id: "r1", label: "R1 & Currículo" },
];

function parseTabParam(raw: string | null, fallback: PlannerTabId): PlannerTabId {
  if (raw === "cronograma" || raw === "plano-6ano" || raw === "r1") {
    return raw;
  }
  return fallback;
}

export function PlannerShell({
  isIntensive,
  initialOrganization,
  initialTab = "cronograma",
}: {
  isIntensive: boolean;
  initialOrganization?: PlannerOrganizationMode;
  initialTab?: PlannerTabId;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const activeTab = parseTabParam(searchParams.get("tab"), initialTab);

  const selectTab = useCallback(
    (tabId: PlannerTabId) => {
      const next = new URLSearchParams(searchParams.toString());
      if (tabId === "cronograma") {
        next.delete("tab");
      } else {
        next.set("tab", tabId);
      }
      const qs = next.toString();
      router.replace(qs ? `/planner?${qs}` : "/planner", { scroll: false });
    },
    [router, searchParams]
  );

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const delta = e.key === "ArrowRight" ? 1 : -1;
    const nextIdx = (idx + delta + PLANNER_TABS.length) % PLANNER_TABS.length;
    const nextTab = PLANNER_TABS[nextIdx];
    selectTab(nextTab.id);
    tabRefs.current[nextIdx]?.focus();
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["planner-bundle", isIntensive, initialOrganization ?? "default"],
    queryFn: () => fetchPlannerBundle(isIntensive, initialOrganization),
    enabled: activeTab === "cronograma",
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });

  const renderCronogramaContent = () => {
    if (isLoading && !data) {
      return (
        <div className="space-y-6 animate-pulse" aria-busy="true" aria-label="Carregando cronograma">
          <div className="h-36 w-full rounded-2xl bg-surface border border-line-subtle" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-28 rounded-xl bg-surface border border-line-subtle" />
            <div className="h-28 rounded-xl bg-surface border border-line-subtle" />
            <div className="h-28 rounded-xl bg-surface border border-line-subtle" />
          </div>
          <div className="h-64 w-full rounded-2xl bg-surface border border-line-subtle" />
        </div>
      );
    }

    if (isError && !data) {
      return (
        <div className="animate-in fade-in duration-500 flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
          <div className="w-12 h-12 bg-destructive/15 text-destructive rounded-2xl flex items-center justify-center mb-4 border border-destructive/20">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-foreground mb-2">Erro ao carregar cronograma</h2>
          <p className="text-sm text-muted-foreground max-w-md mb-6">
            Não foi possível conectar ao servidor para obter seu plano de estudos.
          </p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="px-4 py-2 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:bg-primary/90 transition-colors shadow-sm cursor-pointer"
          >
            Tentar novamente
          </button>
        </div>
      );
    }

    const config = data?.config ?? null;
    const planResponse = data?.planResponse ?? null;

    if (!config || !config.exam_date || !config.start_date) {
      return (
        <div className="animate-in fade-in duration-500 flex flex-col items-center justify-center min-h-[70vh]">
          <PlannerWizard />
        </div>
      );
    }

    if (!planResponse?.plan || planResponse.plan.length === 0) {
      return (
        <div className="animate-in fade-in duration-500 flex flex-col items-center justify-center min-h-[70vh]">
          <div className="bg-destructive/10 text-destructive text-center p-6 rounded-xl border border-destructive/20 max-w-md">
            A data da prova precisa ser no futuro (ou não há temas no modo intensivo).
          </div>
          <div className="mt-8">
            <PlannerWizard initialConfig={config} />
          </div>
        </div>
      );
    }

    return (
      <div className="animate-in fade-in duration-500">
        <PlannerClient
          plan={planResponse.plan}
          completedTopicsOutside={planResponse.completed_topics ?? []}
          initialProgress={data?.progressMap ?? {}}
          initialTopicProgress={data?.topicProgressMap ?? {}}
          warning={planResponse.warning}
          isIntensive={isIntensive}
          organizationMode={data?.organization ?? "geral"}
          config={config}
        />
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label="Seções do Planejador"
        className="flex items-center gap-1.5 p-1 rounded-xl bg-surface border border-line-subtle overflow-x-auto"
      >
        {PLANNER_TABS.map((tab, idx) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[idx] = el;
              }}
              id={`planner-tab-${tab.id}`}
              role="tab"
              type="button"
              aria-selected={isSelected}
              aria-controls={`planner-panel-${tab.id}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, idx)}
              className={clsx(
                "px-3.5 py-2 rounded-lg text-xs sm:text-sm font-bold whitespace-nowrap transition-colors cursor-pointer",
                isSelected
                  ? "bg-primary text-primary-foreground shadow-2xs"
                  : "text-ink-secondary hover:text-ink-primary hover:bg-elevated/70"
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        id={`planner-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`planner-tab-${activeTab}`}
      >
        {activeTab === "cronograma" && renderCronogramaContent()}
        {activeTab === "plano-6ano" && <SixYearPlanTab />}
        {activeTab === "r1" && <R1CurriculumTab />}
      </div>
    </div>
  );
}
