"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import clsx from "clsx";
import { BarChart3, Crosshair, Layers, ShieldCheck } from "lucide-react";
import type {
  AnalysisSummaryResponse,
  ExamReadiness,
  TimelineStat,
} from "@/types/api";
import { api } from "@/lib/api";

function AnalysisTabSkeleton() {
  return (
    <div className="flex flex-col gap-6 pb-8 animate-pulse" aria-hidden="true">
      <div className="h-32 w-full rounded-lg bg-surface border border-line-subtle" />
      <div className="h-[380px] w-full rounded-lg bg-surface border border-line-subtle" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="h-64 rounded-lg bg-surface border border-line-subtle" />
        <div className="h-64 rounded-lg bg-surface border border-line-subtle" />
      </div>
    </div>
  );
}

const PerformanceRadarTab = dynamic(
  () => import("./components/PerformanceRadarTab").then((m) => m.PerformanceRadarTab),
  { loading: () => <AnalysisTabSkeleton /> }
);
const CoverageThemesTab = dynamic(
  () => import("./components/CoverageThemesTab").then((m) => m.CoverageThemesTab),
  { loading: () => <AnalysisTabSkeleton /> }
);
const ReadinessEditalTab = dynamic(
  () => import("./components/ReadinessEditalTab").then((m) => m.ReadinessEditalTab),
  { loading: () => <AnalysisTabSkeleton /> }
);
const FocusRadarTab = dynamic(
  () => import("./components/FocusRadarTab").then((m) => m.FocusRadarTab),
  { loading: () => <AnalysisTabSkeleton /> }
);

export type AnalysisTabKey = "desempenho" | "cobertura" | "prontidao" | "sniper";

interface AnalysisClientProps {
  initialSummary: AnalysisSummaryResponse;
  institutionOptions: { key: string; label: string }[];
  initialTab?: AnalysisTabKey;
  initialSubtema?: string | null;
  initialError?: string | null;
}

const DEFAULT_INSTITUTIONS = [
  { key: "USP-SP", label: "USP - São Paulo" },
  { key: "USP-RP", label: "USP - Ribeirão Preto" },
  { key: "UNICAMP", label: "Unicamp" },
  { key: "UNIFESP", label: "Unifesp / EPM" },
  { key: "SUS-SP", label: "SUS-SP" },
];

function mergeSummary(
  prev: AnalysisSummaryResponse,
  fresh: Partial<AnalysisSummaryResponse> | null | undefined
): AnalysisSummaryResponse {
  return {
    overview: fresh?.overview ?? prev.overview,
    learning_profile: fresh?.learning_profile ?? prev.learning_profile,
    exam_readiness: fresh?.exam_readiness ?? prev.exam_readiness,
    institution_radar: fresh?.institution_radar ?? prev.institution_radar,
    blindspots: fresh?.blindspots ?? prev.blindspots,
    weak_topics: Array.isArray(fresh?.weak_topics) ? fresh.weak_topics : prev.weak_topics,
    distractors: Array.isArray(fresh?.distractors) ? fresh.distractors : prev.distractors,
    at_risk: Array.isArray(fresh?.at_risk) ? fresh.at_risk : prev.at_risk,
    timeline_180: Array.isArray(fresh?.timeline_180) ? fresh.timeline_180 : prev.timeline_180,
    coverage: fresh?.coverage ?? prev.coverage,
  };
}

