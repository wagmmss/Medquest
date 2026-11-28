"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, ChevronDown, Flag, Gauge } from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";
import {
  SIX_YEAR_SUMMARY_KEY,
  fetchSixYearSummary,
  invalidateSixYearQueries,
} from "@/lib/queries/sixYear";
import {
  DAY_MODE_DISPLAY,
  MARCHAS_6ANO,
  MARCHA_ORDER,
  type DayOverrideMode,
  type MarchaId,
} from "@/lib/sixYear/staticData";
import clsx from "clsx";

interface SixYearStatusCardProps {
  onRoutineUpdated?: () => void;
}

export function SixYearStatusCard({ onRoutineUpdated }: SixYearStatusCardProps) {
  const queryClient = useQueryClient();
  const [marchaMenuOpen, setMarchaMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data: summary, isError } = useQuery({
    queryKey: SIX_YEAR_SUMMARY_KEY,
    queryFn: fetchSixYearSummary,
    staleTime: 30_000,
    retry: false,
    refetchOnWindowFocus: false,
  });

  // Falha silenciosa: nunca quebra o Dashboard
  if (isError || !summary) {
    return null;
  }

  const { today, rodizio, week, next_milestone } = summary;
  const todayDisplay = DAY_MODE_DISPLAY[today.mode] ?? DAY_MODE_DISPLAY.integral;
  const marchaInfo = MARCHAS_6ANO[week.marcha_id] ?? MARCHAS_6ANO["3_normal"];

  const handleQuickOverride = async (mode: DayOverrideMode | null) => {
    setBusy(true);
    try {
      if (mode === null) {
        await api.sixYear.deleteDayOverride(today.date_iso);
        toast.success("Rotina de hoje restaurada para o normal.");
      } else {
        await api.sixYear.putDayOverride(today.date_iso, mode);
        toast.success(
          mode === "pos_plantao" ? "Hoje marcado como pós-plantão." : "Hoje marcado como folga."
        );
      }
      await invalidateSixYearQueries(queryClient);
      onRoutineUpdated?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao atualizar rotina de hoje.");
    } finally {
      setBusy(false);
    }
  };

  const handleSelectMarcha = async (mId: MarchaId) => {
    setBusy(true);
    setMarchaMenuOpen(false);
    try {
      await api.sixYear.putMarcha(week.week_iso, mId);
      await invalidateSixYearQueries(queryClient);
      onRoutineUpdated?.();
      toast.success(`Marcha da semana definida: ${MARCHAS_6ANO[mId].short}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao alterar Marcha.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      data-testid="six-year-status-card"
      aria-label="Resumo do Plano 6º Ano"
      className="bg-surface border border-line-subtle rounded-sm p-3.5 sm:p-4 shadow-2xs space-y-3"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span className="inline-flex items-center gap-1 text-xs font-bold text-ink-primary">
            <CalendarClock size={14} className="text-primary shrink-0" />
            {rodizio ? rodizio.label || rodizio.area : "6º Ano"}
          </span>
          <span className="px-2 py-0.5 rounded-xs text-[11px] font-bold bg-primary/10 text-primary border border-primary/25">
            {todayDisplay.label} · {today.goal_questions}q
          </span>

          {/* Chip de Marcha interativo */}
          <div className="relative">
            <button
              type="button"
              disabled={busy}
              aria-haspopup="menu"
              aria-expanded={marchaMenuOpen}
              onClick={() => setMarchaMenuOpen((v) => !v)}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs text-[11px] font-semibold bg-elevated border border-line-subtle text-ink-primary hover:border-line-strong cursor-pointer"
            >
              <Gauge size={12} className="text-ink-secondary" />
              Marcha: {marchaInfo.short} ({week.marcha_source})
              <ChevronDown size={12} />
            </button>

            {marchaMenuOpen && (
              <div
                role="menu"
                className="absolute left-0 mt-1 z-30 w-52 rounded-xl bg-surface border border-line-strong shadow-lg p-1.5 space-y-1"
              >
                {MARCHA_ORDER.map((mId) => (
                  <button
                    key={mId}
                    type="button"
                    role="menuitem"
                    onClick={() => void handleSelectMarcha(mId)}
                    className={clsx(
                      "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center justify-between cursor-pointer",
                      week.marcha_id === mId
                        ? "bg-primary text-primary-foreground"
                        : "text-ink-primary hover:bg-elevated"
                    )}
                  >
                    <span>{MARCHAS_6ANO[mId].short}</span>
                    <span className="text-[10px] font-mono opacity-80">
                      {MARCHAS_6ANO[mId].badge}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {next_milestone && (
            <span className="inline-flex items-center gap-1 text-[11px] text-ink-secondary">
              <Flag size={11} className="text-warning shrink-0" />
              <span className="truncate max-w-[180px]">{next_milestone.titulo}</span>
              {next_milestone.days_left !== null && (
                <strong className="text-ink-primary">
                  ({next_milestone.days_left >= 0 ? `${next_milestone.days_left}d` : "passou"})
                </strong>
              )}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 text-xs">
          <Link
            href="/planner?tab=plano-6ano"
            className="font-semibold text-primary hover:underline"
          >
            Plano
          </Link>
          <span className="text-ink-muted">·</span>
          <Link href="/planner?tab=r1" className="font-semibold text-primary hover:underline">
            R1
          </Link>
        </div>
      </div>

      {/* Ações 1-clique */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-line-subtle">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleQuickOverride("pos_plantao")}
          className={clsx(
            "px-2.5 py-1 rounded-xs border text-[11px] font-semibold transition-colors cursor-pointer disabled:opacity-50",
            today.source === "override" && today.mode === "pos_plantao"
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-elevated text-ink-primary border-line-subtle hover:border-line-strong"
          )}
        >
          Hoje: Pós-plantão
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleQuickOverride("folga")}
          className={clsx(
            "px-2.5 py-1 rounded-xs border text-[11px] font-semibold transition-colors cursor-pointer disabled:opacity-50",
            today.source === "override" && today.mode === "folga"
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-elevated text-ink-primary border-line-subtle hover:border-line-strong"
          )}
        >
          Folga
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleQuickOverride(null)}
          className="px-2.5 py-1 rounded-xs border border-line-subtle bg-elevated text-ink-secondary hover:text-ink-primary text-[11px] font-semibold cursor-pointer disabled:opacity-50"
        >
          Normal
        </button>
      </div>
    </section>
  );
}
