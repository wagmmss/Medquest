"use client";

import React from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Award, ChevronLeft, Printer, Sparkles } from "lucide-react";
import {
  OsceCircuitPlanResponse,
  OsceCircuitSummaryResponse,
  OsceFinishResponse,
  OsceStationDetail,
} from "@/types/api";
import { PreceptorFeedback } from "@/types/osce-evaluation";

const StationResultMirror = dynamic(
  () => import("./StationResultMirror").then((m) => m.StationResultMirror),
  { ssr: false }
);

interface OsceFinishViewProps {
  station: OsceStationDetail;
  report: OsceFinishResponse;
  finalElapsedSeconds: number;
  circuitId?: string;
  step: number;
  circuitPlan: OsceCircuitPlanResponse | null;
  circuitSummary: OsceCircuitSummaryResponse | null;
  showCircuitModal: boolean;
  isLoadingCircuit: boolean;
  onAdvanceCircuit: () => void;
  onOpenCircuitSummary: () => void;
  onCloseCircuitModal: () => void;
  onNavigateHub: () => void;
}

export function OsceFinishView({
  station,
  report,
  finalElapsedSeconds,
  circuitId,
  step,
  circuitPlan,
  circuitSummary,
  showCircuitModal,
  isLoadingCircuit,
  onAdvanceCircuit,
  onOpenCircuitSummary,
  onCloseCircuitModal,
  onNavigateHub,
}: OsceFinishViewProps) {
  return (
    <>
      <div className="flex-1 flex flex-col p-4 max-w-4xl mx-auto w-full space-y-6 pb-32 animate-in fade-in duration-300 print:p-0 print:m-0 print:max-w-full print:pb-0 print:space-y-4">
        <div className="hidden print:block border-b-2 border-line-strong pb-4 text-ink-primary">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-xl font-black uppercase tracking-wider">MedQuest • Prova Prática Beira-Leito (OSCE)</h1>
              <p className="text-xs font-bold text-ink-secondary">Simulador de 2ª Fase • Parecer da Estação</p>
            </div>
            <div className="text-right text-xs text-ink-muted font-mono">
              <div>Data: {new Date().toLocaleDateString("pt-BR")}</div>
              <div>Banca: {station.institution || "USP-RP"}</div>
            </div>
          </div>
          <div className="mt-3 pt-2 border-t border-line-subtle flex justify-between text-xs">
            <span><strong>Estação:</strong> {station.title}</span>
            <span><strong>Grande Área:</strong> {station.area}</span>
            <span><strong>Subtema:</strong> {station.subtema}</span>
          </div>
        </div>

        <StationResultMirror
          feedback={report.preceptor_feedback as unknown as PreceptorFeedback}
          timeline={report.timeline_post_mortem}
          stationTitle={station.title}
          institution={station.institution || "USP-RP"}
          area={station.area}
          subtema={station.subtema}
          elapsedSeconds={finalElapsedSeconds}
          onRetryStation={() => window.location.reload()}
          onGoBack={onNavigateHub}
        />

        <div className="flex items-center justify-between pt-4 border-t border-border print:hidden">
          <div className="flex items-center gap-2">
            <Link
              href="/osce"
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-border hover:bg-muted text-xs font-semibold"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Voltar ao Catálogo</span>
            </Link>

            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-border bg-card hover:bg-muted text-xs font-bold text-foreground transition-all shadow-sm active:scale-95 cursor-pointer"
              title="Imprimir ou salvar parecer oficial em PDF"
            >
              <Printer className="w-4 h-4 text-primary" />
              <span>Imprimir Espelho (PDF)</span>
            </button>
          </div>

          {circuitId && (
            step < 5 ? (
              <button
                onClick={onAdvanceCircuit}
                className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-black text-xs font-bold shadow-md transition-transform active:scale-95 flex items-center gap-2 cursor-pointer"
              >
                <Award className="w-4 h-4" />
                <span>
                  Avançar para Estação {step + 1} de 5 {circuitPlan?.stations?.find((s) => s.step === step + 1)?.area ? `(${circuitPlan.stations.find((s) => s.step === step + 1)?.area})` : ""} →
                </span>
              </button>
            ) : (
              <button
                onClick={onOpenCircuitSummary}
                disabled={isLoadingCircuit}
                className="px-5 py-2 rounded-md bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold transition-colors flex items-center gap-2 cursor-pointer"
              >
                <Sparkles className="w-4 h-4" />
                <span>{isLoadingCircuit ? "Calculando Parecer Global..." : "Parecer Final do Circuito (0 a 50 pts)"}</span>
              </button>
            )
          )}
        </div>
      </div>

      {showCircuitModal && circuitSummary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="bg-surface border border-line-subtle rounded-lg max-w-2xl w-full p-6 md:p-8 space-y-6 shadow-2xl overflow-y-auto max-h-[90vh]">
            <div className="text-center space-y-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/15 text-amber-500 text-xs font-bold uppercase tracking-wider">
                <Award className="w-4 h-4" />
                <span>Circuito Misto de Treino • 5 Estações</span>
              </div>
              <h2 className="text-2xl md:text-3xl font-black text-foreground">
                Resultado do Circuito de Treino
              </h2>
              <p className="text-xs text-muted-foreground">
                Filtro de referência: {circuitPlan?.institution || station.institution || "Misto"}
              </p>
            </div>

            <div className={`p-6 rounded-2xl border-2 flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
              circuitSummary.approved ? "bg-emerald-500/10 border-emerald-500/30" : "bg-rose-500/10 border-rose-500/30"
            }`}>
              <div>
                <div className="text-xs uppercase font-bold text-muted-foreground">Nota Consolidada (0 a 50)</div>
                <div className={`text-4xl font-black ${circuitSummary.approved ? "text-emerald-500" : "text-rose-500"}`}>
                  {circuitSummary.total_score.toFixed(1)} <span className="text-xl text-muted-foreground">/ 50.0</span>
                </div>
                <div className="text-xs font-semibold text-foreground/80 mt-1">
                  Aproveitamento Global: {circuitSummary.percentage}% • Referência interna de treino: 35,0 / 50,0 pts
                </div>
              </div>

              <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase text-center ${
                circuitSummary.approved ? "bg-emerald-500 text-black" : "bg-rose-500 text-white"
              }`}>
                {circuitSummary.approved ? "Meta de Treino Atingida" : "Abaixo da Referência"}
              </div>
            </div>

            <div className="p-4 rounded-xl bg-muted/40 border border-border text-xs leading-relaxed text-foreground/90 space-y-1">
              <span className="font-bold text-foreground block">Parecer da Banca Examinadora:</span>
              <p>{circuitSummary.board_feedback}</p>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Desempenho por Estação de Especialidade:
              </div>
              <div className="border border-border rounded-xl divide-y divide-border overflow-hidden bg-background">
                {circuitSummary.stations.map((s) => (
                  <div key={s.station_id} className="p-3 text-xs flex items-center justify-between gap-3">
                    <div>
                      <div className="font-bold text-foreground">{s.area}</div>
                      <div className="text-[11px] text-muted-foreground line-clamp-1">{s.title}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <span className={`px-2 py-0.5 rounded-md font-mono font-bold text-[11px] ${
                        s.approved ? "bg-emerald-500/15 text-emerald-500" : "bg-rose-500/15 text-rose-500"
                      }`}>
                        {s.final_score.toFixed(1)} / 10.0
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-border">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onCloseCircuitModal}
                  className="px-4 py-2 rounded-xl border border-border hover:bg-muted text-xs font-semibold cursor-pointer"
                >
                  Fechar Espelho
                </button>
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="px-3.5 py-2 rounded-xl border border-border bg-card hover:bg-muted text-xs font-bold text-foreground flex items-center gap-1.5 cursor-pointer shadow-sm active:scale-95"
                  title="Imprimir ou Salvar Parecer Consolidado do Circuito em PDF"
                >
                  <Printer className="w-3.5 h-3.5 text-primary" />
                  <span>Imprimir Circuito</span>
                </button>
              </div>
              <button
                type="button"
                onClick={onNavigateHub}
                className="px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 cursor-pointer"
              >
                Concluir e Voltar ao Hub
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
