"use client";

import React, { useMemo } from "react";
import Link from "next/link";
import { CheckCircle2, Clock, Eye, FileText, Lock, ShieldCheck, Sparkles, Stethoscope } from "lucide-react";
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

function renderInlineMarkdown(text: string): React.ReactNode {
  const tokenRegex = /(\*\*\*[^*\n]+?\*\*\*|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*|`[^`\n]+`)/g;
  const parts = text.split(tokenRegex);

  return parts.map((part, idx) => {
    if (!part) return null;
    if (part.startsWith("***") && part.endsWith("***") && part.length > 6) {
      return (
        <strong key={idx} className="font-semibold italic text-foreground">
          {part.slice(3, -3)}
        </strong>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return (
        <em key={idx} className="italic text-muted-foreground">
          {part.slice(1, -1)}
        </em>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={idx} className="font-mono text-[0.9em] px-1.5 py-0.5 rounded bg-muted text-foreground">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function renderKeyValueOrInline(text: string): React.ReactNode {
  const kvMatch = text.match(/^([A-Za-zÀ-ÿ0-9()/\s-]{2,36}):\s+(.+)$/);
  if (kvMatch && !text.startsWith("**")) {
    return (
      <>
        <strong className="font-semibold text-foreground">{kvMatch[1]}:</strong>{" "}
        {renderInlineMarkdown(kvMatch[2])}
      </>
    );
  }
  return renderInlineMarkdown(text);
}

function OsceDoorMarkdown({ content }: { content: string }) {
  const blocks = useMemo(() => {
    const normalized = (content || "").replace(/\\n/g, "\n").replace(/\r\n/g, "\n").trim();
    if (!normalized) return null;

    const lines = normalized.split("\n");
    const nodes: React.ReactNode[] = [];
    let paragraphLines: string[] = [];
    let listItems: string[] = [];
    let listType: "ul" | "ol" | null = null;

    const flushParagraph = () => {
      const cleaned = paragraphLines.map((l) => l.trim()).filter(Boolean);
      paragraphLines = [];
      if (cleaned.length === 0) return;

      // Nota de rodapé em itálico (ex: *Tempo de prova: 10 minutos.*)
      if (
        cleaned.length === 1 &&
        /^\*[^*\n]+\*$/.test(cleaned[0])
      ) {
        nodes.push(
          <div
            key={`note-${nodes.length}`}
            className="pt-3 mt-4 border-t border-line-subtle flex items-center gap-2 text-xs font-medium text-muted-foreground"
          >
            <Clock className="w-3.5 h-3.5 text-primary shrink-0" />
            <span>{cleaned[0].slice(1, -1)}</span>
          </div>
        );
        return;
      }

      nodes.push(
        <p key={`p-${nodes.length}`} className="text-sm md:text-[15px] leading-relaxed text-foreground/90">
          {cleaned.map((ln, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <br />}
              {renderInlineMarkdown(ln)}
            </React.Fragment>
          ))}
        </p>
      );
    };

    const flushList = () => {
      if (listItems.length === 0 || !listType) return;
      const items = [...listItems];
      const currentType = listType;
      listItems = [];
      listType = null;

      if (currentType === "ul") {
        nodes.push(
          <ul key={`ul-${nodes.length}`} className="space-y-2 pl-1 text-sm md:text-[15px] leading-relaxed text-foreground/90">
            {items.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-primary/70 shrink-0" aria-hidden="true" />
                <span className="flex-1">{renderKeyValueOrInline(item)}</span>
              </li>
            ))}
          </ul>
        );
        return;
      }

      nodes.push(
        <ol key={`ol-${nodes.length}`} className="space-y-2 text-sm leading-relaxed">
          {items.map((item, idx) => {
            const lockedMatch = item.match(/^\[?(Bloqueada\b[^\]]*)\]?$/i);
            if (lockedMatch) {
              return (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                >
                  <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[11px] font-mono font-bold text-muted-foreground shrink-0">
                    {idx + 1}
                  </span>
                  <div className="flex items-start gap-1.5 pt-0.5">
                    <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-muted-foreground/80" />
                    <span>{lockedMatch[1]}</span>
                  </div>
                </li>
              );
            }

            return (
              <li
                key={idx}
                className="flex items-start gap-2.5 rounded-lg border border-primary/20 bg-primary/[0.04] px-3 py-2.5 text-foreground/95"
              >
                <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-[11px] font-mono font-bold text-primary shrink-0">
                  {idx + 1}
                </span>
                <span className="flex-1">{renderInlineMarkdown(item)}</span>
              </li>
            );
          })}
        </ol>
      );
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();

      if (!line) {
        flushParagraph();
        flushList();
        continue;
      }

      // Título Markdown (# .. ######)
      const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        flushParagraph();
        flushList();
        const headingText = headingMatch[2].replace(/^ESTAÇÃO:\s*/i, "");
        nodes.push(
          <div key={`h-${nodes.length}`} className="pb-1">
            {/^ESTAÇÃO:/i.test(headingMatch[2]) && (
              <span className="block text-[10px] font-bold uppercase tracking-widest text-primary mb-1">
                Estação Clínica
              </span>
            )}
            <h2 className="text-base sm:text-lg font-extrabold tracking-tight text-foreground leading-snug">
              {renderInlineMarkdown(headingText)}
            </h2>
          </div>
        );
        continue;
      }

      // Subtítulo em negrito isolado (ex: **Candidato(a)**: ou **Candidato(a):**)
      const sectionLabelMatch = line.match(/^\*\*([^*\n]{2,60}?):?\*\*:?$/);
      if (sectionLabelMatch) {
        flushParagraph();
        flushList();
        nodes.push(
          <h3
            key={`sec-${nodes.length}`}
            className="text-xs font-bold uppercase tracking-wider text-primary pt-3 first:pt-0"
          >
            {sectionLabelMatch[1]}
          </h3>
        );
        continue;
      }

      // Lista com marcadores (- ou * ou •)
      const bulletMatch = line.match(/^[-*•]\s+(.+)$/);
      if (bulletMatch) {
        flushParagraph();
        if (listType !== "ul") {
          flushList();
          listType = "ul";
        }
        listItems.push(bulletMatch[1]);
        continue;
      }

      // Lista numerada (1. ...)
      const orderedMatch = line.match(/^\d+[.)]\s+(.+)$/);
      if (orderedMatch) {
        flushParagraph();
        if (listType !== "ol") {
          flushList();
          listType = "ol";
        }
        listItems.push(orderedMatch[1]);
        continue;
      }

      // Citação (> ...)
      const quoteMatch = line.match(/^>\s*(.+)$/);
      if (quoteMatch) {
        flushParagraph();
        flushList();
        nodes.push(
          <blockquote
            key={`q-${nodes.length}`}
            className="border-l-2 border-primary/40 pl-3.5 py-0.5 text-sm italic text-muted-foreground"
          >
            {renderInlineMarkdown(quoteMatch[1])}
          </blockquote>
        );
        continue;
      }

      flushList();
      paragraphLines.push(line);
    }

    flushParagraph();
    flushList();

    return nodes;
  }, [content]);

  if (!blocks) return null;

  return <div className="space-y-2.5 text-left">{blocks}</div>;
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
    <div className="shrink-0 flex flex-col items-center p-2 sm:p-4 max-w-3xl mx-auto text-center space-y-6 w-full pb-12 animate-in fade-in zoom-in-95 duration-200">
      <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
        <Stethoscope className="w-4 h-4" />
        <span>Porta da Estação • {station.institution}</span>
        {circuitId && <span className="ml-2 text-amber-500 font-extrabold">• Circuito: Estação {step} de 5</span>}
      </div>

      <h1 className="text-2xl sm:text-3xl md:text-4xl font-black text-foreground tracking-tight leading-tight">
        {selectedMode === "blind" ? neutralStationLabel : station.title}
      </h1>

      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs md:text-sm text-muted-foreground font-semibold">
        <span>{station.area}</span>
        {selectedMode !== "blind" && (
          <>
            <span aria-hidden="true">•</span>
            <span>{station.subtema}</span>
          </>
        )}
        <span aria-hidden="true">•</span>
        <span className="inline-flex items-center gap-1.5 text-primary">
          <Clock className="w-4 h-4" />
          {Math.round(station.duration_seconds / 60)} minutos
        </span>
      </div>

      <div className="w-full text-left rounded-2xl border border-line-subtle bg-surface shadow-sm overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-5 sm:px-7 py-3.5 bg-canvas/80 border-b border-line-subtle">
          <div className="flex items-center gap-2 text-xs font-bold uppercase text-muted-foreground tracking-wider">
            <FileText className="w-3.5 h-3.5 text-primary" />
            <span>Instruções Fixadas na Porta da Sala</span>
          </div>
          <span className="text-[11px] font-mono font-semibold text-muted-foreground">
            {station.institution}
          </span>
        </div>
        <div className="p-5 sm:p-7">
          <OsceDoorMarkdown content={station.scenario_door_markdown} />
        </div>
      </div>

      {taskProgress.visible_tasks.length > 0 && (
        <div className="w-full text-left rounded-2xl border border-line-subtle bg-surface p-5 sm:p-6 space-y-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <span>Tarefas Sequenciais da Estação</span>
            <span className="text-[11px] font-mono text-primary">
              Liberação progressiva na sala
            </span>
          </div>
          <div className="space-y-2">
            {taskProgress.visible_tasks.map((t) => (
              <div
                key={t.id}
                className={`flex items-start gap-2.5 p-3 rounded-xl border text-xs leading-relaxed ${
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

      <div className="w-full text-left rounded-2xl border border-line-subtle bg-surface p-5 sm:p-6 space-y-3.5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Escolha o Modo de Simulação
          </span>
          <span className="text-[11px] text-muted-foreground font-medium hidden sm:inline">
            Pode alternar livremente a qualquer momento
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <button
            type="button"
            onClick={() => onSelectMode("guided")}
            className={`p-4 rounded-xl border-2 text-left transition-all relative flex flex-col justify-between cursor-pointer ${
              selectedMode === "guided"
                ? "border-accent bg-accent/10 shadow-sm ring-2 ring-accent/20"
                : "border-border bg-background hover:bg-muted/50"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-accent shrink-0" />
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
                <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
              )}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Barema dinâmico com pontuação ao vivo. O Preceptor alerta sobre tempos críticos, dosagem de eletrólitos e condutas essenciais antes do fim do tempo.
            </p>
            <div className="mt-3 flex items-center gap-1.5 text-[10px] font-bold text-accent">
              <Sparkles className="w-3 h-3" />
              <span>Recomendado para aprendizado e fixação</span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onSelectMode("blind")}
            className={`p-4 rounded-xl border-2 text-left transition-all relative flex flex-col justify-between cursor-pointer ${
              selectedMode === "blind"
                ? "border-primary bg-primary/10 shadow-sm ring-2 ring-primary/20"
                : "border-border bg-background hover:bg-muted/50"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <Eye className="w-5 h-5 text-muted-foreground shrink-0" />
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

      <div className="w-full flex flex-col-reverse sm:flex-row items-center justify-center gap-3 pt-2">
        <Link
          href="/osce"
          className="w-full sm:w-auto text-center px-6 py-3 rounded-xl border border-border bg-card hover:bg-muted text-sm font-semibold transition-colors shrink-0"
        >
          Voltar ao Hub
        </Link>
        <button
          type="button"
          onClick={onStartExam}
          disabled={isLoading}
          className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl font-bold bg-primary text-primary-foreground hover:bg-primary/90 shadow-md transition-transform active:scale-95 text-base cursor-pointer shrink-0 disabled:opacity-50"
        >
          <Stethoscope className="w-5 h-5" />
          <span>Entrar na Sala de Exame</span>
        </button>
      </div>
    </div>
  );
}
