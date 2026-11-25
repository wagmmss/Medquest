"use client";

import React, { memo } from "react";
import Link from "next/link";
import clsx from "clsx";
import {
  Activity,
  AlertCircle,
  ArrowUpDown,
  CalendarDays,
  Check,
  Clock,
  Gem,
  GripVertical,
  Loader2,
  Play,
  PlayCircle,
  Stethoscope,
  TrendingUp,
} from "lucide-react";
import {
  LessonsSummaryBySubtemaItem,
  PlannerOrganizationMode,
  PlannerTopic,
  PlannerTopicProgressMap,
  PlannerWeek,
  PlannerWeekProgress,
} from "@/types/api";

export const getAreaColorClass = (areaName: string) => {
  const name = areaName.toLowerCase();
  if (name.includes("preventiva")) return "bg-area-preventiva text-area-preventiva";
  if (name.includes("pediatria")) return "bg-area-pediatria text-area-pediatria";
  if (name.includes("go") || name.includes("ginecologia")) return "bg-area-go text-area-go";
  if (name.includes("cirurgia")) return "bg-area-cirurgia text-area-cirurgia";
  return "bg-area-clinica text-area-clinica";
};

export const formatHours = (hours: number) =>
  hours.toLocaleString("pt-BR", {
    minimumFractionDigits: Number.isInteger(hours) ? 0 : 1,
    maximumFractionDigits: 1,
  });

const formatRemainingSeconds = (seconds?: number) => {
  if (!seconds || seconds <= 0) return "";
  const totalMin = Math.round(seconds / 60);
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
};

