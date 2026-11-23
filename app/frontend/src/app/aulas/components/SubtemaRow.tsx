"use client";

import Link from "next/link";
import clsx from "clsx";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Play,
  Zap,
} from "lucide-react";
import { buildLessonCycleQuizUrl } from "@/lib/themeJourney";
import type { LessonCyclePhase, LessonItem, LessonStudyCycle } from "@/types/api";
import {
  type SubtemaGroup,
  formatDuration,
  getAreaDotClass,
  getShortAreaLabel,
} from "../lessonHelpers";
import { LessonRowCompact } from "./LessonRowCompact";

export function SubtemaRow({
  subGroup,
  subCycle,
  isExpanded,
  onToggleExpand,
  isComplementsOpen,
  onToggleComplements,
  showWeekBadge,
  showAreaBadge,
  currentWeek,
  defaultPreQuestions,
  defaultPostQuestions,
  savingProgress,
  savingCycle,
  onSelectLesson,
  onToggleQuickComplete,
  onToggleCyclePhase,
}: {
  subGroup: SubtemaGroup;
  subCycle: LessonStudyCycle | undefined;
  isExpanded: boolean;
  onToggleExpand: () => void;
  isComplementsOpen: boolean;
  onToggleComplements: () => void;
  showWeekBadge: boolean;
  showAreaBadge: boolean;
  currentWeek: number | null;
  defaultPreQuestions: number;
  defaultPostQuestions: number;
  savingProgress: boolean;
  savingCycle: boolean;
  onSelectLesson: (lesson: LessonItem, subtema?: string) => void;
  onToggleQuickComplete: (lesson: LessonItem) => void;
  onToggleCyclePhase: (subtema: string, phase: LessonCyclePhase, currentlyDone: boolean) => void;
}) {
  const complements = [...subGroup.optionalMedwayLessons, ...subGroup.extraMedcofLessons];
  const subNextLesson =
    subGroup.mainLessons.find((l) => l.progress.status !== "completed") ??
    subGroup.mainLessons[0] ??
    complements[0] ??
    null;

  const subMainAllDone =
    subGroup.mainTotal > 0 && subGroup.mainCompleted >= subGroup.mainTotal;
  const preDone = Boolean(subCycle?.pre_done);
  const postDone = Boolean(subCycle?.post_done);
  const preRequired = defaultPreQuestions > 0;
  const cycleAllDone = (!preRequired || preDone) && subMainAllDone && postDone;

  const nextStep: "pre" | "lesson" | "post" | "done" =
    preRequired && !preDone && subGroup.mainCompleted === 0
      ? "pre"
      : !subMainAllDone && subGroup.mainTotal > 0
      ? "lesson"
      : !postDone
      ? "post"
      : "done";

  const progressPct =
    subGroup.mainTotal > 0
      ? Math.round((subGroup.mainCompleted / subGroup.mainTotal) * 100)
      : 0;

  const showComplementsInline = subGroup.mainLessons.length === 0 && complements.length > 0;
  const complementsVisible = showComplementsInline || isComplementsOpen;

  return (
    <article
      className={clsx(
        "transition-colors",
        isExpanded && "bg-canvas/30",
        subGroup.isCurrentWeek && showWeekBadge && "border-l-2 border-l-primary"
      )}
    >
      {/* Linha Principal Compacta */}
      <div className="px-4 py-3 flex items-center justify-between gap-3 hover:bg-elevated/35 transition-colors">
        <button
          type="button"
          onClick={onToggleExpand}
          aria-expanded={isExpanded}
          className="flex-1 min-w-0 flex items-start gap-2.5 text-left cursor-pointer group"
        >
          <span className="mt-0.5 text-ink-muted group-hover:text-ink-primary transition-colors shrink-0">
            {isExpanded ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
          </span>

          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <h3 className="text-sm font-semibold text-ink-primary leading-snug group-hover:text-primary transition-colors break-words">
                {subGroup.subtema}
              </h3>

              {showWeekBadge && subGroup.isCurrentWeek && currentWeek !== null && (
                <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded-xs bg-primary/10 text-primary border border-primary/25 shrink-0">
                  Semana {currentWeek}
                </span>
              )}

              {showAreaBadge && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.2 rounded-xs bg-elevated text-ink-secondary border border-line-subtle shrink-0">
                  <span className={clsx("w-1.5 h-1.5 rounded-full", getAreaDotClass(subGroup.area))} />
                  {getShortAreaLabel(subGroup.area)}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              {subGroup.mainTotal > 0 ? (
                <>
                  <div className="w-16 h-1 rounded-full bg-elevated overflow-hidden shrink-0">
                    <div
                      className={clsx(
                        "h-full rounded-full transition-all",
                        subMainAllDone ? "bg-success" : "bg-primary"
                      )}
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <span
                    className={clsx(
                      "font-mono-lab tabular-nums",
                      subMainAllDone ? "text-success font-medium" : "text-ink-secondary"
                    )}
                  >
                    {subGroup.mainCompleted}/{subGroup.mainTotal} principais
                    {subGroup.mainRemainingSeconds > 0
                      ? ` • ${formatDuration(subGroup.mainRemainingSeconds)}`
                      : " • Concluído"}
                  </span>
                </>
              ) : (
                <span className="text-ink-muted">
                  {complements.length} {complements.length === 1 ? "complemento" : "complementos"}
                </span>
              )}
            </div>
          </div>
        </button>

        {/* Lado Direito: Indicador discreto do Ciclo + 1 Ação Principal */}
        <div className="flex items-center gap-3 shrink-0">
          <div
            className="hidden sm:flex items-center gap-1.5 text-[10px] text-ink-muted"
            title={`Ciclo: ${preRequired ? `Pré (${preDone ? "feito" : "pendente"}) • ` : ""}Aula (${subMainAllDone ? "feita" : "pendente"}) • Pós (${postDone ? "feito" : "pendente"})`}
          >
            {preRequired && (
              <span className="inline-flex items-center gap-1">
                <span
                  className={clsx(
                    "w-2 h-2 rounded-full",
                    preDone
                      ? "bg-success"
                      : nextStep === "pre"
                      ? "bg-primary ring-2 ring-primary/25"
                      : "bg-line-strong"
                  )}
                />
                <span className={preDone ? "text-success" : nextStep === "pre" ? "text-ink-primary font-medium" : ""}>
                  Pré
                </span>
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <span
                className={clsx(
                  "w-2 h-2 rounded-full",
                  subMainAllDone
                    ? "bg-success"
                    : nextStep === "lesson"
                    ? "bg-primary ring-2 ring-primary/25"
                    : "bg-line-strong"
                )}
              />
              <span className={subMainAllDone ? "text-success" : nextStep === "lesson" ? "text-ink-primary font-medium" : ""}>
                Aula
              </span>
            </span>
            <span className="inline-flex items-center gap-1">
              <span
                className={clsx(
                  "w-2 h-2 rounded-full",
                  postDone
                    ? "bg-success"
                    : nextStep === "post"
                    ? "bg-primary ring-2 ring-primary/25"
                    : "bg-line-strong"
                )}
              />
              <span className={postDone ? "text-success" : nextStep === "post" ? "text-ink-primary font-medium" : ""}>
                Pós
              </span>
            </span>
          </div>

          {nextStep === "pre" ? (
            <Link
              href={buildLessonCycleQuizUrl({
                subtema: subGroup.subtema,
                phase: "pre",
                target: defaultPreQuestions,
                returnLessonId: subNextLesson?.id,
              })}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors whitespace-nowrap"
            >
              <Zap className="w-3 h-3" />
              Pré {defaultPreQuestions}q
            </Link>
          ) : nextStep === "lesson" && subNextLesson ? (
            <button
              type="button"
              onClick={() => onSelectLesson(subNextLesson, subGroup.subtema)}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap"
            >
              <Play className="w-3 h-3 fill-current" />
              Assistir
            </button>
          ) : nextStep === "post" ? (
            <Link
              href={buildLessonCycleQuizUrl({
                subtema: subGroup.subtema,
                phase: "post",
                target: defaultPostQuestions,
                returnLessonId: subNextLesson?.id,
              })}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors whitespace-nowrap"
            >
              <Zap className="w-3 h-3" />
              Pós {defaultPostQuestions}q
            </Link>
          ) : cycleAllDone ? (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-xs bg-success/10 text-success border border-success/30 text-[11px] font-semibold whitespace-nowrap">
              <CheckCircle2 className="w-3 h-3" />
              Ciclo ✓
            </span>
          ) : null}
        </div>
      </div>

      {/* Conteúdo Expandido */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-2.5 border-t border-line-subtle/60 bg-canvas/40 space-y-3">
          {/* Barra discreta do Ciclo + Link Análise */}
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-line-subtle/60 text-[11px]">
            <div className="flex flex-wrap items-center gap-1.5">
              {preRequired && (
                <div className="inline-flex items-center gap-1">
                  <Link
                    href={buildLessonCycleQuizUrl({
                      subtema: subGroup.subtema,
                      phase: "pre",
                      target: defaultPreQuestions,
                      returnLessonId: subNextLesson?.id,
                    })}
                    className={clsx(
                      "inline-flex items-center gap-1 px-2 py-1 rounded-xs font-semibold border transition-colors",
                      preDone
                        ? "bg-success/10 text-success border-success/30 hover:bg-success/15"
                        : "bg-surface text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
                    )}
                  >
                    {preDone ? <CheckCircle2 className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                    1. Pré ({defaultPreQuestions}q)
                    {preDone && subCycle?.pre_accuracy != null ? ` • ${subCycle.pre_accuracy}%` : ""}
                  </Link>
                  <button
                    type="button"
                    disabled={savingCycle}
                    onClick={() => onToggleCyclePhase(subGroup.subtema, "pre", preDone)}
                    className="px-1.5 py-1 rounded-xs text-[10px] text-ink-muted hover:text-ink-primary hover:bg-elevated cursor-pointer"
                  >
                    {preDone ? "Reabrir" : "Já fiz"}
                  </button>
                </div>
              )}

              {subNextLesson && (
                <>
                  {preRequired && <span className="text-ink-muted">→</span>}
                  <button
                    type="button"
                    onClick={() => onSelectLesson(subNextLesson, subGroup.subtema)}
                    className={clsx(
                      "inline-flex items-center gap-1 px-2 py-1 rounded-xs font-semibold border transition-colors cursor-pointer",
                      subMainAllDone
                        ? "bg-success/10 text-success border-success/30 hover:bg-success/15"
                        : "bg-surface text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
                    )}
                  >
                    {subMainAllDone ? (
                      <CheckCircle2 className="w-3 h-3" />
                    ) : (
                      <Play className="w-3 h-3 fill-current" />
                    )}
                    {preRequired ? "2. Aula" : "1. Aula"}
                    {subGroup.mainTotal > 0 ? ` (${subGroup.mainCompleted}/${subGroup.mainTotal})` : ""}
                  </button>
                </>
              )}

              <span className="text-ink-muted">→</span>

              <div className="inline-flex items-center gap-1">
                <Link
                  href={buildLessonCycleQuizUrl({
                    subtema: subGroup.subtema,
                    phase: "post",
                    target: defaultPostQuestions,
                    returnLessonId: subNextLesson?.id,
                  })}
                  className={clsx(
                    "inline-flex items-center gap-1 px-2 py-1 rounded-xs font-semibold border transition-colors",
                    postDone
                      ? "bg-success/10 text-success border-success/30 hover:bg-success/15"
                      : "bg-surface text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
                  )}
                >
                  {postDone ? <CheckCircle2 className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                  {preRequired ? "3. Pós" : "2. Pós"} ({defaultPostQuestions}q)
                  {postDone && subCycle?.post_accuracy != null ? ` • ${subCycle.post_accuracy}%` : ""}
                </Link>
                <button
                  type="button"
                  disabled={savingCycle}
                  onClick={() => onToggleCyclePhase(subGroup.subtema, "post", postDone)}
                  className="px-1.5 py-1 rounded-xs text-[10px] text-ink-muted hover:text-ink-primary hover:bg-elevated cursor-pointer"
                >
                  {postDone ? "Reabrir" : "Já fiz"}
                </button>
              </div>
            </div>

            <Link
              href={`/analise?tab=cobertura&subtema=${encodeURIComponent(subGroup.subtema)}`}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-xs bg-surface hover:bg-elevated text-ink-secondary hover:text-ink-primary font-medium border border-line-subtle transition-colors"
            >
              Análise <ExternalLink className="w-3 h-3" />
            </Link>
          </div>

          {/* Aulas Principais Medway diretamente visíveis */}
          {subGroup.mainLessons.length > 0 && (
            <div className="space-y-1">
              {subGroup.mainLessons.map((lesson) => (
                <LessonRowCompact
                  key={lesson.id}
                  item={lesson}
                  savingProgress={savingProgress}
                  onSelect={(l) => onSelectLesson(l, subGroup.subtema)}
                  onToggleComplete={onToggleQuickComplete}
                  showKindBadge={false}
                />
              ))}
            </div>
          )}

          {/* Gaveta única para Flash/Revisão Medway + Extras MedCof */}
          {complements.length > 0 && (
            <div className="space-y-1.5">
              {!showComplementsInline && (
                <button
                  type="button"
                  onClick={onToggleComplements}
                  aria-expanded={complementsVisible}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xs text-[11px] font-semibold text-ink-secondary hover:text-ink-primary bg-surface border border-line-subtle hover:bg-elevated transition-colors cursor-pointer"
                >
                  {complementsVisible ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5" />
                  )}
                  Complementos &amp; MedCof ({complements.length})
                </button>
              )}

              {complementsVisible && (
                <div className="space-y-1 pl-2 border-l-2 border-line-subtle">
                  {complements.map((lesson) => (
                    <LessonRowCompact
                      key={lesson.id}
                      item={lesson}
                      savingProgress={savingProgress}
                      onSelect={(l) => onSelectLesson(l, subGroup.subtema)}
                      onToggleComplete={onToggleQuickComplete}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
