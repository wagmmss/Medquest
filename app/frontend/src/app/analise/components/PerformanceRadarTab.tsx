"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import clsx from "clsx";
import { Calendar, Clock, RefreshCcw } from "lucide-react";
import type {
  AtRiskTopic,
  BlindspotsResponse,
  DistractorStat,
  InstitutionRadarResponse,
  LearningProfile,
  OverviewStats,
  TimelineStat,
  WeakTopic,
} from "@/types/api";
import { sliceTimelineByDays } from "@/lib/analysisTimeline";
import { InstitutionRadarSection } from "@/components/analytics/InstitutionRadarSection";
import { BlindspotsRadarSection } from "@/components/analytics/BlindspotsRadarSection";
import { TimelineEvolutionChart } from "./TimelineEvolutionChart";
import { FsrsAndWeakTopicsGrid } from "./FsrsAndWeakTopicsGrid";

interface PerformanceRadarTabProps {
  overview?: OverviewStats;
  learningProfile: LearningProfile;
  selectedInstitution: string;
  institutionOptions: { key: string; label: string }[];
  institutionRadar?: InstitutionRadarResponse | null;
  blindspots?: BlindspotsResponse | null;
  timeline180: TimelineStat[];
  atRiskTopics: AtRiskTopic[];
  weakTopics: WeakTopic[];
  distractors: DistractorStat[];
  timelineError?: string | null;
  loadingTimeline?: boolean;
  onRefreshTimeline?: () => void;
}

const REASON_LABELS: Record<string, string> = {
  low_accuracy: "baixa acurácia",
  reviews_due: "revisões vencidas",
  memory_at_risk: "risco de esquecimento",
  low_coverage: "baixa cobertura",
  balanced_practice: "prática equilibrada",
};

