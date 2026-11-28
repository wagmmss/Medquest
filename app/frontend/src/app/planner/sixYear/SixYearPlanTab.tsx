"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Gauge,
  Link2,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";
import {
  SIX_YEAR_SUMMARY_KEY,
  fetchSixYearSummary,
  invalidateSixYearQueries,
} from "@/lib/queries/sixYear";
import {
  DAY_MODE_DISPLAY,
  DAY_SOURCE_LABELS,
  FERIAS_SEMANAS,
  MARCHAS_6ANO,
  MARCHA_ORDER,
  NOVO_PEP_ESTEIRA_URL,
  NOVO_PEP_LOGBOOK_URL,
  RITUAL_DOMINGO_DATA,
  WEEKDAY_CHIPS,
  type DayOverrideMode,
  type MarchaId,
  type WeekPatternMode,
  type WeekdayKey,
} from "@/lib/sixYear/staticData";
import type { InternatoBlock, SixYearFeedTokenResponse } from "@/types/api";
import { ShiftCalendarSection } from "./ShiftCalendarSection";
import clsx from "clsx";

const PATTERN_CYCLE: WeekPatternMode[] = ["integral", "meio_periodo", "folga"];
const PATTERN_LABELS: Record<WeekPatternMode, string> = {
  integral: "Integral",
  meio_periodo: "Meio per.",
  folga: "Folga",
};

function daysRemainingInclusive(todayIso: string, endIso?: string): number | null {
  if (!endIso) return null;
  const [ty, tm, td] = todayIso.split("-").map(Number);
  const [ey, em, ed] = endIso.split("-").map(Number);
  if (!ty || !ey) return null;
  const diff = Math.round(
    (Date.UTC(ey, em - 1, ed) - Date.UTC(ty, tm - 1, td)) / 86400000
  );
  return diff;
}

