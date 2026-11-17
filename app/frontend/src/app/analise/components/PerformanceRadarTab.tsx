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

interface TimelineChartRow {
  day: string;
  dateShort: string;
  attempts: number;
  accPct: number;
}

function TimelineEvolutionChart({ data }: { data: TimelineChartRow[] }) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const width = 760;
  const height = 280;
  const padTop = 18;
  const padRight = 18;
  const padBottom = 34;
  const padLeft = 36;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const maxAttempts = useMemo(() => {
    let max = 10;
    for (const d of data) {
      if (d.attempts > max) max = d.attempts;
    }
    return Math.ceil(max / 5) * 5;
  }, [data]);

  const points = useMemo(() => {
    const n = data.length;
    return data.map((row, idx) => {
      const slotW = plotW / Math.max(1, n);
      const x = padLeft + slotW * idx + slotW / 2;
      const barW = Math.min(24, Math.max(4, slotW * 0.56));
      const barH = Math.max(0, (row.attempts / maxAttempts) * plotH);
      const barY = padTop + plotH - barH;
      const accClamped = Math.max(0, Math.min(100, row.accPct || 0));
      const lineY = padTop + plotH - (accClamped / 100) * plotH;
      return {
        ...row,
        x,
        slotLeft: padLeft + slotW * idx,
        slotW,
        barW,
        barH,
        barY,
        lineY,
      };
    });
  }, [data, maxAttempts, plotW, plotH]);

  const { linePath, areaPath } = useMemo(() => {
    if (points.length === 0) return { linePath: "", areaPath: "" };
    if (points.length === 1) {
      const p = points[0];
      const base = padTop + plotH;
      return {
        linePath: `M ${p.x} ${p.lineY}`,
        areaPath: `M ${p.x - 10} ${base} L ${p.x} ${p.lineY} L ${p.x + 10} ${base} Z`,
      };
    }
    let d = `M ${points[0].x.toFixed(1)} ${points[0].lineY.toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i];
      const p1 = points[i + 1];
      const midX = ((p0.x + p1.x) / 2).toFixed(1);
      d += ` C ${midX} ${p0.lineY.toFixed(1)}, ${midX} ${p1.lineY.toFixed(1)}, ${p1.x.toFixed(1)} ${p1.lineY.toFixed(1)}`;
    }
    const base = (padTop + plotH).toFixed(1);
    const firstX = points[0].x.toFixed(1);
    const lastX = points[points.length - 1].x.toFixed(1);
    return {
      linePath: d,
      areaPath: `${d} L ${lastX} ${base} L ${firstX} ${base} Z`,
    };
  }, [points, plotH]);

  const yTicks = useMemo(
    () => [0, 0.25, 0.5, 0.75, 1].map((t) => ({
      val: Math.round(maxAttempts * t),
      y: padTop + plotH * (1 - t),
    })),
    [maxAttempts, plotH]
  );

  const labelStep = Math.max(1, Math.ceil(points.length / 8));
  const activePoint = hoveredIdx !== null ? points[hoveredIdx] : null;

  return (
    <div
      className="relative w-full h-full select-none"
      onMouseLeave={() => setHoveredIdx(null)}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full overflow-visible"
        role="img"
        aria-label="Gráfico de evolução de volume e acurácia diária"
      >
        <defs>
          <linearGradient id="colorAcc" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--success)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--success)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="barAttempts" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.45} />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.12} />
          </linearGradient>
        </defs>

        {yTicks.map((tick, idx) => (
          <g key={idx}>
            <line
              x1={padLeft}
              x2={width - padRight}
              y1={tick.y}
              y2={tick.y}
              stroke="var(--border)"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
            <text
              x={padLeft - 8}
              y={tick.y + 4}
              textAnchor="end"
              fill="var(--muted-foreground)"
              fontSize={11}
            >
              {tick.val}
            </text>
          </g>
        ))}

        {points.map((pt, idx) => (
          <g key={pt.day}>
            {hoveredIdx === idx && (
              <rect
                x={pt.slotLeft}
                y={padTop}
                width={pt.slotW}
                height={plotH}
                fill="var(--muted)"
                opacity={0.15}
                rx={4}
              />
            )}
            {pt.barH > 0 && (
              <rect
                x={pt.x - pt.barW / 2}
                y={pt.barY}
                width={pt.barW}
                height={pt.barH}
                fill="url(#barAttempts)"
                rx={3}
              />
            )}
            {(idx % labelStep === 0 || idx === points.length - 1) && (
              <text
                x={pt.x}
                y={height - 10}
                textAnchor="middle"
                fill="var(--muted-foreground)"
                fontSize={11}
                fontWeight={500}
              >
                {pt.dateShort}
              </text>
            )}
          </g>
        ))}

        {areaPath && <path d={areaPath} fill="url(#colorAcc)" stroke="none" />}
        {linePath && (
          <path
            d={linePath}
            fill="none"
            stroke="var(--success)"
            strokeWidth={3}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {points.map((pt, idx) => {
          const isHovered = hoveredIdx === idx;
          return (
            <g key={`dot-${pt.day}`}>
              <circle
                cx={pt.x}
                cy={pt.lineY}
                r={isHovered ? 6 : 4}
                fill={isHovered ? "var(--success)" : "var(--background)"}
                stroke={isHovered ? "var(--background)" : "var(--success)"}
                strokeWidth={2.5}
              />
              <rect
                x={pt.slotLeft}
                y={padTop}
                width={pt.slotW}
                height={plotH}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIdx(idx)}
                onFocus={() => setHoveredIdx(idx)}
              />
            </g>
          );
        })}
      </svg>

      {activePoint && (
        <div
          className="pointer-events-none absolute top-2 bg-popover border border-line-subtle shadow-md rounded-md p-3 text-xs z-50 min-w-[180px]"
          style={{
            left: `${Math.min(72, Math.max(4, (activePoint.x / width) * 100))}%`,
          }}
        >
          <p className="font-mono-lab font-bold text-popover-foreground mb-2 border-b border-line-subtle pb-1.5">
            {activePoint.day}
          </p>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-muted-foreground">Volume</span>
            <span className="font-mono-lab tabular-nums font-semibold text-foreground">
              {activePoint.attempts} q.
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Acurácia</span>
            <span className="font-mono-lab tabular-nums font-bold text-success">
              {activePoint.accPct}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

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
              <h2 className="text-lg font-bold text-foreground">Meta adaptativa de hoje</h2>
            </div>

            <p className="text-sm text-muted-foreground">
              <span className="font-mono-lab tabular-nums font-semibold text-foreground">
                {learningProfile.goal.questions_today}
              </span>{" "}
              questões:{" "}
              <span className="font-mono-lab tabular-nums font-semibold text-foreground">
                {learningProfile.goal.reviews_to_do_today}
              </span>{" "}
              revisões FSRS e até{" "}
              <span className="font-mono-lab tabular-nums font-semibold text-foreground">
                {adaptiveRemainder}
              </span>{" "}
              questões adaptativas.
            </p>

            {learningProfile.goal.backlog_pending > 0 && (
              <div className="mt-3 p-3 bg-warning/10 border border-warning/25 text-foreground rounded-md text-xs flex items-start gap-2 max-w-xl">
                <Clock size={15} className="mt-0.5 shrink-0 text-warning" />
                <p>
                  Orçamento de tempo ({learningProfile.goal.hours_budget}h/dia) ativado: limitamos
                  suas revisões a {learningProfile.goal.max_capacity} questões hoje. As{" "}
                  {learningProfile.goal.backlog_pending} pendências foram redistribuídas.
                </p>
              </div>
            )}

            {priorityTopic && (
              <p className="text-xs text-muted-foreground mt-2.5">
                Prioridade atual:{" "}
                <span className="font-semibold text-foreground">{priorityTopic.topic}</span>
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
            <h2 className="text-xl font-bold text-foreground">
              Evolução: volume e acurácia diária
            </h2>
            <p className="text-xs text-muted-foreground">
              Acurácia diária oscila com amostras pequenas; avalie a tendência junto com o volume.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div
              role="group"
              aria-label="Modo de cálculo da acurácia"
              className="flex items-center gap-1 bg-surface-subtle p-1 rounded-xl border border-line-subtle"
            >
              <button
                type="button"
                onClick={() => setTimelineMode("all")}
                aria-pressed={timelineMode === "all"}
                className={clsx(
                  "px-2.5 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer min-h-[34px]",
                  timelineMode === "all"
                    ? "bg-surface text-foreground shadow-xs border border-line-subtle"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Todas
              </button>
              <button
                type="button"
                onClick={() => setTimelineMode("latest")}
                aria-pressed={timelineMode === "latest"}
                className={clsx(
                  "px-2.5 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer min-h-[34px]",
                  timelineMode === "latest"
                    ? "bg-surface text-foreground shadow-xs border border-line-subtle"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Última tentativa
              </button>
            </div>

            <div className="flex items-center gap-1.5 bg-surface-subtle p-1 rounded-xl border border-line-subtle">
              {[14, 30, 90, 180].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(d)}
                  disabled={loadingTimeline}
                  aria-pressed={days === d}
                  aria-label={`Ver evolução de ${d} dias`}
                  className={clsx(
                    "px-2.5 py-1.5 text-xs font-mono-lab font-semibold rounded-lg transition-colors cursor-pointer min-h-[34px] min-w-[44px] inline-flex items-center justify-center",
                    days === d
                      ? "bg-surface text-foreground shadow-xs border border-line-subtle"
                      : "text-muted-foreground hover:text-foreground",
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
                  className="p-1.5 min-h-[34px] min-w-[34px] rounded-lg text-muted-foreground hover:text-foreground transition-colors inline-flex items-center justify-center cursor-pointer disabled:opacity-50"
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
            <p className="text-xs text-muted-foreground mb-3 font-mono-lab">
              Dados exibidos: últimos {days} dias{loadingTimeline ? " · Atualizando…" : ""}
            </p>
            <div className="h-[340px] w-full min-w-0 border border-line-subtle rounded-md bg-canvas p-4 flex flex-col">
              {chartTimeline.length > 0 ? (
                <div className="flex-1 min-h-0 w-full">
                  <TimelineEvolutionChart data={chartTimeline} />
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2 text-sm">
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
          <div className="flex items-center gap-2 text-foreground">
            <Calendar className="w-4 h-4 text-primary" aria-hidden="true" />
            <h3 className="text-base font-bold text-foreground">
              Histórico de Atividade (Últimos 6 meses)
            </h3>
          </div>
          <span className="text-xs text-muted-foreground hidden sm:inline-block font-mono-lab">
            Consistência e volume diário
          </span>
        </div>

        {(() => {
          if (!isMounted) {
            return <div className="w-full h-[105px] bg-surface-subtle rounded-md" />;
          }
          if (!timeline180 || timeline180.length === 0) {
            return (
              <p className="text-sm text-muted-foreground py-6 text-center">
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

            let colorClass = "bg-surface-subtle";
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
              <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-3 pt-2 border-t border-line-subtle font-mono-lab">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-xs bg-surface-subtle" /> 0
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

      {/* Radar de Esquecimento FSRS + Tópicos Fracos e Distratores */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar de Esquecimento (FSRS) */}
        <section className="bg-surface border border-line-subtle rounded-lg p-6 flex flex-col">
          <div className="mb-4">
            <h3 className="font-bold text-lg text-foreground">Radar de Esquecimento (FSRS)</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Subtemas com questões próximas do limiar de retenção programada.
            </p>
          </div>

          <div className="flex-1 space-y-2.5">
            {atRiskTopics && atRiskTopics.length > 0 ? (
              atRiskTopics.map((topic, idx) => (
                <Link
                  key={`${topic.subtema}-${idx}`}
                  href={`/estudar?subtema=${encodeURIComponent(topic.subtema)}&status=srs_due&limit=20`}
                  className="flex items-center justify-between p-3 bg-canvas rounded-md border border-line-subtle hover:border-warning/50 transition-colors"
                >
                  <div className="flex flex-col min-w-0 pr-3">
                    <span
                      className="font-medium text-sm text-foreground leading-tight truncate"
                      title={topic.subtema}
                    >
                      {topic.subtema}
                    </span>
                    <span className="text-xs text-muted-foreground mt-0.5 font-mono-lab tabular-nums">
                      {topic.items_count} {topic.items_count === 1 ? "questão em risco" : "questões em risco"}
                    </span>
                  </div>
                  <div className="flex flex-col items-end shrink-0 gap-1">
                    <span className="text-xs font-mono-lab tabular-nums font-semibold text-warning">
                      {topic.retrievability !== undefined
                        ? `${Math.round(topic.retrievability * 100)}% retenção`
                        : "Baixa retenção"}
                    </span>
                    <span className="text-[11px] font-semibold text-accent">
                      Treinar →
                    </span>
                  </div>
                </Link>
              ))
            ) : (
              <div className="h-full min-h-[140px] flex items-center justify-center text-xs text-muted-foreground text-center p-4 border border-dashed border-line-subtle rounded-md">
                Nenhuma questão com risco elevado de esquecimento no momento.
              </div>
            )}
          </div>
        </section>

        {/* Tópicos Fracos & Armadilhas */}
        <section className="bg-surface border border-line-subtle rounded-lg overflow-hidden flex flex-col">
          <div className="p-5 border-b border-line-subtle bg-surface-subtle">
            <h3 className="font-bold text-lg text-foreground">Tópicos Fracos & Armadilhas</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Ordenados por acurácia, com amostra visível e padrão de distratores.
            </p>
          </div>
          <div className="divide-y divide-line-subtle">
            {weakTopics && weakTopics.length > 0 ? (
              weakTopics.slice(0, 8).map((wt) => {
                const distractor = distractorsBySubtema.get(wt.topic);
                const worstChoice = distractor?.wrong_choices?.[0];

                return (
                  <Link
                    key={wt.topic}
                    href={`/estudar?subtema=${encodeURIComponent(wt.topic)}&status=all&limit=10`}
                    className="p-4 hover:bg-surface-subtle/60 transition-colors flex items-center justify-between gap-4 group"
                  >
                    <div className="min-w-0 flex-1">
                      <p
                        className="font-medium text-sm text-foreground truncate group-hover:text-primary transition-colors"
                        title={wt.topic}
                      >
                        {wt.topic}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5 font-mono-lab tabular-nums">
                        {wt.correct} acertos em {wt.attempts} tentativas
                        {wt.attempts < 10 ? " · amostra inicial" : ""}
                      </p>

                      {worstChoice && worstChoice.count >= 2 && wt.attempts >= 5 && (
                        <div className="mt-2 flex items-center gap-1.5 flex-wrap bg-destructive/5 w-fit px-2 py-1 rounded-xs border border-destructive/20 text-xs">
                          <span className="text-muted-foreground">Distrator recorrente:</span>
                          <span className="inline-flex items-center justify-center bg-canvas font-mono-lab font-bold text-foreground w-5 h-5 rounded-xs text-[10px] uppercase border border-line-subtle">
                            {worstChoice.letter}
                          </span>
                          <span className="font-mono-lab font-semibold text-destructive">
                            ({worstChoice.count}x)
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span
                        className={clsx(
                          "font-mono-lab tabular-nums font-bold text-base",
                          (wt.accuracy || 0) < 0.5 ? "text-destructive" : "text-warning"
                        )}
                      >
                        {((wt.accuracy || 0) * 100).toFixed(0)}%
                      </span>
                      <span className="text-[11px] font-semibold text-accent">
                        Treinar (10q) →
                      </span>
                    </div>
                  </Link>
                );
              })
            ) : (
              <div className="p-8 text-center text-xs text-muted-foreground">
                Nenhum tópico fraco identificado ainda (mínimo de 5 tentativas por tema).
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