export function PerformanceRadarTab({
  overview,
  learningProfile,
  selectedInstitution,
  institutionOptions,
  institutionRadar,
  blindspots,
  timeline180,
  atRiskTopics,
  weakTopics,
  distractors,
  timelineError = null,
  loadingTimeline = false,
  onRefreshTimeline,
}: PerformanceRadarTabProps) {
  const [days, setDays] = useState<number>(14);
  const [timelineMode, setTimelineMode] = useState<"all" | "latest">("all");
  const isMounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  const visibleTimeline = useMemo(
    () => sliceTimelineByDays(timeline180, days),
    [timeline180, days]
  );

  const chartTimeline = useMemo(
    () =>
      visibleTimeline.map((t) => {
        const useLatest = timelineMode === "latest";
        const rawAcc = useLatest ? (t.latest_accuracy ?? t.accuracy) : t.accuracy;
        const count = useLatest ? (t.latest_attempts ?? t.attempts) : t.attempts;
        return {
          ...t,
          attempts: count,
          dateShort: t.day.split("-").slice(1).reverse().join("/"),
          accPct: parseFloat(((rawAcc || 0) * 100).toFixed(1)),
        };
      }),
    [visibleTimeline, timelineMode]
  );

  const periodPaceStats = useMemo(() => {
    let totalAttempts = 0;
    let totalCorrect = 0;
    let assistedCorrect = 0;
    let totalTimeMs = 0;
    let timedAttempts = 0;

    for (const t of visibleTimeline) {
      const count = timelineMode === "latest" ? (t.latest_attempts ?? t.attempts) : t.attempts;
      const correct = timelineMode === "latest" ? (t.latest_correct ?? t.correct) : t.correct;
      totalAttempts += count || 0;
      totalCorrect += correct || 0;
      assistedCorrect += t.assisted_correct ?? 0;
      totalTimeMs += t.total_time_ms || 0;
      timedAttempts += t.timed_attempts || 0;
    }

    if (visibleTimeline.length === 0 && overview?.assisted_correct_count) {
      assistedCorrect = overview.assisted_correct_count;
    }
    const unassistedCorrect = Math.max(0, totalCorrect - assistedCorrect);

    const avgSeconds = timedAttempts > 0 ? Math.round(totalTimeMs / timedAttempts / 1000) : null;
    const totalMinutes = totalTimeMs > 0 ? Math.round(totalTimeMs / 60000) : 0;
    const periodAccuracy = totalAttempts > 0 ? Math.round((totalCorrect / totalAttempts) * 100) : null;

    return {
      totalAttempts,
      totalCorrect,
      assistedCorrect,
      unassistedCorrect,
      avgSeconds,
      totalMinutes,
      periodAccuracy,
    };
  }, [visibleTimeline, timelineMode, overview]);

  const distractorsBySubtema = useMemo(() => {
    const map = new Map<string, DistractorStat>();
    if (!Array.isArray(distractors)) return map;
    for (const d of distractors) {
      if (d?.subtema) map.set(d.subtema, d);
    }
    return map;
  }, [distractors]);

  const priorityTopic = learningProfile.topics[0];
  const adaptiveRemainder = Math.max(
    0,
    learningProfile.goal.questions_today - learningProfile.goal.reviews_to_do_today
  );

  return (
    <div className="flex flex-col gap-6 pb-8">
      {/* Adaptive Goal Banner */}
      <section className="bg-surface border border-line-subtle rounded-lg p-5 md:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-5">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
              </span>
              <h2 className="text-lg font-bold text-ink-primary">Meta adaptativa de hoje</h2>
            </div>

            <p className="text-sm text-ink-secondary">
              <span className="font-mono-lab tabular-nums font-semibold text-ink-primary">
                {learningProfile.goal.questions_today}
              </span>{" "}
              questões:{" "}
              <span className="font-mono-lab tabular-nums font-semibold text-ink-primary">
                {learningProfile.goal.reviews_to_do_today}
              </span>{" "}
              revisões FSRS e até{" "}
              <span className="font-mono-lab tabular-nums font-semibold text-ink-primary">
                {adaptiveRemainder}
              </span>{" "}
              questões adaptativas.
            </p>

            {learningProfile.goal.backlog_pending > 0 && (
              <div className="mt-3 p-3 bg-warning/10 border border-warning/25 text-ink-primary rounded-md text-xs flex items-start gap-2 max-w-xl">
                <Clock size={15} className="mt-0.5 shrink-0 text-warning" />
                <p>
                  Orçamento de tempo ({learningProfile.goal.hours_budget}h/dia) ativado: limitamos
                  suas revisões a {learningProfile.goal.max_capacity} questões hoje. As{" "}
                  {learningProfile.goal.backlog_pending} pendências foram redistribuídas.
                </p>
              </div>
            )}

            {priorityTopic && (
              <p className="text-xs text-ink-secondary mt-2.5">
                Prioridade atual:{" "}
                <span className="font-semibold text-ink-primary">{priorityTopic.topic}</span>
                {priorityTopic.reasons.length > 0 && (
                  <span>
                    {" "}
                    ·{" "}
                    {priorityTopic.reasons
                      .map((r) => REASON_LABELS[r] || r)
                      .join(", ")}
                  </span>
                )}
              </p>
            )}
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
            {priorityTopic && (
              <Link
                href={`/estudar?subtema=${encodeURIComponent(priorityTopic.topic)}&limit=10${
                  selectedInstitution
                    ? `&institution=${encodeURIComponent(selectedInstitution)}`
                    : ""
                }`}
                className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-surface border border-line-subtle px-4 py-2.5 text-sm font-semibold text-ink-primary hover:border-accent/50 hover:text-accent transition-colors shadow-2xs"
              >
                Treinar prioridade (10q)
              </Link>
            )}
            <Link
              href={`/estudar?mode=adaptive&limit=${learningProfile.goal.questions_today}${
                selectedInstitution
                  ? `&institution=${encodeURIComponent(selectedInstitution)}`
                  : ""
              }`}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-2xs"
            >
              Iniciar sessão personalizada
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      {/* Radar Comparativo de Bancas */}
      <InstitutionRadarSection
        initialData={institutionRadar}
        institutionOptions={institutionOptions}
        defaultInstitution={selectedInstitution || "USP-SP"}
      />

      {/* Radar de Pontos Cegos & Caderno de Erros */}
      <BlindspotsRadarSection initialData={blindspots} />

      {/* Timeline (in-memory slice from timeline_180) */}
      <section className="bg-surface border border-line-subtle rounded-lg p-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-ink-primary">
              Evolução: volume e acurácia diária
            </h2>
            <p className="text-xs text-ink-muted">
              Acurácia diária oscila com amostras pequenas; avalie a tendência junto com o volume.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div
              role="group"
              aria-label="Modo de cálculo da acurácia"
              className="flex items-center gap-1 bg-elevated/60 p-1 rounded-xl border border-line-subtle"
            >
              <button
                type="button"
                onClick={() => setTimelineMode("all")}
                aria-pressed={timelineMode === "all"}
                className={clsx(
                  "px-2.5 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer min-h-[38px]",
                  timelineMode === "all"
                    ? "bg-surface text-ink-primary shadow-xs border border-line-subtle"
                    : "text-ink-muted hover:text-ink-primary"
                )}
              >
                Todas
              </button>
              <button
                type="button"
                onClick={() => setTimelineMode("latest")}
                aria-pressed={timelineMode === "latest"}
                className={clsx(
                  "px-2.5 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer min-h-[38px]",
                  timelineMode === "latest"
                    ? "bg-surface text-ink-primary shadow-xs border border-line-subtle"
                    : "text-ink-muted hover:text-ink-primary"
                )}
              >
                Última tentativa
              </button>
            </div>

            <div className="flex items-center gap-1.5 bg-elevated/60 p-1 rounded-xl border border-line-subtle">
              {[14, 30, 90, 180].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(d)}
                  disabled={loadingTimeline}
                  aria-pressed={days === d}
                  aria-label={`Ver evolução de ${d} dias`}
                  className={clsx(
                    "px-2.5 py-1.5 text-xs font-mono-lab font-semibold rounded-lg transition-colors cursor-pointer min-h-[38px] min-w-[44px] inline-flex items-center justify-center",
                    days === d
                      ? "bg-surface text-ink-primary shadow-xs border border-line-subtle"
                      : "text-ink-muted hover:text-ink-primary",
                    loadingTimeline && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {d}D
                </button>
              ))}
              {onRefreshTimeline && (
                <button
                  type="button"
                  onClick={onRefreshTimeline}
                  disabled={loadingTimeline}
                  aria-label="Atualizar histórico de evolução"
                  title="Atualizar histórico"
                  className="p-1.5 min-h-[38px] min-w-[38px] rounded-lg text-ink-muted hover:text-ink-primary transition-colors inline-flex items-center justify-center cursor-pointer disabled:opacity-50"
                >
                  <RefreshCcw
                    size={14}
                    className={loadingTimeline ? "animate-spin text-primary" : undefined}
                  />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Faixa de KPIs do Período (Ritmo & Acurácia) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div className="bg-canvas border border-line-subtle rounded-xl px-3.5 py-2.5">
            <p className="text-[11px] text-ink-secondary font-medium">Questões no período</p>
            <p className="text-base font-bold text-ink-primary font-mono-lab tabular-nums">
              {periodPaceStats.totalAttempts}
            </p>
          </div>
          <div className="bg-canvas border border-line-subtle rounded-xl px-3.5 py-2.5">
            <p className="text-[11px] text-ink-secondary font-medium">
              {timelineMode === "latest" ? "Acurácia (última)" : "Acurácia (geral)"}
            </p>
            <p className="text-base font-bold text-ink-primary font-mono-lab tabular-nums">
              {periodPaceStats.periodAccuracy !== null ? `${periodPaceStats.periodAccuracy}%` : "—"}
            </p>
            {periodPaceStats.totalCorrect > 0 && (
              <p className="text-[10px] font-mono-lab text-ink-muted mt-0.5 tabular-nums">
                {periodPaceStats.unassistedCorrect} correto · {periodPaceStats.assistedCorrect} c/ ajuda
              </p>
            )}
          </div>
          <div className="bg-canvas border border-line-subtle rounded-xl px-3.5 py-2.5">
            <p className="text-[11px] text-ink-secondary font-medium">Tempo / Questão</p>
            <p className="text-base font-bold text-ink-primary font-mono-lab tabular-nums">
              {periodPaceStats.avgSeconds !== null ? `${periodPaceStats.avgSeconds}s` : "—"}
            </p>
          </div>
          <div className="bg-canvas border border-line-subtle rounded-xl px-3.5 py-2.5">
            <p className="text-[11px] text-ink-secondary font-medium">Tempo Total</p>
            <p className="text-base font-bold text-ink-primary font-mono-lab tabular-nums">
              {periodPaceStats.totalMinutes > 0
                ? periodPaceStats.totalMinutes >= 60
                  ? `${Math.floor(periodPaceStats.totalMinutes / 60)}h ${periodPaceStats.totalMinutes % 60}m`
                  : `${periodPaceStats.totalMinutes}m`
                : "—"}
            </p>
          </div>
        </div>

        {timelineError ? (
          <div
            role="alert"
            className="p-3 rounded-md bg-destructive/10 border border-destructive/25 text-xs text-destructive flex items-center justify-between"
          >
            <span>{timelineError}</span>
            {onRefreshTimeline && (
              <button
                type="button"
                disabled={loadingTimeline}
                onClick={onRefreshTimeline}
                className="font-semibold underline ml-2 cursor-pointer"
              >
                Tentar novamente
              </button>
            )}
          </div>
        ) : (
          <div aria-busy={loadingTimeline}>
            <p className="text-xs text-ink-muted mb-3 font-mono-lab">
              Dados exibidos: últimos {days} dias{loadingTimeline ? " · Atualizando…" : ""}
            </p>
            <div className="h-[340px] w-full min-w-0 border border-line-subtle rounded-md bg-canvas p-4 flex flex-col">
              {chartTimeline.length > 0 ? (
                <div className="flex-1 min-h-0 w-full">
                  <TimelineEvolutionChart data={chartTimeline} />
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-ink-muted gap-2 text-sm">
                  <p>Nenhuma atividade registrada neste recorte de {days} dias.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Heatmap de Consistência (Últimos 6 meses) */}
      <section className="bg-surface border border-line-subtle rounded-lg p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 text-ink-primary">
            <Calendar className="w-4 h-4 text-primary" aria-hidden="true" />
            <h3 className="text-base font-bold text-ink-primary">
              Histórico de Atividade (Últimos 6 meses)
            </h3>
          </div>
          <span className="text-xs text-ink-muted hidden sm:inline-block font-mono-lab">
            Consistência e volume diário
          </span>
        </div>

        {(() => {
          if (!isMounted) {
            return <div className="w-full h-[105px] bg-elevated/60 rounded-md" />;
          }
          if (!timeline180 || timeline180.length === 0) {
            return (
              <p className="text-sm text-ink-muted py-6 text-center">
                Nenhuma atividade registrada nos últimos 6 meses.
              </p>
            );
          }
          const today = new Date();
          const daysCount = 180;
          const startDate = new Date(today.getTime() - (daysCount - 1) * 24 * 60 * 60 * 1000);
          startDate.setDate(startDate.getDate() - startDate.getDay());
          const totalDays =
            Math.floor((today.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000)) + 1;

          const activityMap = new Map<string, number>();
          timeline180.forEach((t) => {
            activityMap.set(t.day, t.attempts);
          });

          const grid = [];
          for (let i = 0; i < totalDays; i++) {
            const d = new Date(startDate.getTime() + i * 24 * 60 * 60 * 1000);
            const dateStr = d.toISOString().split("T")[0];
            const count = activityMap.get(dateStr) || 0;

            let colorClass = "bg-elevated";
            if (count > 0 && count <= 10) colorClass = "bg-primary/30";
            else if (count > 10 && count <= 30) colorClass = "bg-primary/50";
            else if (count > 30 && count <= 60) colorClass = "bg-primary/75";
            else if (count > 60) colorClass = "bg-primary";

            grid.push(
              <div
                key={dateStr}
                title={`${dateStr}: ${count} questões`}
                className={clsx(
                  "w-[13px] h-[13px] rounded-xs transition-colors hover:ring-2 ring-primary/50",
                  colorClass
                )}
              />
            );
          }

          return (
            <div className="w-full overflow-x-auto pb-2 scrollbar-thin">
              <div className="flex flex-col flex-wrap gap-1 h-[105px] min-w-max content-start">
                {grid}
              </div>
              <div className="flex items-center justify-between text-[11px] text-ink-muted mt-3 pt-2 border-t border-line-subtle font-mono-lab">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-xs bg-elevated" /> 0
                  <span className="w-2.5 h-2.5 rounded-xs bg-primary/30 ml-2" /> 1-10
                  <span className="w-2.5 h-2.5 rounded-xs bg-primary/50 ml-1" /> 11-30
                  <span className="w-2.5 h-2.5 rounded-xs bg-primary/75 ml-1" /> 31-60
                  <span className="w-2.5 h-2.5 rounded-xs bg-primary ml-1" /> 60+
                </span>
                <span>180 dias</span>
              </div>
            </div>
          );
        })()}
      </section>

      <FsrsAndWeakTopicsGrid
        atRiskTopics={atRiskTopics}
        weakTopics={weakTopics}
        distractorsBySubtema={distractorsBySubtema}
      />
    </div>
  );
}
