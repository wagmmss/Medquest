"use client";

import clsx from "clsx";
import { CheckCircle2 } from "lucide-react";
import type { LessonItem } from "@/types/api";
import {
  formatDuration,
  formatSecondsToMmSs,
  formatSize,
  kindBadge,
} from "../lessonHelpers";

export function LessonRowCompact({
  item,
  isActive,
  savingProgress,
  onSelect,
  onToggleComplete,
  showKindBadge = true,
}: {
  item: LessonItem;
  isActive?: boolean;
  savingProgress: boolean;
  onSelect: (lesson: LessonItem) => void;
  onToggleComplete: (lesson: LessonItem) => void;
  showKindBadge?: boolean;
}) {
  const isDone = item.progress.status === "completed";
  const isInProg = item.progress.status === "in_progress";
  const badge = showKindBadge ? kindBadge(item.lesson_kind) : null;
  const durLabel = formatDuration(item.duration_seconds);

  return (
    <div
      className={clsx(
        "flex items-start gap-2.5 px-3 py-2 rounded-sm transition-colors border",
        isActive
          ? "bg-accent/10 border-accent/40"
          : "bg-surface/70 border-transparent hover:bg-elevated/60 hover:border-line-subtle"
      )}
    >
      <button
        type="button"
        title={isDone ? "Desmarcar conclusão" : "Marcar aula concluída"}
        aria-label={isDone ? `Desmarcar conclusão de ${item.title}` : `Marcar ${item.title} como concluída`}
        disabled={savingProgress}
        onClick={() => onToggleComplete(item)}
        className={clsx(
          "mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center shrink-0 cursor-pointer transition-colors",
          isDone
            ? "bg-success border-success text-white"
            : isInProg
            ? "border-warning text-warning"
            : "border-line-subtle hover:border-accent"
        )}
      >
        {isDone && <CheckCircle2 className="w-3 h-3" />}
      </button>

      <button
        type="button"
        onClick={() => onSelect(item)}
        className="flex-1 min-w-0 text-left cursor-pointer group"
      >
        <div className="flex items-start justify-between gap-2">
          <p
            className={clsx(
              "text-xs leading-snug break-words transition-colors",
              isActive
                ? "font-semibold text-accent"
                : isDone
                ? "text-ink-muted line-through"
                : "text-ink-primary font-medium group-hover:text-primary"
            )}
          >
            {item.title}
          </p>
          {durLabel ? (
            <span className="text-[11px] font-mono-lab text-ink-muted shrink-0 tabular-nums">
              {durLabel}
            </span>
          ) : item.size_bytes && item.size_bytes > 0 ? (
            <span className="text-[11px] font-mono-lab text-ink-muted shrink-0">
              {formatSize(item.size_bytes)}
            </span>
          ) : null}
        </div>
        {(badge || item.progress.bookmark_seconds > 0 || item.progress.has_notes) && (
          <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px] text-ink-muted">
            {badge && (
              <span
                className={clsx(
                  "px-1.5 py-0.2 rounded-xs border",
                  badge.tone === "accent"
                    ? "bg-accent/10 text-accent border-accent/25"
                    : badge.tone === "primary"
                    ? "bg-primary/10 text-primary border-primary/25"
                    : "bg-elevated border-line-subtle text-ink-secondary"
                )}
              >
                {badge.label}
              </span>
            )}
            {item.progress.bookmark_seconds > 0 && (
              <span className="font-mono-lab text-warning">
                ⏱ {formatSecondsToMmSs(item.progress.bookmark_seconds)}
              </span>
            )}
            {item.progress.has_notes && (
              <span className="text-ink-secondary">• com notas</span>
            )}
          </div>
        )}
      </button>
    </div>
  );
}