export function AnalysisClient({
  initialSummary,
  institutionOptions,
  initialTab = "desempenho",
  initialSubtema = null,
  initialError = null,
}: AnalysisClientProps) {
  const availableInstitutions = useMemo(
    () => (institutionOptions.length > 0 ? institutionOptions : DEFAULT_INSTITUTIONS),
    [institutionOptions]
  );

  const [activeTab, setActiveTab] = useState<AnalysisTabKey>(initialTab);
  const [selectedSubtema, setSelectedSubtema] = useState<string | null>(initialSubtema);
  const [summary, setSummary] = useState<AnalysisSummaryResponse>(initialSummary);
  const [summaryError, setSummaryError] = useState<string | null>(initialError);

  const [selectedInstitution, setSelectedInstitution] = useState<string>(
    initialSummary.exam_readiness?.institution || "USP-SP"
  );
  const [localReadiness, setLocalReadiness] = useState<ExamReadiness>(
    initialSummary.exam_readiness
  );
  const [loadingReadiness, setLoadingReadiness] = useState(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [readinessRetry, setReadinessRetry] = useState(0);

  const [timeline180, setTimeline180] = useState<TimelineStat[]>(
    initialSummary.timeline_180 || []
  );
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [timelineRetry, setTimelineRetry] = useState(0);

  const isFirstReadinessMount = useRef(true);
  const isFirstTimelineMount = useRef(true);

  const syncUrlParams = useCallback(
    (tab: AnalysisTabKey, subtema: string | null) => {
      if (typeof window === "undefined") return;
      const url = new URL(window.location.href);
      if (tab === "desempenho" && !subtema) {
        url.searchParams.delete("tab");
      } else {
        url.searchParams.set("tab", tab);
      }
      if (subtema) {
        url.searchParams.set("subtema", subtema);
      } else {
        url.searchParams.delete("subtema");
      }
      window.history.replaceState(null, "", url.toString());
    },
    []
  );

  const handleTabChange = (tab: AnalysisTabKey) => {
    setActiveTab(tab);
    const nextSubtema = tab === "cobertura" ? selectedSubtema : null;
    if (tab !== "cobertura") setSelectedSubtema(null);
    syncUrlParams(tab, nextSubtema);
  };

  const handleSelectSubtema = (subtema: string | null) => {
    setSelectedSubtema(subtema);
    syncUrlParams("cobertura", subtema);
  };

  const handleRefreshAll = useCallback(async () => {
    setSummaryError(null);
    try {
      const fresh = await api.stats.getAnalysisSummary(
        selectedInstitution || undefined
      );
      setSummary((prev) => mergeSummary(prev, fresh));
      if (fresh?.exam_readiness) {
        setLocalReadiness(fresh.exam_readiness);
        setReadinessError(null);
      }
      if (Array.isArray(fresh?.timeline_180)) {
        setTimeline180(fresh.timeline_180);
        setTimelineError(null);
      }
    } catch {
      setSummaryError(
        "Falha ao atualizar o painel analítico. Tente novamente."
      );
    }
  }, [selectedInstitution]);

  useEffect(() => {
    if (!initialError) return;
    let cancelled = false;
    api.stats
      .getAnalysisSummary(selectedInstitution || undefined)
      .then((fresh) => {
        if (cancelled) return;
        setSummaryError(null);
        setSummary((prev) => mergeSummary(prev, fresh));
        if (fresh?.exam_readiness) {
          setLocalReadiness(fresh.exam_readiness);
          setReadinessError(null);
        }
        if (Array.isArray(fresh?.timeline_180)) {
          setTimeline180(fresh.timeline_180);
          setTimelineError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSummaryError(
            "Falha ao atualizar o painel analítico. Tente novamente."
          );
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (isFirstReadinessMount.current) {
      isFirstReadinessMount.current = false;
      return;
    }
    const controller = new AbortController();
    setLoadingReadiness(true);
    setReadinessError(null);
    api.stats
      .getExamReadiness(selectedInstitution || undefined, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setLocalReadiness(data);
          setReadinessError(null);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setReadinessError("Falha ao atualizar dados de prontidão deste edital.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingReadiness(false);
      });
    return () => controller.abort();
  }, [selectedInstitution, readinessRetry]);

  useEffect(() => {
    if (isFirstTimelineMount.current) {
      isFirstTimelineMount.current = false;
      return;
    }
    const controller = new AbortController();
    setLoadingTimeline(true);
    setTimelineError(null);
    api.stats
      .getTimeline(180, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setTimeline180(data);
          setTimelineError(null);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setTimelineError("Não foi possível carregar a evolução de desempenho.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingTimeline(false);
      });
    return () => controller.abort();
  }, [timelineRetry]);

  useEffect(() => {
    let lastFocus = Date.now();
    const handleFocus = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        if (Date.now() - lastFocus > 30000) {
          setTimelineRetry((r) => r + 1);
          setReadinessRetry((r) => r + 1);
        }
        lastFocus = Date.now();
      }
    };
    const handleSync = (e: Event) => {
      const endpoint = (e as CustomEvent<{ endpoint?: string }>).detail?.endpoint;
      if (
        endpoint?.includes("/api/questions/") ||
        endpoint?.includes("/attempt") ||
        endpoint?.includes("/simulado")
      ) {
        void handleRefreshAll();
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleFocus);
    window.addEventListener("sync-item-success", handleSync);

    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleFocus);
      window.removeEventListener("sync-item-success", handleSync);
    };
  }, [handleRefreshAll]);

  const tabs: Array<{
    key: AnalysisTabKey;
    label: string;
    icon: typeof BarChart3;
  }> = [
    { key: "desempenho", label: "Desempenho & Radar", icon: BarChart3 },
    { key: "cobertura", label: "Cobertura & Temas", icon: Layers },
    { key: "prontidao", label: "Prontidão por Edital", icon: ShieldCheck },
    { key: "sniper", label: "Focos & Sniper", icon: Crosshair },
  ];

  return (
    <div className="flex flex-col gap-6">
      {summaryError && (
        <div
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/10 p-3.5 text-xs text-destructive flex items-center justify-between gap-3"
        >
          <span>{summaryError}</span>
          <button
            type="button"
            onClick={handleRefreshAll}
            className="font-semibold underline cursor-pointer shrink-0"
          >
            Tentar novamente
          </button>
        </div>
      )}

      {/* Segmented Clinical Tab Bar */}
      <div
        role="tablist"
        aria-label="Seções de Análise"
        className="flex flex-wrap items-center gap-1.5 bg-surface border border-line-subtle p-1.5 rounded-2xl w-full sm:w-fit shadow-2xs"
      >
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isSelected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => handleTabChange(tab.key)}
              className={clsx(
                "flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-colors cursor-pointer min-h-[38px]",
                isSelected
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "text-ink-secondary hover:text-ink-primary hover:bg-elevated/60"
              )}
            >
              <Icon size={15} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "desempenho" && (
        <PerformanceRadarTab
          overview={summary.overview}
          learningProfile={summary.learning_profile}
          selectedInstitution={selectedInstitution}
          institutionOptions={availableInstitutions}
          institutionRadar={initialError ? undefined : summary.institution_radar}
          blindspots={initialError ? undefined : summary.blindspots}
          timeline180={timeline180}
          atRiskTopics={summary.at_risk || []}
          weakTopics={summary.weak_topics || []}
          distractors={summary.distractors || []}
          timelineError={timelineError}
          loadingTimeline={loadingTimeline}
          onRefreshTimeline={() => setTimelineRetry((r) => r + 1)}
        />
      )}

      {activeTab === "cobertura" && (
        <CoverageThemesTab
          initialAreas={summary.coverage?.areas || []}
          learningTopics={summary.learning_profile?.topics || []}
          initialSubtema={selectedSubtema}
          onSelectSubtema={handleSelectSubtema}
        />
      )}

      {activeTab === "prontidao" && (
        <ReadinessEditalTab
          examReadiness={localReadiness}
          institutionOptions={availableInstitutions}
          selectedInstitution={selectedInstitution}
          onSelectInstitution={setSelectedInstitution}
          loadingReadiness={loadingReadiness}
          readinessError={readinessError}
          onRetryReadiness={() => setReadinessRetry((r) => r + 1)}
        />
      )}

      {activeTab === "sniper" && (
        <FocusRadarTab
          institutionOptions={availableInstitutions}
          selectedInstitution={selectedInstitution}
          onSelectInstitution={setSelectedInstitution}
        />
      )}
    </div>
  );
}