export function SixYearPlanTab() {
  const queryClient = useQueryClient();
  const { data: summary, isLoading, isError, refetch } = useQuery({
    queryKey: SIX_YEAR_SUMMARY_KEY,
    queryFn: fetchSixYearSummary,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [editingFocus, setEditingFocus] = useState(false);
  const [focusAncora, setFocusAncora] = useState("");
  const [focusTrilha, setFocusTrilha] = useState("");
  const [feriasOpen, setFeriasOpen] = useState<boolean | null>(null);
  const [generatedFeed, setGeneratedFeed] = useState<SixYearFeedTokenResponse | null>(null);

  if (isLoading && !summary) {
    return (
      <div className="space-y-4 animate-pulse" aria-busy="true" aria-label="Carregando Plano 6º Ano">
        <div className="h-32 rounded-2xl bg-surface border border-line-subtle" />
        <div className="h-48 rounded-2xl bg-surface border border-line-subtle" />
        <div className="h-64 rounded-2xl bg-surface border border-line-subtle" />
      </div>
    );
  }

  if (isError || !summary) {
    return (
      <div className="bg-surface border border-line-subtle rounded-2xl p-6 text-center space-y-3">
        <p className="text-sm font-semibold text-ink-primary">
          Não foi possível carregar o Plano 6º Ano.
        </p>
        <p className="text-xs text-ink-secondary">
          Verifique sua conexão e tente novamente (esta aba funciona online).
        </p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  const { today, plan, rodizio, next_rodizio, week, balance_7030, ritual, ferias } = summary;
  const todayDisplay = DAY_MODE_DISPLAY[today.mode] ?? DAY_MODE_DISPLAY.integral;
  const defaultFeriasOpen = today.date_iso <= "2027-01-24";
  const isFeriasExpanded = feriasOpen ?? defaultFeriasOpen;
  const rodizioDaysLeft = daysRemainingInclusive(today.date_iso, rodizio?.end);

  const handleTodayOverride = async (mode: DayOverrideMode | null) => {
    setBusyAction("override");
    try {
      if (mode === null) {
        await api.sixYear.deleteDayOverride(today.date_iso);
        toast.success("Ajuste de hoje removido.");
      } else {
        await api.sixYear.putDayOverride(today.date_iso, mode);
        toast.success("Modo de hoje atualizado.");
      }
      await invalidateSixYearQueries(queryClient);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao ajustar hoje.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleToggleRoutineMode = async () => {
    setBusyAction("routine");
    try {
      await api.sixYear.patchPlan({ routine_mode_enabled: !plan.routine_mode_enabled });
      await invalidateSixYearQueries(queryClient);
      toast.success(
        !plan.routine_mode_enabled
          ? "Modo rotina ativado: meta diária ajustada pelos plantões."
          : "Modo rotina desativado: meta fixa do planejador restaurada."
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao alterar modo rotina.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleSaveFocus = async () => {
    if (!rodizio?.id) return;
    setBusyAction("focus");
    try {
      await api.sixYear.patchPlan({
        foco_override: {
          [rodizio.id]: {
            ancora70: focusAncora.trim() || null,
            trilha30: focusTrilha.trim() || null,
          },
        },
      });
      await invalidateSixYearQueries(queryClient);
      setEditingFocus(false);
      toast.success("Foco 70/30 atualizado.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar foco.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleResetFocus = async () => {
    if (!rodizio?.id) return;
    setBusyAction("focus");
    try {
      await api.sixYear.patchPlan({
        foco_override: {
          [rodizio.id]: { ancora70: null, trilha30: null },
        },
      });
      await invalidateSixYearQueries(queryClient);
      setEditingFocus(false);
      toast.success("Foco 70/30 restaurado para o padrão do rodízio.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao restaurar foco.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleCycleWeekPattern = async (dayKey: WeekdayKey) => {
    if (!rodizio) return;
    setBusyAction(`pattern-${dayKey}`);
    try {
      const cfg = await api.planner.getConfig();
      const blocks: InternatoBlock[] = cfg?.internato_blocks ? [...cfg.internato_blocks] : [];
      const idx = blocks.findIndex(
        (b) =>
          (rodizio.id && b.id === rodizio.id) ||
          (b.start === rodizio.start && b.end === rodizio.end)
      );
      if (idx < 0) {
        toast.error("Não foi possível localizar o bloco vigente para atualizar o padrão.");
        return;
      }
      const target = { ...blocks[idx] };
      const currentPattern = { ...(target.week_pattern ?? {}) };
      const defaultMode: WeekPatternMode = dayKey === "sab" || dayKey === "dom" ? "folga" : "integral";
      const curMode = (currentPattern[dayKey] as WeekPatternMode | undefined) ?? defaultMode;
      const nextMode = PATTERN_CYCLE[(PATTERN_CYCLE.indexOf(curMode) + 1) % PATTERN_CYCLE.length];
      currentPattern[dayKey] = nextMode;
      target.week_pattern = currentPattern;
      blocks[idx] = target;

      await api.planner.saveInternatoBlocks(blocks);
      await invalidateSixYearQueries(queryClient);
      toast.success(`Padrão de ${dayKey.toUpperCase()} alterado para ${PATTERN_LABELS[nextMode]}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar padrão semanal.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleSelectMarcha = async (marchaId: MarchaId | null) => {
    setBusyAction("marcha");
    try {
      await api.sixYear.putMarcha(week.week_iso, marchaId);
      await invalidateSixYearQueries(queryClient);
      toast.success(marchaId ? "Marcha da semana confirmada." : "Marcha revertida para sugerida.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao atualizar Marcha.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleToggleRitual = async (itemId: string) => {
    setBusyAction(`ritual-${itemId}`);
    try {
      const current = Boolean(ritual.done[itemId]);
      await api.sixYear.patchPlan({
        ritual_done: {
          [ritual.cycle_key]: { [itemId]: !current },
        },
      });
      await invalidateSixYearQueries(queryClient);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar Ritual de Domingo.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleGenerateFeedToken = async () => {
    setBusyAction("feed-gen");
    try {
      const res = await api.sixYear.createFeedToken();
      setGeneratedFeed(res);
      await invalidateSixYearQueries(queryClient);
      toast.success("Link do feed gerado. Copie e guarde agora.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao gerar token do feed.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleRevokeFeedToken = async () => {
    setBusyAction("feed-revoke");
    try {
      await api.sixYear.revokeFeedToken();
      setGeneratedFeed(null);
      await invalidateSixYearQueries(queryClient);
      toast.success("Link do feed revogado.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao revogar token.");
    } finally {
      setBusyAction(null);
    }
  };

  const copyText = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copiado!`);
    } catch {
      toast.error("Não foi possível copiar para a área de transferência.");
    }
  };

  const currentMarchaMeta = MARCHAS_6ANO[week.marcha_id] ?? MARCHAS_6ANO["3_normal"];
  const suggestedMarchaMeta = MARCHAS_6ANO[week.suggested_marcha_id] ?? MARCHAS_6ANO["3_normal"];

  return (
    <div className="space-y-5 pb-10">
      {/* 1. HOJE */}
      <section
        aria-labelledby="six-year-today-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="space-y-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="six-year-today-heading" className="text-base sm:text-lg font-bold text-ink-primary">
                Hoje ({today.date_iso})
              </h2>
              <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-primary/10 text-primary border border-primary/25">
                {todayDisplay.label}
              </span>
              <span className="text-[11px] text-ink-muted">
                origem: {DAY_SOURCE_LABELS[today.source] ?? today.source}
              </span>
            </div>
            <p className="text-xs sm:text-sm text-ink-secondary">{today.guidance}</p>
          </div>

          <div className="flex items-center gap-3 shrink-0 bg-elevated/60 border border-line-subtle rounded-xl px-3.5 py-2.5">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                Meta de hoje
              </div>
              <div className="text-xl font-extrabold text-ink-primary leading-tight">
                {today.goal_questions} <span className="text-xs font-medium text-ink-secondary">questões</span>
              </div>
              {today.reviews_optional && (
                <div className="text-[11px] text-normal font-medium">Revisões FSRS opcionais</div>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-line-subtle">
          <span className="text-[11px] font-semibold text-ink-muted mr-1">Ajuste rápido:</span>
          {(
            [
              ["pos_plantao", "Pós-plantão"],
              ["folga", "Folga"],
              ["meio_periodo", "Meio período"],
              ["integral", "Integral"],
            ] as Array<[DayOverrideMode, string]>
          ).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              disabled={busyAction !== null}
              onClick={() => void handleTodayOverride(mode)}
              className={clsx(
                "px-2.5 py-1 rounded-lg border text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50",
                today.source === "override" && today.mode === mode
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-elevated text-ink-primary border-line-subtle hover:border-line-strong"
              )}
            >
              {label}
            </button>
          ))}
          {today.source === "override" && (
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => void handleTodayOverride(null)}
              className="px-2.5 py-1 rounded-lg border border-line-subtle text-xs font-medium text-ink-secondary hover:text-ink-primary cursor-pointer"
            >
              Limpar ajuste
            </button>
          )}
        </div>
      </section>

      {/* 2. RODÍZIO VIGENTE */}
      <section
        aria-labelledby="six-year-rodizio-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="space-y-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 id="six-year-rodizio-heading" className="text-base font-bold text-ink-primary">
                {rodizio ? `Rodízio vigente: ${rodizio.label || rodizio.area}` : "Fora de rodízio cadastrado"}
              </h3>
              {rodizio && (
                <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-elevated border border-line-subtle text-ink-secondary">
                  {rodizio.start} → {rodizio.end}
                  {rodizioDaysLeft !== null && rodizioDaysLeft >= 0
                    ? ` · ${rodizioDaysLeft}d restante(s)`
                    : ""}
                </span>
              )}
            </div>
            {(rodizio?.next || next_rodizio) && (
              <p className="text-xs text-ink-muted">
                Próximo: {(rodizio?.next || next_rodizio)?.label} (início {(rodizio?.next || next_rodizio)?.start})
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <a
              href={NOVO_PEP_ESTEIRA_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-elevated border border-line-subtle text-xs font-semibold text-ink-primary hover:border-line-strong"
            >
              Esteira <ExternalLink size={12} />
            </a>
            <a
              href={NOVO_PEP_LOGBOOK_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-elevated border border-line-subtle text-xs font-semibold text-ink-primary hover:border-line-strong"
            >
              Logbook <ExternalLink size={12} />
            </a>
          </div>
        </div>

        {rodizio && (
          <div className="space-y-3">
            {/* Foco 70/30 editável inline */}
            <div className="p-3.5 rounded-xl bg-elevated/60 border border-line-subtle space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                  <Sparkles size={14} className="text-primary" />
                  Foco semanal 70/30
                  {rodizio.foco_effective.is_override && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary font-semibold">
                      personalizado
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-2">
                  {rodizio.foco_effective.is_override && !editingFocus && (
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void handleResetFocus()}
                      className="inline-flex items-center gap-1 text-[11px] text-ink-secondary hover:text-ink-primary cursor-pointer"
                    >
                      <RotateCcw size={12} /> Restaurar padrão
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (!editingFocus) {
                        setFocusAncora(rodizio.foco_effective.ancora70);
                        setFocusTrilha(rodizio.foco_effective.trilha30);
                      }
                      setEditingFocus((v) => !v);
                    }}
                    className="text-xs font-semibold text-primary hover:underline cursor-pointer"
                  >
                    {editingFocus ? "Cancelar" : "Editar"}
                  </button>
                </div>
              </div>

              {editingFocus ? (
                <div className="space-y-2">
                  <div>
                    <label className="block text-[11px] font-semibold text-ink-secondary mb-1">
                      Âncora 70%
                    </label>
                    <input
                      type="text"
                      value={focusAncora}
                      onChange={(e) => setFocusAncora(e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-ink-secondary mb-1">
                      Trilha 30%
                    </label>
                    <input
                      type="text"
                      value={focusTrilha}
                      onChange={(e) => setFocusTrilha(e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <button
                    type="button"
                    disabled={busyAction !== null}
                    onClick={() => void handleSaveFocus()}
                    className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
                  >
                    Salvar foco
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
                  <div>
                    <span className="font-semibold text-ink-secondary">70% Âncora: </span>
                    <span className="text-ink-primary">{rodizio.foco_effective.ancora70 || "—"}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-ink-secondary">30% Trilha: </span>
                    <span className="text-ink-primary">{rodizio.foco_effective.trilha30 || "—"}</span>
                  </div>
                </div>
              )}
            </div>

            {rodizio.micro_habito && (
              <div className="text-xs text-ink-secondary">
                <strong className="text-ink-primary">Micro-hábito:</strong> {rodizio.micro_habito}
              </div>
            )}

            {rodizio.procedimentos_alvo && rodizio.procedimentos_alvo.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-xs font-semibold text-ink-secondary">Procedimentos-alvo</div>
                <ul className="space-y-1">
                  {rodizio.procedimentos_alvo.map((proc) => (
                    <li
                      key={proc}
                      className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-elevated/40 border border-line-subtle text-xs text-ink-primary"
                    >
                      <span className="min-w-0 break-words">{proc}</span>
                      <a
                        href={NOVO_PEP_LOGBOOK_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                      >
                        Logbook <ExternalLink size={11} />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 3. MODO ROTINA */}
      <section className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <ShieldCheck size={18} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-bold text-ink-primary">
              Ajustar a meta diária pelos plantões
            </div>
            <p className="text-xs text-ink-secondary">
              {plan.routine_mode_enabled
                ? "Ativo: Dashboard, Perfil Adaptativo e streak protegido seguem a rotina do 6º Ano."
                : "Desligado: o calendário e o padrão semanal abaixo continuam editáveis, mas sem efeito na meta diária."}
            </p>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={plan.routine_mode_enabled}
          disabled={busyAction !== null}
          onClick={() => void handleToggleRoutineMode()}
          className={clsx(
            "shrink-0 px-3.5 py-2 rounded-xl text-xs font-bold transition-colors cursor-pointer disabled:opacity-50",
            plan.routine_mode_enabled
              ? "bg-primary text-primary-foreground"
              : "bg-elevated text-ink-primary border border-line-subtle hover:border-line-strong"
          )}
        >
          {plan.routine_mode_enabled ? "Modo rotina: Ligado" : "Modo rotina: Desligado"}
        </button>
      </section>

      {!plan.routine_mode_enabled && (
        <div className="px-4 py-2.5 rounded-xl bg-warning/10 border border-warning/30 text-xs text-warning flex items-center gap-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>Modo rotina desligado — calendário e padrão semanal estão sem efeito na meta.</span>
        </div>
      )}

      {/* 4. CALENDÁRIO DE PLANTÕES */}
      <ShiftCalendarSection
        todayIso={today.date_iso}
        routineEnabled={plan.routine_mode_enabled}
        rodizio={rodizio}
      />

      {/* 5. PADRÃO SEMANAL DO RODÍZIO */}
      {rodizio && (
        <section
          aria-labelledby="six-year-pattern-heading"
          className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-3"
        >
          <div>
            <h3 id="six-year-pattern-heading" className="text-base font-bold text-ink-primary">
              Padrão semanal do rodízio ({rodizio.label || rodizio.area})
            </h3>
            <p className="text-xs text-ink-secondary">
              Clique em cada dia para alternar entre Integral, Meio período e Folga (não regenera seu cronograma).
            </p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-7 gap-2">
            {WEEKDAY_CHIPS.map((wd) => {
              const defaultMode: WeekPatternMode =
                wd.key === "sab" || wd.key === "dom" ? "folga" : "integral";
              const mode =
                (rodizio.week_pattern?.[wd.key] as WeekPatternMode | undefined) ?? defaultMode;
              return (
                <button
                  key={wd.key}
                  type="button"
                  disabled={busyAction !== null}
                  onClick={() => void handleCycleWeekPattern(wd.key)}
                  className="p-2.5 rounded-xl border border-line-subtle bg-elevated/60 hover:border-line-strong text-center transition-colors cursor-pointer disabled:opacity-50"
                >
                  <div className="text-[11px] font-bold text-ink-primary">{wd.short}</div>
                  <div className="text-[11px] text-primary font-semibold mt-0.5">
                    {PATTERN_LABELS[mode]}
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* 6. MARCHA DA SEMANA */}
      <section
        aria-labelledby="six-year-marcha-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
              <Gauge size={18} />
            </div>
            <div>
              <h3 id="six-year-marcha-heading" className="text-base font-bold text-ink-primary">
                Marcha da semana ({week.week_iso})
              </h3>
              <p className="text-xs text-ink-secondary">
                Sugerida: <strong>{suggestedMarchaMeta.short}</strong> (peso de plantões na semana:{" "}
                {week.shift_weight}) · Atual:{" "}
                <strong>
                  {currentMarchaMeta.short} ({week.marcha_source})
                </strong>
              </p>
            </div>
          </div>
          <div className="text-right shrink-0 bg-elevated/60 border border-line-subtle rounded-xl px-3 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Meta semanal resultante
            </div>
            <div className="text-lg font-extrabold text-ink-primary">{week.weekly_goal} questões</div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {MARCHA_ORDER.map((mId) => {
            const m = MARCHAS_6ANO[mId];
            const isSelected = week.marcha_id === mId;
            return (
              <button
                key={mId}
                type="button"
                disabled={busyAction !== null}
                onClick={() => void handleSelectMarcha(mId)}
                className={clsx(
                  "p-3 rounded-xl border text-left transition-all cursor-pointer disabled:opacity-50",
                  isSelected
                    ? "bg-primary/10 border-primary ring-1 ring-primary/30"
                    : "bg-elevated/40 border-line-subtle hover:border-line-strong"
                )}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-bold text-ink-primary">{m.short}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface border border-line-subtle text-ink-secondary">
                    {m.badge}
                  </span>
                </div>
                <p className="text-[11px] text-ink-secondary mt-1 line-clamp-2">{m.resumo}</p>
              </button>
            );
          })}
        </div>

        {week.marcha_source === "confirmada" && (
          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => void handleSelectMarcha(null)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-secondary hover:text-ink-primary cursor-pointer"
          >
            <RotateCcw size={13} /> Voltar para sugerida ({suggestedMarchaMeta.short})
          </button>
        )}
      </section>

      {/* 7. RITUAL DE DOMINGO + SALDO 70/30 REAL */}
      <section
        aria-labelledby="six-year-ritual-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <Activity size={18} />
          </div>
          <div>
            <h3 id="six-year-ritual-heading" className="text-base font-bold text-ink-primary">
              Ritual de Domingo & Saldo 70/30 Real
            </h3>
            <p className="text-xs text-ink-secondary">
              Ciclo {ritual.cycle_key} · Janela 70/30: {balance_7030.window_from} a {balance_7030.window_to}
            </p>
          </div>
        </div>

        {/* Saldo 70/30 */}
        <div className="p-3.5 rounded-xl bg-elevated/60 border border-line-subtle space-y-2">
          {balance_7030.total === 0 ? (
            <p className="text-xs text-ink-secondary">Sem questões nos últimos 7 dias.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-ink-primary">
                  Âncora ({balance_7030.anchor_areas.join(", ") || "Geral"}):{" "}
                  <strong>{balance_7030.anchor_pct}%</strong> ({balance_7030.anchor}/{balance_7030.total})
                </span>
                <span className="text-ink-secondary">
                  Outras: {balance_7030.other_pct}% ({balance_7030.other}) · Meta: {balance_7030.target_anchor_pct}%
                </span>
              </div>
              <div className="h-2.5 w-full rounded-full bg-surface overflow-hidden border border-line-subtle flex">
                <div
                  className="bg-primary h-full transition-all"
                  style={{ width: `${Math.min(100, balance_7030.anchor_pct ?? 0)}%` }}
                />
                <div
                  className="bg-ink-muted/40 h-full transition-all"
                  style={{ width: `${Math.min(100, balance_7030.other_pct ?? 0)}%` }}
                />
              </div>
            </>
          )}
        </div>

        {/* Checklist */}
        <ul className="space-y-2">
          {RITUAL_DOMINGO_DATA.map((item) => {
            const checked = Boolean(ritual.done[item.id]);
            return (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={busyAction !== null}
                  onClick={() => void handleToggleRitual(item.id)}
                  className={clsx(
                    "w-full flex items-start gap-2.5 p-2.5 rounded-xl border text-left transition-colors cursor-pointer",
                    checked
                      ? "bg-normal-bg/50 border-normal/30 text-ink-secondary"
                      : "bg-elevated/40 border-line-subtle text-ink-primary hover:border-line-strong"
                  )}
                >
                  <span
                    className={clsx(
                      "mt-0.5 w-4 h-4 rounded flex items-center justify-center border shrink-0",
                      checked
                        ? "bg-normal text-white border-normal"
                        : "bg-surface border-line-strong"
                    )}
                  >
                    {checked && <Check size={12} />}
                  </span>
                  <span className={clsx("text-xs", checked && "line-through")}>{item.text}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {/* 8. FÉRIAS (SÓ LEITURA, COLAPSÁVEL) */}
      <section className="bg-surface border border-line-subtle rounded-2xl overflow-hidden">
        <button
          type="button"
          onClick={() => setFeriasOpen(!isFeriasExpanded)}
          aria-expanded={isFeriasExpanded}
          className="w-full p-4 sm:p-5 flex items-center justify-between gap-3 text-left cursor-pointer hover:bg-elevated/40 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <Calendar size={18} className="text-primary shrink-0" />
            <div>
              <h3 className="text-base font-bold text-ink-primary">
                Pré-Temporada de Férias (30/11/2026 – 24/01/2027)
              </h3>
              <p className="text-xs text-ink-secondary">
                Cronograma de referência (somente leitura)
                {ferias.current_week_id ? ` · Semana ativa: ${ferias.current_week_id}` : ""}
              </p>
            </div>
          </div>
          {isFeriasExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>

        {isFeriasExpanded && (
          <div className="px-4 sm:px-5 pb-5 space-y-2.5 border-t border-line-subtle pt-4">
            {FERIAS_SEMANAS.map((sem) => {
              const isCurrent = ferias.current_week_id === sem.id;
              return (
                <div
                  key={sem.id}
                  className={clsx(
                    "p-3 rounded-xl border text-xs space-y-1",
                    isCurrent
                      ? "bg-primary/10 border-primary"
                      : sem.isFreeWeek
                        ? "bg-normal-bg/40 border-normal/30"
                        : "bg-elevated/40 border-line-subtle"
                  )}
                >
                  <div className="font-bold text-ink-primary flex flex-wrap items-center gap-2">
                    <span>{sem.label}</span>
                    {isCurrent && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-primary text-primary-foreground">
                        Semana atual
                      </span>
                    )}
                  </div>
                  <p className="text-ink-secondary">
                    <strong className="text-ink-primary">Conteúdo:</strong> {sem.focoConteudo}
                  </p>
                  <p className="text-ink-secondary">
                    <strong className="text-ink-primary">Esteira:</strong> {sem.focoExames}
                  </p>
                  <p className="text-ink-secondary">
                    <strong className="text-ink-primary">Habilidades:</strong> {sem.focoHabilidade}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* 9. INTEGRAÇÃO COM O NOVO-PEP & CALENDÁRIO ICS */}
      <section
        aria-labelledby="six-year-feed-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-3"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
              <Link2 size={18} />
            </div>
            <div>
              <h3 id="six-year-feed-heading" className="text-base font-bold text-ink-primary">
                Integração com o Novo-PEP & Calendário (ICS)
              </h3>
              <p className="text-xs text-ink-secondary">
                Link privado por token (somente modos/metas e plantões — sem currículo, marcos ou e-mail).
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => void handleGenerateFeedToken()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
            >
              {busyAction === "feed-gen" && <Loader2 size={13} className="animate-spin" />}
              {plan.has_feed_token ? "Rotacionar link do feed" : "Gerar link do feed"}
            </button>
            {plan.has_feed_token && (
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() => void handleRevokeFeedToken()}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-destructive/40 text-destructive text-xs font-semibold hover:bg-destructive/10 cursor-pointer disabled:opacity-50"
              >
                <Trash2 size={13} /> Revogar
              </button>
            )}
          </div>
        </div>

        {generatedFeed && (
          <div className="p-3.5 rounded-xl bg-warning/10 border border-warning/30 space-y-2.5">
            <p className="text-xs font-bold text-warning">
              Guarde agora: estes links não serão exibidos novamente após sair desta tela.
            </p>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={generatedFeed.feed_url}
                  aria-label="URL do feed JSON para o Novo-PEP"
                  className="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-surface border border-line-subtle font-mono text-[11px] text-ink-primary"
                />
                <button
                  type="button"
                  onClick={() => void copyText(generatedFeed.feed_url, "Link do feed JSON")}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-surface border border-line-subtle text-xs font-semibold text-ink-primary cursor-pointer shrink-0"
                >
                  <Copy size={13} /> Copiar JSON
                </button>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={generatedFeed.ics_url}
                  aria-label="URL do feed ICS de calendário"
                  className="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-surface border border-line-subtle font-mono text-[11px] text-ink-primary"
                />
                <button
                  type="button"
                  onClick={() => void copyText(generatedFeed.ics_url, "Link ICS")}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-surface border border-line-subtle text-xs font-semibold text-ink-primary cursor-pointer shrink-0"
                >
                  <Copy size={13} /> Copiar ICS
                </button>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
