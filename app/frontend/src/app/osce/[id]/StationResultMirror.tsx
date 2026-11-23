"use client";

import React, { useState } from "react";
import {
  Award,
  CheckCircle2,
  XCircle,
  Clock,
  BookOpen,
  RotateCcw,
  ChevronRight,
  ShieldAlert,
  HelpCircle,
  FileText,
  Activity,
  HeartPulse,
  Stethoscope,
  Pill,
  Zap,
  Hourglass,
  Target,
  Filter,
} from "lucide-react";
import { OsceTimelinePostMortem } from "@/types/api";
import {
  PreceptorFeedback,
  CompetencyRadarScores,
  EvaluatedBaremaItem,
  FulfillmentStatus,
} from "@/types/osce-evaluation";

interface StationResultMirrorProps {
  feedback: PreceptorFeedback;
  timeline?: OsceTimelinePostMortem;
  stationTitle: string;
  institution: string;
  area: string;
  subtema?: string;
  elapsedSeconds: number;
  onRetryStation: () => void;
  onGoBack?: () => void;
}

// =========================================================================
// RADAR DE 5 COMPETÊNCIAS MÉDICAS EM SVG PURO (LEVE & 60FPS)
// =========================================================================
function CompetencyRadarSVG({ scores }: { scores?: CompetencyRadarScores }) {
  const safeScores: CompetencyRadarScores = scores || {
    clinical_reasoning: null,
    communication_empathy: null,
    surgical_semiotics: null,
    patient_safety: null,
    sus_time_efficiency: null,
  };

  const axes = [
    { key: "clinical_reasoning", label: "Raciocínio Clínico", value: safeScores.clinical_reasoning },
    { key: "communication_empathy", label: "Comunicação & Empatia", value: safeScores.communication_empathy },
    { key: "surgical_semiotics", label: "Semiotécnica & Prática", value: safeScores.surgical_semiotics },
    { key: "patient_safety", label: "Segurança do Paciente", value: safeScores.patient_safety },
    { key: "sus_time_efficiency", label: "Eficiência / Tempo", value: safeScores.sus_time_efficiency },
  ];

  const size = 320;
  const center = size / 2;
  const maxRadius = 100;
  const totalAxes = axes.length;

  const getCoordinates = (index: number, valuePct: number | null | undefined) => {
    const angle = (index * (2 * Math.PI)) / totalAxes - Math.PI / 2;
    const numeric = valuePct !== null && valuePct !== undefined && Number.isFinite(valuePct) ? valuePct : 0;
    const r = (Math.max(0, Math.min(100, numeric)) / 100) * maxRadius;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle),
    };
  };

  const polygonPoints = axes
    .map((axis, i) => {
      const { x, y } = getCoordinates(i, axis.value);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="relative flex flex-col items-center justify-center p-2">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="w-full max-w-[320px] h-auto overflow-visible select-none drop-shadow-sm"
      >
        {/* Anéis de Referência: 25%, 50%, 75%, 100% */}
        {[25, 50, 75, 100].map((level) => {
          const ringPoints = axes
            .map((_, i) => {
              const { x, y } = getCoordinates(i, level);
              return `${x},${y}`;
            })
            .join(" ");

          return (
            <polygon
              key={level}
              points={ringPoints}
              fill={level === 100 ? "currentColor" : "none"}
              className={level === 100 ? "text-muted/15 stroke-border" : "stroke-border/60"}
              strokeWidth="1"
              strokeDasharray={level === 50 ? "3,3" : undefined}
            />
          );
        })}

        {/* Eixos Radiais e Rótulos */}
        {axes.map((axis, i) => {
          const end = getCoordinates(i, 100);
          const labelPos = getCoordinates(i, 122);
          const hasValue = axis.value !== null && axis.value !== undefined && Number.isFinite(axis.value);
          return (
            <g key={axis.key}>
              <line
                x1={center}
                y1={center}
                x2={end.x}
                y2={end.y}
                className="stroke-border/70"
                strokeWidth="1"
              />
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-ink-secondary text-[9px] font-mono font-bold uppercase tracking-wider"
              >
                {axis.label} ({hasValue ? `${Math.round(Number(axis.value))}%` : "Sem evidência"})
              </text>
            </g>
          );
        })}

        {/* Polígono de Desempenho do Candidato */}
        <polygon
          points={polygonPoints}
          className="fill-success/20 stroke-success transition-all duration-500 ease-out"
          strokeWidth="2.5"
        />

        {/* Pontos nos vértices */}
        {axes.map((axis, i) => {
          if (axis.value === null || axis.value === undefined) return null;
          const pt = getCoordinates(i, axis.value);
          return (
            <circle
              key={axis.key}
              cx={pt.x}
              cy={pt.y}
              r="4"
              className="fill-success stroke-surface stroke-2"
            />
          );
        })}
      </svg>
    </div>
  );
}

