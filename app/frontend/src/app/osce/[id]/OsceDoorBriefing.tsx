"use client";

import React from "react";
import Link from "next/link";
import { CheckCircle2, Clock, Eye, Lock, ShieldCheck, Sparkles, Stethoscope } from "lucide-react";
import { OsceStationDetail, OsceTaskProgress } from "@/types/api";

interface OsceDoorBriefingProps {
  station: OsceStationDetail;
  circuitId?: string;
  step: number;
  selectedMode: "blind" | "guided";
  neutralStationLabel: string;
  taskProgress: OsceTaskProgress;
  isLoading: boolean;
  onSelectMode: (mode: "blind" | "guided") => void;
  onStartExam: () => void;
}

export function OsceDoorBriefing({
  station,
  circuitId,
  step,
  selectedMode,
  neutralStationLabel,
  taskProgress,
  isLoading,
  onSelectMode,
  onStartExam,
}: OsceDoorBriefingProps) {
  return (
    <div className="flex-1 flex flex-col items-center p-2 sm:p-4 max-w-3xl mx-auto text-center space-y-6 w-full pb-32 animate-in fade-in zoom-in-95 duration-200">
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
        <Stethoscope className="w-4 h-4" />
        <span>Porta da Estação • {station.institution}</span>
        {circuitId && <span className="ml-2 text-amber-500 font-extrabold">• Circuito: Estação {step} de 5</span>}
      </div>

      <h1 className="text-3xl md:text-4xl font-black text-foreground">
        {selectedMode === "blind" ? neutralStationLabel : station.title}
      </h1>

      <div className="flex items-center justify-center gap-4 text-xs md:text-sm text-muted-foreground font-semibold">
        <span>{station.area}</span>
        {selectedMode !== "blind" && (
          <>
            <span>•</span>
            <span>{station.subtema}</span>
          </>
        )}
        <span>•</span>
        <span className="flex items-center gap-1 text-primary">
          <Clock className="w-4 h-4" />
          {Math.round(station.duration_seconds / 60)} minutos
        </span>
      </div>

      <div className="w-full text-left rounded-lg border border-line-subtle bg-surface p-6 md:p-8 space-y-4">
        <div className="text-xs font-bold uppercase text-muted-foreground tracking-wider pb-2 border-b border-line-subtle">
          Instruções Fixadas na Porta da Sala
        </div>
        <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-line text-sm text-foreground/90">
          {station.scenario_door_markdown}
        </div>
      </div>

      {taskProgress.visible_tasks.length > 0 && (
        <div className="w-full text-left rounded-lg border border-line-subtle bg-surface p-4 md:p-5 space-y-2.5">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <span>Tarefas Sequenciais da Estação</span>
            <span className="text-[11px] font-mono text-primary">
              Liberação progressiva na sala
            </span>
          </div>
          <div className="space-y-2">
            {taskProgress.visible_tasks.map((t) => (
              <div
                key={t.id}
                className={`flex items-start gap-2.5 p-2.5 rounded-lg border text-xs ${
                  t.locked
                    ? "border-border/60 bg-muted/40 text-muted-foreground"
                    : "border-primary/30 bg-primary/5 text-foreground"
                }`}
              >
                {t.locked ? (
                  <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0 text-primary" />
                )}
                <div>
                  <span className="font-mono font-bold mr-1.5">Tarefa {t.step}:</span>
                  <span>
                    {t.locked
                      ? `Bloqueada — declare a Tarefa ${t.step - 1} concluída para liberar`
                      : t.description}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="w-full text-left rounded-lg border border-line-subtle bg-surface p-4 md:p-6 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Escolha o Modo de Simulação
          </span>
          <span className="text-[11px] text-muted-foreground font-medium hidden sm:inline">
            Pode alternar livremente a qualquer momento
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => onSelectMode("guided")}
            className={`p-4 rounded-lg border text-left transition-colors relative flex flex-col justify-between ${
              selectedMode === "guided"
                ? "border-accent bg-accent/10"
                : "border-line-subtle bg-canvas hover:bg-muted/50"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-accent" />
                <div>
                  <div className="font-bold text-sm text-foreground flex items-center gap-1.5">
                    Treinamento Guiado
                  </div>
                  <div className="text-[10px] font-bold text-accent uppercase">
                    Preceptor Fantasma Ativo
                  </div>
                </div>
              </div>
              {selectedMode === "guided" && (
                <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
              )}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Barema dinâmico com pontuação ao vivo. O Preceptor alerta sobre tempos críticos, dosagem de eletrólitos e condutas essenciais antes do fim do tempo.
            </p>
            <div className="mt-3 flex items-center gap-1.5 text-[10px] font-bold text-primary">
              <Sparkles className="w-3 h-3" />
              <span>Recomendado para aprendizado e fixação</span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelectMode("blind")}
            className={`p-4 rounded-xl border-2 text-left transition-all relative flex flex-col justify-between ${
              selectedMode === "blind"
                ? "border-primary bg-primary/10 shadow-sm ring-2 ring-primary/20"
                : "border-border bg-background hover:bg-muted/50"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Eye className="w-5 h-5 text-muted-foreground" />
                <div>
                  <div className="font-bold text-sm text-foreground flex items-center gap-1.5">
                    Prova Cega (Padrão)
                  </div>
                  <div className="text-[10px] font-bold text-muted-foreground uppercase">
                    Sem spoilers de tema ou barema
                  </div>
                </div>
              </div>
              {selectedMode === "blind" && (
                <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
              )}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Experiência realística de 2ª fase sem nenhuma pista visual. Cronômetro puro e barema 100% oculto até a finalização da conduta.
            </p>
            <div className="mt-3 flex items-center gap-1.5 text-[10px] font-bold text-muted-foreground">
              <ShieldCheck className="w-3 h-3" />
              <span>Simulação de alta pressão real</span>
            </div>
          </button>
        </div>
      </div>

      <div className="sticky bottom-4 z-20 flex items-center justify-center gap-4 pt-4 pb-2 w-full max-w-xl mx-auto bg-background/90 backdrop-blur-md p-3 rounded-2xl border border-border shadow-xl">
        <Link
          href="/osce"
          className="px-5 py-3 rounded-xl border border-border bg-card hover:bg-muted text-sm font-semibold transition-colors shrink-0"
        >
          Voltar ao Hub
        </Link>
        <button
          onClick={onStartExam}
          disabled={isLoading}
          className="flex items-center gap-2 px-8 py-3.5 rounded-xl font-bold bg-primary text-primary-foreground hover:bg-primary/90 shadow-md transition-transform active:scale-95 text-base cursor-pointer shrink-0"
        >
          <Stethoscope className="w-5 h-5" />
          <span>Entrar na Sala de Exame</span>
        </button>
      </div>
    </div>
  );
}