export const TopicRow = memo(function TopicRow({
  t,
  completed,
  toggleTopic,
  week,
  index,
  isDragging,
  isDragOverBefore,
  onDragStartTopic,
  onDragEnd,
  onDragOverTopic,
  onDropTopic,
  onOpenMoveModalTopic,
  lessonSummary,
}: {
  t: PlannerTopic;
  completed: boolean;
  toggleTopic: (week: number, subtema: string, completed: boolean) => void;
  week: number;
  index: number;
  isDragging?: boolean;
  isDragOverBefore?: boolean;
  onDragStartTopic?: (week: number, subtema: string, index: number, e: React.DragEvent) => void;
  onDragEnd?: () => void;
  onDragOverTopic?: (week: number, index: number, e: React.DragEvent) => void;
  onDropTopic?: (week: number, index: number, e: React.DragEvent) => void;
  onOpenMoveModalTopic?: (subtema: string, currentWeek: number) => void;
  lessonSummary?: LessonsSummaryBySubtemaItem;
}) {
  const key = `planner-topic-${week}-${t.subtema}`;
  const isChecked = completed;

  return (
    <div className="relative flex flex-col">
      {isDragOverBefore && <div className="h-1 w-full bg-accent rounded-xs mb-1" />}
      <div
        draggable={Boolean(onDragStartTopic)}
        onDragStart={onDragStartTopic ? (e) => onDragStartTopic(week, t.subtema, index, e) : undefined}
        onDragEnd={onDragEnd}
        onDragOver={onDragOverTopic ? (e) => onDragOverTopic(week, index, e) : undefined}
        onDrop={onDropTopic ? (e) => onDropTopic(week, index, e) : undefined}
        className={clsx(
          "flex items-start gap-2.5 py-2.5 px-3 rounded-xl border transition-all group",
          isDragging
            ? "opacity-30 border-dashed border-primary bg-primary/10 scale-[0.99] shadow-inner"
            : "border-transparent hover:border-border/60 hover:bg-muted/20"
        )}
      >
        <div
          className="mt-1 shrink-0 text-muted-foreground/40 group-hover:text-primary cursor-grab active:cursor-grabbing hover:bg-primary/10 p-1 rounded-md transition-colors"
          title="Segure e arraste este bloco para mudar de semana ou reorganizar"
          aria-label="Arrastar bloco"
        >
          <GripVertical size={16} />
        </div>

        <div className="relative flex items-center mt-1 shrink-0">
          <input
            type="checkbox"
            id={key}
            className="peer sr-only"
            checked={isChecked}
            onChange={() => toggleTopic(week, t.subtema, isChecked)}
            aria-label={`Concluir tema ${t.subtema}`}
          />
          <label
            htmlFor={key}
            className="w-4 h-4 border border-muted-foreground/40 rounded transition-colors peer-checked:bg-primary peer-checked:border-primary flex items-center justify-center cursor-pointer hover:border-primary/60"
          >
            <Check
              size={10}
              className={clsx("text-primary-foreground transition-opacity", isChecked ? "opacity-100" : "opacity-0")}
              strokeWidth={4}
            />
          </label>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <label
              htmlFor={key}
              className={clsx(
                "font-semibold text-sm leading-snug cursor-pointer transition-colors",
                isChecked ? "text-muted-foreground line-through opacity-70" : "text-foreground group-hover:text-primary"
              )}
            >
              {t.subtema}
            </label>
            {t.priority_tier && t.priority_tier !== "Normal" && (
              <span
                title={t.priority_explanation || "Recomendação adaptativa"}
                className={clsx(
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold border cursor-help",
                  t.priority_tier === "Diamante"
                    ? "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/20"
                    : t.priority_tier === "Alta"
                    ? "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20"
                    : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20"
                )}
              >
                {t.priority_tier === "Diamante" ? (
                  <Gem size={12} className="fill-current" />
                ) : t.priority_tier === "Alta" ? (
                  <TrendingUp size={12} />
                ) : (
                  <AlertCircle size={12} />
                )}
                {t.priority_tier}
              </span>
            )}
            {t.is_internato_essential && (
              <span
                title="Tema essencial do dia a dia do internato (PS, Enfermaria, UBS ou Sala de Parto)"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border bg-accent/10 text-accent border-accent/25 cursor-help"
              >
                <Stethoscope size={11} />
                Internato
              </span>
            )}
          </div>

          <div className="text-xs text-muted-foreground flex items-center flex-wrap gap-1.5 mt-1.5">
            <span className={clsx("font-medium", getAreaColorClass(t.area).split(" ")[1])}>{t.area}</span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <Clock size={11} /> {formatHours(t.estimated_theory_hours)}h teóricas + {formatHours(t.estimated_practice_hours)}h questões ={" "}
              {formatHours(t.estimated_hours)}h
            </span>
            <span>•</span>
            <span>
              {t.questions_available} questões disponíveis
              {t.incidence_source === "target_banks" && typeof t.target_questions_count === "number"
                ? ` (${t.target_questions_count} nas suas bancas)`
                : ""}
            </span>
          </div>

          <div className="mt-2.5 flex items-center gap-2 flex-wrap">
            <Link
              href={`/analise?tab=cobertura&subtema=${encodeURIComponent(t.subtema)}`}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-accent text-white text-xs font-semibold rounded-md"
            >
              Abrir tema
            </Link>
            <Link
              href={`/estudar?subtema=${encodeURIComponent(t.subtema)}&limit=25`}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-accent/10 hover:bg-accent/20 text-accent text-xs font-semibold rounded-md transition-colors border border-accent/20"
            >
              <Play size={11} className="fill-current" /> Praticar Questões
            </Link>
            {lessonSummary && lessonSummary.essential_total > 0 ? (
              <Link
                href={
                  lessonSummary.next_lesson_id
                    ? `/aulas?subtema=${encodeURIComponent(t.subtema)}&lesson=${lessonSummary.next_lesson_id}`
                    : `/aulas?subtema=${encodeURIComponent(t.subtema)}`
                }
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold rounded-md transition-colors border border-primary/20"
              >
                <PlayCircle size={12} /> Assistir aulas ({lessonSummary.essential_completed}/
                {lessonSummary.essential_total}
                {lessonSummary.remaining_duration_seconds
                  ? ` • ${formatRemainingSeconds(lessonSummary.remaining_duration_seconds)}`
                  : ""}
                )
              </Link>
            ) : lessonSummary && lessonSummary.total > 0 ? (
              <Link
                href={
                  lessonSummary.next_lesson_id
                    ? `/aulas?subtema=${encodeURIComponent(t.subtema)}&lesson=${lessonSummary.next_lesson_id}`
                    : `/aulas?subtema=${encodeURIComponent(t.subtema)}`
                }
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-elevated hover:bg-elevated/80 text-ink-secondary hover:text-ink-primary text-xs font-medium rounded-md transition-colors border border-line-subtle"
              >
                <PlayCircle size={12} /> Aulas extras ({lessonSummary.total})
              </Link>
            ) : null}
            {lessonSummary?.cycle?.pre_done && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-success/10 text-success border border-success/25">
                <Check size={11} /> Pré {lessonSummary.cycle.pre_completed > 0 ? `${lessonSummary.cycle.pre_completed}q` : "✓"}
              </span>
            )}
            {lessonSummary?.theory_completed ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-success/10 text-success border border-success/25">
                <Check size={11} /> Teoria ✓
              </span>
            ) : lessonSummary?.essential_all_completed ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-primary/10 text-primary border border-primary/25">
                <Check size={11} /> Aulas ✓
              </span>
            ) : null}
            {lessonSummary?.cycle?.post_done && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-success/10 text-success border border-success/25">
                <Check size={11} /> Pós {lessonSummary.cycle.post_completed > 0 ? `${lessonSummary.cycle.post_completed}q` : "✓"}
              </span>
            )}
            {onOpenMoveModalTopic && (
              <button
                type="button"
                onClick={() => onOpenMoveModalTopic(t.subtema, week)}
                className="inline-flex items-center gap-1 px-2.5 py-1 bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground text-xs font-medium rounded-md transition-colors border border-line-subtle"
                title="Mover este tema para outra semana"
              >
                <ArrowUpDown size={12} className="text-accent" />
                Mover semana
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
TopicRow.displayName = "TopicRow";

interface PlannerWeekCardProps {
  week: PlannerWeek;
  weekProgress: PlannerWeekProgress;
  topicProgress: PlannerTopicProgressMap;
  todayTimestamp: number;
  organizationMode: PlannerOrganizationMode;
  draggedTopic: { week: number; subtema: string; index: number } | null;
  dragOverWeek: number | null;
  dragOverTopicIndex: { week: number; index: number } | null;
  loadingAction: string | null;
  canAccessLessons: boolean;
  lessonsSummaryBySubtema?: Record<string, LessonsSummaryBySubtemaItem>;
  toggleTopic: (week: number, subtema: string, completed: boolean) => void;
  handleToggleStudy: (week: number, currentStudied: boolean) => void;
  handleWeekDragOver: (e: React.DragEvent, weekNumber: number) => void;
  handleWeekDrop: (e: React.DragEvent, targetWeek: number) => void;
  handleDragStart: (week: number, subtema: string, index: number, e: React.DragEvent) => void;
  handleDragEnd: () => void;
  handleTopicDragOver: (week: number, index: number, e: React.DragEvent) => void;
  handleTopicDrop: (week: number, index: number, e: React.DragEvent) => void;
  handleOpenMoveModalTopic: (subtema: string, currentWeek: number) => void;
}

export const PlannerWeekCard = memo(function PlannerWeekCard({
  week,
  weekProgress,
  topicProgress,
  todayTimestamp,
  organizationMode,
  draggedTopic,
  dragOverWeek,
  dragOverTopicIndex,
  loadingAction,
  canAccessLessons,
  lessonsSummaryBySubtema,
  toggleTopic,
  handleToggleStudy,
  handleWeekDragOver,
  handleWeekDrop,
  handleDragStart,
  handleDragEnd,
  handleTopicDragOver,
  handleTopicDrop,
  handleOpenMoveModalTopic,
}: PlannerWeekCardProps) {
  const completedInWeek = week.topics.filter(
    (topic) => topicProgress[`${week.week}:${topic.subtema}`] || topicProgress[topic.subtema]
  ).length;
  const weekDate = new Date(`${week.date.slice(0, 10)}T12:00:00`);
  const weekTime = weekDate.getTime();
  const isCurrentWeek = weekTime <= todayTimestamp && weekTime + 7 * 24 * 60 * 60 * 1000 > todayTimestamp;
  const isOverloaded = week.allocated_hours > week.recommended_hours + 1.0;
  const isOverDropWeek = dragOverWeek === week.week;

  return (
    <div
      onDragOver={(e) => handleWeekDragOver(e, week.week)}
      onDrop={(e) => handleWeekDrop(e, week.week)}
      className={clsx(
        "bg-surface border rounded-xl overflow-hidden shadow-1 flex flex-col md:flex-row transition-all",
        isOverDropWeek
          ? "border-primary ring-2 ring-primary/40 bg-primary/[0.02]"
          : isCurrentWeek
          ? "border-primary ring-1 ring-primary/20"
          : "border-line-subtle",
        weekProgress.studied ? "opacity-75" : "opacity-100"
      )}
    >
      <div className="p-5 flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-bold text-ink-secondary bg-elevated px-2.5 py-1 rounded-md">
              Semana {week.week}
            </span>
            {organizationMode === "internato" && week.internato_block_label && (
              <span className="text-xs font-semibold text-primary bg-primary/10 border border-primary/20 px-2.5 py-0.5 rounded-full">
                {week.internato_block_label}
              </span>
            )}
            <span className="text-sm text-ink-secondary flex items-center gap-2">
              {weekDate.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
              <span
                className={clsx(
                  "text-xs px-2 py-0.5 rounded-full font-medium transition-colors",
                  isOverloaded
                    ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 font-semibold"
                    : "bg-elevated text-ink-secondary"
                )}
              >
                {week.allocated_hours}h / {week.recommended_hours}h
              </span>
            </span>
            {isCurrentWeek && (
              <span className="text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                <Activity size={12} /> Atual
              </span>
            )}
            <span className="text-xs text-ink-muted">
              {completedInWeek}/{week.topics.length} temas
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-3 min-h-[40px]">
          {week.topics.map((t, idx) => (
            <TopicRow
              key={t.subtema}
              t={t}
              completed={Boolean(topicProgress[`${week.week}:${t.subtema}`]) || Boolean(topicProgress[t.subtema])}
              toggleTopic={toggleTopic}
              week={week.week}
              index={idx}
              isDragging={draggedTopic?.subtema === t.subtema}
              isDragOverBefore={
                dragOverTopicIndex?.week === week.week &&
                dragOverTopicIndex?.index === idx &&
                draggedTopic?.subtema !== t.subtema
              }
              onDragStartTopic={handleDragStart}
              onDragEnd={handleDragEnd}
              onDragOverTopic={handleTopicDragOver}
              onDropTopic={handleTopicDrop}
              onOpenMoveModalTopic={handleOpenMoveModalTopic}
              lessonSummary={canAccessLessons ? lessonsSummaryBySubtema?.[t.subtema] : undefined}
            />
          ))}
          {week.topics.length === 0 && (
            <div
              onDragOver={(e) => handleWeekDragOver(e, week.week)}
              onDrop={(e) => handleWeekDrop(e, week.week)}
              className={clsx(
                "py-7 px-4 border-2 border-dashed rounded-xl text-center transition-all flex flex-col items-center justify-center gap-1.5",
                isOverDropWeek
                  ? "border-primary bg-primary/10 text-primary scale-[1.01]"
                  : "border-line-subtle text-ink-muted bg-elevated/10 hover:border-primary/40"
              )}
            >
              <CalendarDays size={20} className="opacity-60" />
              <span className="text-xs font-semibold">Semana sem matérias (descanso ou revisão)</span>
              <span className="text-[11px] opacity-75">Arraste temas para cá para agendar nesta semana.</span>
            </div>
          )}
        </div>
      </div>

      <div className="bg-canvas/60 p-5 border-t md:border-t-0 md:border-l border-line-subtle md:w-72 shrink-0 flex flex-col justify-center">
        <h3 className="text-sm font-semibold text-ink-primary mb-2 uppercase tracking-wider">Status da semana</h3>
        <p className="text-xs text-ink-muted mb-4">As revisões espaçadas de questões são gerenciadas pelo FSRS.</p>
        <div className="flex flex-col gap-3">
          <label
            className={clsx(
              "flex items-center gap-3 p-2.5 min-h-[38px] rounded-lg cursor-pointer transition-colors border",
              weekProgress.studied ? "bg-primary/10 border-primary/20" : "bg-surface border-line-subtle hover:bg-elevated"
            )}
          >
            <div className="relative flex items-center">
              <input
                type="checkbox"
                className="peer sr-only"
                checked={weekProgress.studied}
                onChange={() => handleToggleStudy(week.week, weekProgress.studied)}
                disabled={loadingAction === `study-${week.week}`}
                aria-label={`Concluir semana ${week.week}`}
              />
              <div className="w-5 h-5 border-2 border-ink-muted rounded transition-colors peer-checked:bg-primary peer-checked:border-primary flex items-center justify-center">
                {loadingAction === `study-${week.week}` ? (
                  <Loader2 size={12} className="text-primary-foreground animate-spin" />
                ) : (
                  <Check
                    size={14}
                    className={clsx("text-primary-foreground transition-opacity", weekProgress.studied ? "opacity-100" : "opacity-0")}
                    strokeWidth={3}
                  />
                )}
              </div>
            </div>
            <span className={clsx("text-sm font-medium select-none", weekProgress.studied ? "text-primary" : "text-ink-primary")}>
              Fechar semana
            </span>
          </label>
        </div>
      </div>
    </div>
  );
});
PlannerWeekCard.displayName = "PlannerWeekCard";