// =========================================================================
// COMPONENTE PRINCIPAL: ESPELHO DE CORREÇÃO (2ª FASE)
// =========================================================================
export function StationResultMirror({
  feedback,
  timeline,
  stationTitle,
  institution,
  area,
  subtema,
  elapsedSeconds,
  onRetryStation,
  onGoBack,
}: StationResultMirrorProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [timelineFilter, setTimelineFilter] = useState<"all" | "gaps" | "timely">("all");

  const verdictStyles = {
    "APROVADO COM DISTINÇÃO": {
      bg: "bg-success/10 border-success/40 text-success",
      badge: "bg-success text-success-foreground",
      border: "border-success/30",
    },
    "APROVADO NO LIMITE": {
      bg: "bg-primary/10 border-primary/40 text-primary",
      badge: "bg-primary text-primary-foreground",
      border: "border-primary/30",
    },
    "REPROVADO POR TÉCNICA": {
      bg: "bg-warning/10 border-warning/40 text-warning",
      badge: "bg-warning text-warning-foreground",
      border: "border-warning/30",
    },
    "ELIMINADO POR IATROGENIA": {
      bg: "bg-destructive/15 border-destructive/60 text-destructive",
      badge: "bg-destructive text-destructive-foreground",
      border: "border-destructive/50",
    },
  };

  const safeFinalScore = Number.isFinite(Number(feedback?.final_score))
    ? Number(feedback.final_score)
    : 0;
  const safeCutoffScore = Number.isFinite(Number(feedback?.cutoff_score))
    ? Number(feedback.cutoff_score)
    : 7.0;

  const currentVerdict = feedback?.headline_verdict || (
    feedback?.approved ? "APROVADO NO LIMITE" : "REPROVADO POR TÉCNICA"
  );
  const style = verdictStyles[currentVerdict] || verdictStyles["REPROVADO POR TÉCNICA"];

  const formatTime = (secs: number) => {
    const safeSecs = Number.isFinite(secs) && secs >= 0 ? Math.floor(secs) : 0;
    const m = Math.floor(safeSecs / 60);
    const s = safeSecs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const getStatusBadge = (status: FulfillmentStatus | string) => {
    switch (status) {
      case "FULL":
      case "cumprido_total":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-success/15 text-success border border-success/30">
            <CheckCircle2 className="w-3 h-3" /> CUMPRIDO TOTAL
          </span>
        );
      case "PARTIAL":
      case "cumprido_parcial":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-warning/15 text-warning border border-warning/30">
            <HelpCircle className="w-3 h-3" /> PARCIAL
          </span>
        );
      case "CRITICAL_ERROR":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-destructive/20 text-destructive border border-destructive/40">
            <ShieldAlert className="w-3 h-3" /> IATROGENIA
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-muted text-muted-foreground border border-border">
            <XCircle className="w-3 h-3" /> NÃO REALIZADO
          </span>
        );
    }
  };

  const evaluatedItems: EvaluatedBaremaItem[] = feedback?.evaluated_items || [];
  const filteredItems = evaluatedItems.filter((item) => {
    if (selectedCategory === "ALL") return true;
    const cat = (item.category || "").toUpperCase();
    return cat.includes(selectedCategory);
  });

  return (
    <div className="max-w-5xl mx-auto w-full p-4 md:p-6 space-y-6 text-ink-primary font-sans pb-10 animate-in fade-in duration-300">
      {/* ========================================================================= */}
      {/* 1. CABEÇALHO OFICIAL DA BANCA EXAMINADORA */}
      {/* ========================================================================= */}
      <div className="bg-surface border border-line-subtle rounded-2xl p-6 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-3 py-1 rounded-md text-xs font-mono font-bold uppercase tracking-widest bg-primary/10 text-primary border border-primary/30">
              BANCA {institution || "USP-RP"}
            </span>
            <span className="text-xs font-mono text-ink-secondary flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-primary" />
              ESPELHO DE CORREÇÃO
            </span>
            <span className="text-xs font-mono text-ink-muted">
              • Tempo Decorrido: {formatTime(elapsedSeconds)}
            </span>
            {(feedback?.graded_with_ai === false || feedback?.grading_notice === "Corrigido sem IA") && (
              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-mono font-bold bg-warning/15 text-warning border border-warning/30">
                {feedback?.grading_notice || "Corrigido sem IA"}
              </span>
            )}
          </div>
          <h1 className="text-2xl md:text-3xl font-black text-ink-primary tracking-tight">
            {stationTitle}
          </h1>
          <div className="text-xs text-ink-secondary flex gap-3 font-medium">
            <span><strong>Grande Área:</strong> {area}</span>
            {subtema && <span>• <strong>Subtema:</strong> {subtema}</span>}
          </div>
        </div>

        {/* NOTA E VEREDITO */}
        <div className={`p-5 rounded-xl border flex flex-col items-center justify-center min-w-[220px] text-center ${style.bg} ${style.border}`}>
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest opacity-80">
            Nota da Estação
          </span>
          <div className="text-4xl md:text-5xl font-black font-mono my-1 tracking-tight tabular-nums">
            {safeFinalScore.toFixed(1)}
            <span className="text-lg font-normal text-ink-muted"> / 10.0</span>
          </div>
          <span className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${style.badge}`}>
            {currentVerdict}
          </span>
          <span className="text-[10px] font-mono text-ink-secondary mt-1">
            Referência de treino: {safeCutoffScore.toFixed(1)}
          </span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. ALERTAS DE RED FLAGS / IATROGENIAS CLÍNICAS */}
      {/* ========================================================================= */}
      {feedback?.red_flags_triggered && feedback.red_flags_triggered.length > 0 && (
        <div className="p-5 rounded-2xl border-2 border-destructive/50 bg-destructive/10 space-y-3 shadow-sm">
          <div className="flex items-center gap-2.5 text-destructive font-bold text-sm tracking-wide">
            <ShieldAlert className="w-5 h-5" />
            <span>FALTAS GRAVES / IATROGENIAS IDENTIFICADAS PELA BANCA:</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {feedback.red_flags_triggered.map((rf, idx) => {
              const deduction = Number.isFinite(Number(rf.score_deduction)) ? Number(rf.score_deduction) : 0;
              return (
                <div
                  key={idx}
                  className="bg-surface border border-destructive/40 rounded-lg p-3.5 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-xs font-bold text-destructive">
                    <span>{rf.title}</span>
                    <span className="font-mono text-destructive">-{deduction.toFixed(1)} pts</span>
                  </div>
                  <p className="text-xs text-ink-secondary leading-snug">
                    {rf.description}
                  </p>
                  <div className="text-[11px] font-mono text-destructive bg-destructive/10 px-2 py-1 rounded border border-destructive/20">
                    Consequência: {rf.clinical_consequence}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. RADAR DE COMPETÊNCIAS + PARECER DO PRECEPTOR CHEFE */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* COLUNA ESQUERDA: RADAR DE 5 COMPETÊNCIAS (5 Colunas) */}
        <div className="lg:col-span-5 bg-surface border border-line-subtle rounded-2xl p-6 flex flex-col justify-between shadow-sm">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wider text-ink-primary flex items-center gap-2">
              <Award className="w-4 h-4 text-success" /> Matriz de Competências Médicas
            </h2>
            <p className="text-xs text-ink-secondary mt-1">
              Avaliação psicométrica baseada nas diretrizes de 2ª fase das bancas de residência.
            </p>
          </div>

          <div className="my-2">
            <CompetencyRadarSVG scores={feedback?.competency_radar_5d} />
          </div>

          <div className="space-y-2 border-t border-line-subtle pt-3 text-xs">
            <div className="flex justify-between text-ink-secondary">
              <span className="flex items-center gap-1.5">
                <HeartPulse className="w-3.5 h-3.5 text-destructive" /> Segurança do Paciente:
              </span>
              <span className="font-mono font-bold text-ink-primary">
                {feedback?.competency_radar_5d?.patient_safety !== null && feedback?.competency_radar_5d?.patient_safety !== undefined
                  ? `${feedback.competency_radar_5d.patient_safety}%`
                  : "Sem evidência"}
              </span>
            </div>
            <div className="flex justify-between text-ink-secondary">
              <span className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-primary" /> Semiotécnica &amp; Prática:
              </span>
              <span className="font-mono font-bold text-ink-primary">
                {feedback?.competency_radar_5d?.surgical_semiotics !== null && feedback?.competency_radar_5d?.surgical_semiotics !== undefined
                  ? `${feedback.competency_radar_5d.surgical_semiotics}%`
                  : "Sem evidência"}
              </span>
            </div>
          </div>
        </div>

        {/* COLUNA DIREITA: PARECER FORMATIVO DO PRECEPTOR CHEFE (7 Colunas) */}
        <div className="lg:col-span-7 bg-surface border border-line-subtle rounded-2xl p-6 flex flex-col justify-between space-y-4 shadow-sm">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wider text-primary flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-primary" /> Parecer do Preceptor
            </h2>
            <p className="text-xs text-ink-primary mt-2 leading-relaxed bg-canvas p-3 rounded-xl border border-line-subtle">
              {feedback?.chief_preceptor_review?.executive_summary || feedback?.summary}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="bg-success/5 border border-success/20 rounded-xl p-3 space-y-1">
              <span className="font-bold text-success uppercase text-[10px] tracking-wider block">
                ✓ Pontos Fortes na Estação
              </span>
              {(feedback?.chief_preceptor_review?.what_went_well || []).length > 0 ? (
                <ul className="space-y-1 text-ink-secondary list-disc list-inside">
                  {(feedback?.chief_preceptor_review?.what_went_well || []).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-muted italic">Nenhum critério foi cumprido integralmente nesta sessão.</p>
              )}
            </div>

            <div className="bg-destructive/5 border border-destructive/20 rounded-xl p-3 space-y-1">
              <span className="font-bold text-destructive uppercase text-[10px] tracking-wider block">
                ⚠ Correções Críticas
              </span>
              {(feedback?.chief_preceptor_review?.critical_corrections || []).length > 0 ? (
                <ul className="space-y-1 text-ink-secondary list-disc list-inside">
                  {(feedback?.chief_preceptor_review?.critical_corrections || []).map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-muted italic">Nenhuma correção pendente identificada.</p>
              )}
            </div>
          </div>

          {/* CONDUTA CANÔNICA PADRÃO-OURO */}
          <div className="bg-canvas border border-primary/30 rounded-lg p-4 space-y-1.5">
            <div className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
              <span>Conduta Canônica Padrão-Ouro (Gabarito da Estação)</span>
            </div>
            <p className="text-xs text-ink-primary leading-relaxed font-mono whitespace-pre-line bg-surface p-2.5 rounded-lg border border-line-subtle">
              {feedback?.chief_preceptor_review?.gold_standard_canonical_conduct ||
                "Abordagem sistemática segundo os protocolos do ATLS/ACLS com estabilização e conduta cirúrgica precisa."}
            </p>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 4. TABELA DO CHECKLIST BAREMA OFICIAL ITEM A ITEM */}
      {/* ========================================================================= */}
      <div className="bg-surface border border-line-subtle rounded-2xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-line-subtle flex flex-wrap justify-between items-center gap-4">
          <div>
            <h2 className="text-base font-bold text-ink-primary flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" /> Checklist Barema Itemizado
            </h2>
            <p className="text-xs text-ink-secondary">
              Auditoria de cada critério da estação com carimbo de tempo e evidência capturada
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5 text-xs">
            {["ALL", "ANAMNESE", "FISICO", "PROCEDIMENTO", "DIAGNOSTICO", "CONDUTA"].map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1.5 rounded-lg font-mono text-[11px] font-semibold transition cursor-pointer ${
                  selectedCategory === cat
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {cat === "ALL" ? "Todos" : cat}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-canvas text-[11px] font-bold uppercase tracking-wider text-ink-secondary border-b border-line-subtle">
                <th className="py-3.5 px-4">Cód / Bloco</th>
                <th className="py-3.5 px-4">Critério Avaliado pela Banca</th>
                <th className="py-3.5 px-4">Evidência Auditada</th>
                <th className="py-3.5 px-4 text-center">Status</th>
                <th className="py-3.5 px-4 text-right">Pontuação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-xs">
              {filteredItems.map((item, idx) => {
                const rawAwarded = item.awarded_score ?? (item as unknown as { score_earned?: number }).score_earned ?? 0;
                const awarded = Number.isFinite(Number(rawAwarded)) ? Number(rawAwarded) : 0;
                const rawMax = item.max_score ?? (item as unknown as { weight?: number }).weight ?? 1.0;
                const maxScore = Number.isFinite(Number(rawMax)) ? Number(rawMax) : 1.0;

                return (
                  <tr key={item.criterion_id || idx} className="hover:bg-muted/30 transition">
                    <td className="py-3.5 px-4 font-mono font-bold text-ink-primary whitespace-nowrap">
                      <div>{item.code || `ITEM-${idx + 1}`}</div>
                      <span className="text-[10px] text-primary font-normal">{item.category}</span>
                    </td>
                    <td className="py-3.5 px-4 text-ink-primary max-w-md font-medium">
                      {item.description || item.code}
                    </td>
                    <td className="py-3.5 px-4 text-ink-secondary font-mono text-[11px] max-w-sm space-y-1">
                      <div>
                        {item.timestamp_achieved_sec !== null && item.timestamp_achieved_sec !== undefined && (
                          <span className="inline-flex items-center gap-1 text-primary mr-1.5">
                            <Clock className="w-3 h-3" />
                            {formatTime(item.timestamp_achieved_sec)}
                          </span>
                        )}
                        {item.evidence_quote ? (
                          <span className="italic text-ink-primary">“{item.evidence_quote}”</span>
                        ) : (
                          item.evidence_citation || (item as unknown as { evidence?: string }).evidence || "Não identificado nas ações."
                        )}
                      </div>
                      {item.evidence_quote && item.rationale && (
                        <div className="text-[10px] font-sans text-ink-muted">
                          {item.rationale}
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      {getStatusBadge(item.status)}
                    </td>
                    <td className="py-3.5 px-4 text-right font-mono font-bold whitespace-nowrap tabular-nums">
                      <span className={awarded > 0 ? "text-success" : "text-ink-muted"}>
                        {awarded.toFixed(2)}
                      </span>
                      <span className="text-ink-muted"> / {maxScore.toFixed(2)}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 5. LINHA DO TEMPO BEIRA-LEITO (INCORPORADA AO ESPELHO ÚNICO) */}
      {/* ========================================================================= */}
      {timeline && (
        <div className="bg-surface border border-line-subtle rounded-2xl overflow-hidden shadow-sm">
          <div className="p-5 border-b border-line-subtle flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-0.5">
              <h2 className="text-base font-bold text-ink-primary flex items-center gap-2">
                <Clock className="w-4 h-4 text-primary" /> Linha do Tempo Beira-Leito
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary">
                  {timeline.summary.pace_label}
                </span>
              </h2>
              <p className="text-xs text-ink-secondary">
                Cronologia das decisões, intervenções, pausas e omissões durante a estação
              </p>
            </div>

            <div className="flex items-center gap-1.5 text-[11px]">
              <Filter className="w-3.5 h-3.5 text-ink-muted mr-0.5" />
              <button
                type="button"
                onClick={() => setTimelineFilter("all")}
                className={`px-2.5 py-1 rounded-lg font-bold transition-colors cursor-pointer ${
                  timelineFilter === "all" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                Todos ({timeline.events.length})
              </button>
              <button
                type="button"
                onClick={() => setTimelineFilter("gaps")}
                className={`px-2.5 py-1 rounded-lg font-bold transition-colors cursor-pointer ${
                  timelineFilter === "gaps" ? "bg-rose-500 text-white" : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                Atrasos &amp; Falhas
              </button>
              <button
                type="button"
                onClick={() => setTimelineFilter("timely")}
                className={`px-2.5 py-1 rounded-lg font-bold transition-colors cursor-pointer ${
                  timelineFilter === "timely" ? "bg-emerald-500 text-white" : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                Oportunos ({timeline.summary.timely_count})
              </button>
            </div>
          </div>

          <div className="p-5 space-y-3">
            {(timeline.events || [])
              .filter((evt) => {
                if (timelineFilter === "gaps") return evt.status === "delayed" || evt.status === "critical_gap";
                if (timelineFilter === "timely") return evt.status === "timely";
                return true;
              })
              .map((evt, idx) => {
                const isTimely = evt.status === "timely";
                const isDelayed = evt.status === "delayed";
                const isGap = evt.status === "critical_gap";
                const EventIcon =
                  evt.event_type === "vitals" ? Activity :
                  evt.event_type === "physical_exam" ? Stethoscope :
                  evt.event_type === "lab_imaging" ? FileText :
                  evt.event_type === "prescription" ? Pill :
                  evt.event_type === "procedure" ? Zap :
                  evt.event_type === "conduct" ? Target :
                  evt.event_type === "hesitacao" ? Hourglass :
                  evt.event_type === "omissao" ? ShieldAlert :
                  Clock;

                return (
                  <div
                    key={idx}
                    className={`p-3 rounded-xl border text-xs space-y-1 ${
                      isGap
                        ? "border-destructive/40 bg-destructive/5"
                        : isDelayed
                        ? "border-warning/40 bg-warning/5"
                        : isTimely
                        ? "border-success/30 bg-success/5"
                        : "border-line-subtle bg-canvas"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 font-bold text-ink-primary">
                        <EventIcon className="w-3.5 h-3.5 text-primary shrink-0" />
                        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-surface border border-line-subtle">
                          {evt.time_formatted}
                        </span>
                        <span>{evt.title}</span>
                      </div>
                      <span className="text-[10px] font-mono font-bold text-ink-secondary shrink-0">
                        {evt.score_impact}
                      </span>
                    </div>
                    <p className="text-ink-secondary">{evt.description}</p>
                    <p className="text-[11px] text-ink-muted italic">{evt.feedback}</p>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. FOOTER: PRESCRIÇÃO DE REMEDIAÇÃO NO MEDQUEST & RE-TREINO */}
      {/* ========================================================================= */}
      <div className="bg-surface border border-primary/30 rounded-lg p-6 flex flex-col md:flex-row justify-between items-center gap-4">
        <div className="space-y-1">
          <div className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
            <BookOpen className="w-4 h-4" /> Prescrição de Estudo Dirigido no MedQuest
          </div>
          <p className="text-sm text-ink-secondary">
            Recomendamos revisar a teoria e as questões comentadas de{" "}
            <span className="font-semibold text-ink-primary">
              {area} ({subtema || "Protocolos Beira-Leito"})
            </span>.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {onGoBack && (
            <button
              onClick={onGoBack}
              className="px-4 py-2.5 rounded-xl bg-muted hover:bg-muted/80 text-ink-primary text-xs font-bold transition border border-line-subtle cursor-pointer"
            >
              Voltar à Arena
            </button>
          )}
          <button
            onClick={onRetryStation}
            className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold flex items-center gap-2 shadow-sm transition cursor-pointer"
          >
            <RotateCcw className="w-4 h-4" /> Refazer Esta Estação <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
