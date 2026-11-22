"use client";

import React, { useRef } from "react";
import { Eraser, Highlighter } from "lucide-react";
import { FormattedContent } from "@/components/FormattedContent";
import type { HighlightColor } from "@/types/api";
import { getSelectionOffsetsWithin, type TextHighlight } from "@/lib/textHighlights";

const COLOR_DOTS: Array<{ color: HighlightColor; label: string; className: string }> = [
  { color: "yellow", label: "Amarelo", className: "bg-amber-300 border-amber-500" },
  { color: "green", label: "Verde", className: "bg-emerald-300 border-emerald-500" },
  { color: "blue", label: "Azul", className: "bg-sky-300 border-sky-500" },
  { color: "pink", label: "Rosa", className: "bg-rose-300 border-rose-500" },
];

interface HighlightableContentProps {
  content: string;
  className?: string;
  onImageClick?: (url: string) => void;
  highlights: TextHighlight[];
  activeColor: HighlightColor;
  enabled?: boolean;
  onAddHighlight: (range: { start: number; end: number; color: HighlightColor }) => void;
  onRemoveHighlight: (id: string) => void;
}

export function HighlightableContent({
  content,
  className = "",
  onImageClick,
  highlights,
  activeColor,
  enabled = true,
  onAddHighlight,
  onRemoveHighlight,
}: HighlightableContentProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const handleSelectionEnd = () => {
    if (!enabled || !containerRef.current) return;
    const selection = window.getSelection();
    const offsets = getSelectionOffsetsWithin(containerRef.current, selection);
    if (!offsets) return;

    onAddHighlight({
      start: offsets.start,
      end: offsets.end,
      color: activeColor,
    });
    selection?.removeAllRanges();
  };

  return (
    <div
      ref={containerRef}
      onMouseUp={handleSelectionEnd}
      onTouchEnd={handleSelectionEnd}
      className={enabled ? "cursor-text" : undefined}
    >
      <FormattedContent
        content={content}
        className={className}
        onImageClick={onImageClick}
        highlights={highlights}
        onRemoveHighlight={onRemoveHighlight}
      />
    </div>
  );
}

interface HighlightToolbarProps {
  activeColor: HighlightColor;
  onChangeColor: (color: HighlightColor) => void;
  enabled: boolean;
  onToggleEnabled: () => void;
  highlightCount: number;
  onClearAll: () => void;
}

export function HighlightToolbar({
  activeColor,
  onChangeColor,
  enabled,
  onToggleEnabled,
  highlightCount,
  onClearAll,
}: HighlightToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
      <button
        type="button"
        onClick={onToggleEnabled}
        title={
          enabled
            ? "Marca-texto automático ativo: selecione qualquer trecho para grifar e clique no grifo para remover"
            : "Ativar marca-texto automático ao selecionar"
        }
        aria-pressed={enabled}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-xs border transition-colors cursor-pointer font-medium ${
          enabled
            ? "bg-amber-500/12 border-amber-500/35 text-amber-800 dark:text-amber-300"
            : "bg-canvas border-line-subtle text-ink-muted hover:text-ink"
        }`}
      >
        <Highlighter className="w-3 h-3" aria-hidden="true" />
        <span>Marca-texto</span>
      </button>

      {enabled && (
        <div className="flex items-center gap-1 px-1" role="group" aria-label="Cor do marca-texto">
          {COLOR_DOTS.map((dot) => (
            <button
              key={dot.color}
              type="button"
              onClick={() => onChangeColor(dot.color)}
              title={`Cor ${dot.label}`}
              aria-label={`Cor de grifo ${dot.label}`}
              aria-pressed={activeColor === dot.color}
              className={`w-3.5 h-3.5 rounded-full border cursor-pointer transition-transform ${dot.className} ${
                activeColor === dot.color ? "scale-120 ring-1 ring-ink-primary" : "opacity-65 hover:opacity-100"
              }`}
            />
          ))}
        </div>
      )}

      {highlightCount > 0 && (
        <button
          type="button"
          onClick={onClearAll}
          title="Remover todos os grifos desta questão"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-xs border border-line-subtle bg-canvas hover:bg-elevated text-ink-muted hover:text-ink transition-colors cursor-pointer"
        >
          <Eraser className="w-3 h-3" aria-hidden="true" />
          <span>Limpar ({highlightCount})</span>
        </button>
      )}
    </div>
  );
}
