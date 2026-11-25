"use client";

import React from "react";
import { ClinicalIcon } from "@/components/ui/ClinicalIcon";

interface DiscursiveAnswerBoxProps {
  value: string;
  readOnly: boolean;
  submitting: boolean;
  hasPendingSubmit: boolean;
  onChange: (val: string) => void;
  onSubmit: () => void;
}

export function DiscursiveAnswerBox({
  value,
  readOnly,
  submitting,
  hasPendingSubmit,
  onChange,
  onSubmit,
}: DiscursiveAnswerBoxProps) {
  return (
    <div className="bg-surface border border-line-subtle shadow-xs rounded-sm p-5 md:p-6 flex flex-col gap-3.5 animate-in fade-in duration-200">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-accent font-bold text-sm">
          <ClinicalIcon name="notes" size={16} />
          <span>Questão Discursiva (Resposta Aberta)</span>
        </div>
        <span className="text-[11px] font-mono-lab text-ink-muted">
          Atalho: <kbd className="bg-canvas px-1 py-0.5 rounded-xs border border-line-subtle text-[10px] text-ink">Ctrl+Enter</kbd>
        </span>
      </div>
      <p className="text-xs text-ink-muted leading-relaxed">
        Anote seus achados clínicos, hipótese diagnóstica ou conduta antes de revelar o gabarito e padrão oficial da banca:
      </p>
      <textarea
        value={value}
        readOnly={readOnly}
        onChange={(e) => {
          if (readOnly) return;
          onChange(e.target.value);
        }}
        placeholder="Escreva sua hipótese diagnóstica ou conduta aqui..."
        rows={4}
        className="w-full bg-canvas border border-line-subtle focus:border-accent focus:bg-surface rounded-sm p-3.5 text-ink placeholder:text-ink-muted/60 focus:outline-none focus:ring-1 focus:ring-accent transition-all resize-y text-sm font-normal leading-relaxed min-h-[100px]"
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            onSubmit();
          }
        }}
      />
      <button
        onClick={onSubmit}
        disabled={submitting}
        className="w-full bg-accent hover:opacity-90 text-white font-bold py-3 rounded-sm transition-opacity flex items-center justify-center gap-2 shadow-xs cursor-pointer text-xs uppercase tracking-wider font-mono-lab disabled:opacity-50"
      >
        {submitting ? (
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <>
            <ClinicalIcon name="checkCircle" size={14} />
            {hasPendingSubmit ? "Tentar de novo" : "Confirmar Resposta & Ver Padrão da Banca"}
          </>
        )}
      </button>
    </div>
  );
}
