"use client";

import React from "react";
import dynamic from "next/dynamic";
import {
  ArrowRight,
  ArrowUpDown,
  CalendarDays,
  Check,
  Copy,
  Download,
  Lightbulb,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { PlannerConfig, PlannerWeek } from "@/types/api";
import { InternatoBlocksModal } from "../InternatoBlocksModal";

const PlannerWizard = dynamic(
  () => import("../PlannerWizard").then((m) => m.PlannerWizard),
  {
    loading: () => (
      <div className="h-80 w-full max-w-3xl mx-auto rounded-xl bg-surface border border-line-subtle animate-pulse" />
    ),
  }
);

interface PlannerModalsProps {
  config?: PlannerConfig | null;
  currentPlan: PlannerWeek[];
  defaultWeeklyHours: number;
  showResetConfirm: boolean;
  showInternatoModal: boolean;
  showSettingsModal: boolean;
  showCalendarModal: boolean;
  moveModalTopic: { subtema: string; currentWeek: number; targetWeek: number } | null;
  exportingIcs: boolean;
  copiedFeed: boolean;
  isMoving: boolean;
  onCloseResetConfirm: () => void;
  onResetScope: (scope: "schedule" | "progress" | "all") => Promise<void>;
  onCloseInternatoModal: () => void;
  onSavedInternato: () => void;
  onCloseSettingsModal: () => void;
  onCloseCalendarModal: () => void;
  onExportIcs: () => void;
  onCopyFeedUrl: () => void;
  onChangeMoveTargetWeek: (week: number) => void;
  onCloseMoveModal: () => void;
  onConfirmMoveTopic: (subtema: string, currentWeek: number, targetWeek: number) => Promise<void>;
}

export function PlannerModals({
  config,
  currentPlan,
  defaultWeeklyHours,
  showResetConfirm,
  showInternatoModal,
  showSettingsModal,
  showCalendarModal,
  moveModalTopic,
  exportingIcs,
  copiedFeed,
  isMoving,
  onCloseResetConfirm,
  onResetScope,
  onCloseInternatoModal,
  onSavedInternato,
  onCloseSettingsModal,
  onCloseCalendarModal,
  onExportIcs,
  onCopyFeedUrl,
  onChangeMoveTargetWeek,
  onCloseMoveModal,
  onConfirmMoveTopic,
}: PlannerModalsProps) {
  return (
    <>
      {showResetConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onCloseResetConfirm} />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-modal-title"
            className="relative bg-surface border border-line-subtle rounded-2xl shadow-2xl p-6 max-w-md w-full mx-4 animate-in fade-in zoom-in-95 duration-200 z-10"
          >
            <button
              type="button"
              onClick={onCloseResetConfirm}
              aria-label="Fechar modal de confirmação"
              className="absolute top-3.5 right-3.5 p-1.5 min-w-[38px] min-h-[38px] flex items-center justify-center rounded-full hover:bg-elevated transition-colors text-ink-muted cursor-pointer"
            >
              <X size={18} />
            </button>
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-amber-500/10 rounded-full shrink-0">
                  <RotateCcw size={22} className="text-amber-500" />
                </div>
                <div>
                  <h3 id="reset-modal-title" className="text-lg font-bold text-ink-primary">
                    Refazer ou Resetar Planner
                  </h3>
                  <p className="text-xs text-ink-secondary">Escolha o que deseja reiniciar:</p>
                </div>
              </div>

              <div className="flex flex-col gap-2.5">
                <button
                  type="button"
                  onClick={() => void onResetScope("schedule")}
                  className="w-full text-left p-3.5 rounded-xl border border-line-subtle bg-elevated/60 hover:bg-elevated hover:border-primary/40 transition-colors cursor-pointer"
                >
                  <p className="text-sm font-bold text-ink-primary">Reorganizar cronograma atual</p>
                  <p className="text-xs text-ink-secondary mt-0.5">
                    Recalcula a distribuição das semanas mantendo todas as aulas já marcadas como feitas.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => void onResetScope("progress")}
                  className="w-full text-left p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 transition-colors cursor-pointer"
                >
                  <p className="text-sm font-bold text-amber-600 dark:text-amber-400">Zerar aulas concluídas</p>
                  <p className="text-xs text-ink-secondary mt-0.5">
                    Desmarca todas as aulas feitas e revisões, mantendo suas datas, horas e blocos do internato.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => void onResetScope("all")}
                  className="w-full text-left p-3.5 rounded-xl border border-destructive/30 bg-destructive/5 hover:bg-destructive/10 transition-colors cursor-pointer"
                >
                  <p className="text-sm font-bold text-destructive">Reset completo</p>
                  <p className="text-xs text-ink-secondary mt-0.5">
                    Apaga configurações, blocos e todo o progresso para recomeçar do zero.
                  </p>
                </button>
              </div>

              <button
                type="button"
                onClick={onCloseResetConfirm}
                className="w-full py-2.5 px-4 min-h-[38px] rounded-xl border border-line-subtle text-ink-primary hover:bg-elevated transition-colors font-medium text-sm cursor-pointer"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {showInternatoModal && (
        <InternatoBlocksModal
          initialBlocks={config?.internato_blocks || []}
          defaultWeeklyHours={defaultWeeklyHours}
          onClose={onCloseInternatoModal}
          onSaved={onSavedInternato}
        />
      )}

      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onCloseSettingsModal} />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Calibrar Perfil de Estudos"
            className="relative z-10 max-h-[90dvh] overflow-y-auto w-full max-w-2xl animate-in fade-in zoom-in-95 duration-200"
          >
            <PlannerWizard initialConfig={config} onClose={onCloseSettingsModal} isModal />
          </div>
        </div>
      )}

      {showCalendarModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onCloseCalendarModal} />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="calendar-modal-title"
            className="relative bg-surface border border-line-subtle rounded-lg shadow-2xl p-6 max-w-lg w-full max-h-[90dvh] overflow-y-auto z-10"
          >
            <button
              type="button"
              onClick={onCloseCalendarModal}
              aria-label="Fechar modal de exportação"
              className="absolute top-3.5 right-3.5 p-1.5 min-w-[38px] min-h-[38px] flex items-center justify-center rounded-md hover:bg-elevated transition-colors text-ink-muted cursor-pointer"
            >
              <X size={18} />
            </button>

            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 bg-accent/15 text-accent rounded-md flex items-center justify-center border border-accent/20 shrink-0">
                <CalendarDays size={20} />
              </div>
              <div>
                <h3 id="calendar-modal-title" className="text-lg font-bold text-ink-primary">
                  Exportar Cronograma (.ics)
                </h3>
                <p className="text-xs text-ink-secondary">Compatível com Google Agenda, Apple Calendar e Outlook.</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="border border-line-subtle bg-canvas rounded-lg p-4 space-y-3">
                <p className="text-xs text-ink-secondary leading-relaxed">
                  Baixe o arquivo padrão <strong className="text-ink-primary">.ics</strong> com todos os blocos semanais
                  de estudo e importe diretamente no aplicativo de agenda da sua preferência.
                </p>

                <button
                  type="button"
                  onClick={onExportIcs}
                  disabled={exportingIcs}
                  className="w-full bg-accent hover:bg-accent/90 text-white font-semibold py-2.5 px-4 min-h-[38px] rounded-md transition-colors flex items-center justify-center gap-2 text-xs disabled:opacity-50 cursor-pointer"
                >
                  {exportingIcs ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  {exportingIcs ? "Gerando arquivo .ics..." : "Baixar Arquivo .ics do Cronograma"}
                </button>
              </div>

              <div className="border border-line-subtle bg-canvas rounded-lg p-4 space-y-2.5">
                <div className="text-xs font-bold text-ink-primary">Assinatura Automática (Feed iCalendar)</div>
                <p className="text-[11px] text-ink-secondary leading-relaxed">
                  Copie a URL do feed para assinar seu cronograma por link no Apple Calendar, Outlook ou Google Agenda.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    aria-label="URL do feed iCalendar"
                    value={api.planner.getCalendarFeedUrl()}
                    className="flex-1 bg-surface border border-line-subtle rounded-md px-2.5 py-1.5 text-[11px] font-mono-lab text-ink-muted focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={onCopyFeedUrl}
                    className="px-3 py-1.5 min-h-[36px] rounded-md border border-line-subtle bg-surface hover:bg-elevated text-xs font-semibold text-ink-primary inline-flex items-center gap-1.5 cursor-pointer shrink-0"
                  >
                    {copiedFeed ? <Check size={13} className="text-success" /> : <Copy size={13} />}
                    {copiedFeed ? "Copiado" : "Copiar"}
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-4 text-[11px] text-ink-secondary flex items-start gap-2 bg-canvas p-3 rounded-md border border-line-subtle">
              <Lightbulb size={14} className="text-accent shrink-0 mt-0.5" />
              <span>
                Após importar o arquivo <strong>.ics</strong> na sua agenda, os eventos passam a ser 100% editáveis no seu calendário pessoal.
              </span>
            </div>
          </div>
        </div>
      )}

      {moveModalTopic && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onCloseMoveModal} />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="move-modal-title"
            className="relative bg-surface border border-line-subtle rounded-2xl shadow-2xl p-6 max-w-sm w-full z-10 animate-in fade-in zoom-in-95 duration-200"
          >
            <button
              type="button"
              onClick={onCloseMoveModal}
              aria-label="Fechar"
              className="absolute top-3.5 right-3.5 p-1.5 min-w-[38px] min-h-[38px] flex items-center justify-center rounded-full hover:bg-elevated transition-colors text-ink-muted cursor-pointer"
            >
              <X size={18} />
            </button>
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-primary/10 text-primary rounded-xl flex items-center justify-center border border-primary/20 shrink-0">
                  <ArrowUpDown size={20} />
                </div>
                <div>
                  <h3 id="move-modal-title" className="text-base font-bold text-ink-primary">
                    Mover Tema
                  </h3>
                  <p className="text-xs text-ink-secondary">Escolha a semana de destino</p>
                </div>
              </div>

              <div className="bg-elevated/40 border border-line-subtle rounded-xl p-3">
                <span className="text-xs font-semibold text-ink-primary block truncate" title={moveModalTopic.subtema}>
                  {moveModalTopic.subtema}
                </span>
                <span className="text-[11px] text-ink-secondary mt-0.5 block">
                  Semana atual: <strong className="text-ink-primary">Semana {moveModalTopic.currentWeek}</strong>
                </span>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="target-week-select" className="text-xs font-semibold text-ink-primary">
                  Mover para:
                </label>
                <select
                  id="target-week-select"
                  value={moveModalTopic.targetWeek}
                  onChange={(e) => onChangeMoveTargetWeek(Number(e.target.value))}
                  className="w-full bg-canvas border border-line-subtle rounded-xl px-3 py-2.5 text-xs text-ink-primary focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
                >
                  {currentPlan.map((w) => {
                    const wDate = new Date(`${w.date.slice(0, 10)}T12:00:00`);
                    return (
                      <option key={w.week} value={w.week}>
                        Semana {w.week} ({wDate.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}) •{" "}
                        {w.topics.length} temas ({w.allocated_hours}h/{w.recommended_hours}h)
                      </option>
                    );
                  })}
                </select>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={onCloseMoveModal}
                  className="flex-1 py-2 px-3 min-h-[38px] rounded-xl border border-line-subtle text-ink-primary hover:bg-elevated text-xs font-medium transition-colors cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  disabled={isMoving}
                  onClick={() => {
                    const { subtema, currentWeek, targetWeek } = moveModalTopic;
                    onCloseMoveModal();
                    void onConfirmMoveTopic(subtema, currentWeek, targetWeek);
                  }}
                  className="flex-1 py-2 px-3 min-h-[38px] rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-colors flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {isMoving ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={13} />}
                  Confirmar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
