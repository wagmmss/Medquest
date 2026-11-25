"use client";

import React from "react";
import { CheckCircle2 } from "lucide-react";

interface FinishSessionModalProps {
  isOpen: boolean;
  completedCount: number;
  totalCount: number;
  onClose: () => void;
  onConfirm: () => void;
}

export function FinishSessionModal({
  isOpen,
  completedCount,
  totalCount,
  onClose,
  onConfirm,
}: FinishSessionModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="finish-modal-title"
    >
      <div
        className="bg-surface border border-line-subtle shadow-2xl rounded-lg p-6 max-w-md w-full flex flex-col gap-4 animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-accent/10 border border-accent/25 text-accent flex items-center justify-center shrink-0">
            <CheckCircle2 size={18} />
          </div>
          <div>
            <h3 id="finish-modal-title" className="text-base font-bold text-ink-primary">
              Finalizar Sessão de Estudos?
            </h3>
            <p className="text-xs text-ink-secondary">Você pode encerrar a sessão a qualquer momento.</p>
          </div>
        </div>

        <div className="bg-elevated/40 rounded-md p-3.5 border border-line-subtle text-xs sm:text-sm text-ink-primary leading-relaxed">
          Você respondeu <strong className="font-mono-lab tabular-nums">{completedCount}</strong> de{" "}
          <strong className="font-mono-lab tabular-nums">{totalCount}</strong> questões. Restam{" "}
          <span className="font-mono-lab tabular-nums">{totalCount - completedCount}</span> não respondidas.
          <p className="mt-2 text-xs text-ink-secondary">
            Todas as questões já respondidas terão suas revisões (FSRS) preservadas. Ao finalizar, você verá
            seu relatório de acertos e o diagnóstico da sessão.
          </p>
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-md text-xs font-semibold text-ink-secondary hover:text-ink-primary hover:bg-elevated transition-colors cursor-pointer"
          >
            Continuar Respondendo
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 rounded-md text-xs font-semibold bg-accent hover:bg-accent/90 text-white shadow-2xs transition-colors cursor-pointer flex items-center gap-1.5"
          >
            <CheckCircle2 size={15} />
            Sim, Finalizar
          </button>
        </div>
      </div>
    </div>
  );
}
