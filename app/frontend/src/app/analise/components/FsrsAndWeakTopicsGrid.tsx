"use client";

import Link from "next/link";
import clsx from "clsx";
import type { AtRiskTopic, DistractorStat, WeakTopic } from "@/types/api";

interface FsrsAndWeakTopicsGridProps {
  atRiskTopics: AtRiskTopic[];
  weakTopics: WeakTopic[];
  distractorsBySubtema: Map<string, DistractorStat>;
}

export function FsrsAndWeakTopicsGrid({
  atRiskTopics,
  weakTopics,
  distractorsBySubtema,
}: FsrsAndWeakTopicsGridProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <section className="bg-surface border border-line-subtle rounded-lg p-6 flex flex-col">
        <div className="mb-4">
          <h3 className="font-bold text-lg text-ink-primary">Radar de Esquecimento (FSRS)</h3>
          <p className="text-xs text-ink-muted mt-1">
            Subtemas com questões próximas do limiar de retenção programada.
          </p>
        </div>

        <div className="flex-1 space-y-2.5">
          {atRiskTopics && atRiskTopics.length > 0 ? (
            atRiskTopics.map((topic, idx) => (
              <Link
                key={`${topic.subtema}-${idx}`}
                href={`/estudar?subtema=${encodeURIComponent(topic.subtema)}&status=srs_due&limit=20`}
                className="flex items-center justify-between p-3 bg-canvas rounded-md border border-line-subtle hover:border-warning/50 transition-colors"
              >
                <div className="flex flex-col min-w-0 pr-3">
                  <span
                    className="font-medium text-sm text-ink-primary leading-tight truncate"
                    title={topic.subtema}
                  >
                    {topic.subtema}
                  </span>
                  <span className="text-xs text-ink-muted mt-0.5 font-mono-lab tabular-nums">
                    {topic.items_count} {topic.items_count === 1 ? "questão em risco" : "questões em risco"}
                  </span>
                </div>
                <div className="flex flex-col items-end shrink-0 gap-1">
                  <span className="text-xs font-mono-lab tabular-nums font-semibold text-warning">
                    {topic.retrievability !== undefined
                      ? `${Math.round(topic.retrievability * 100)}% retenção`
                      : "Baixa retenção"}
                  </span>
                  <span className="text-[11px] font-semibold text-accent">
                    Treinar →
                  </span>
                </div>
              </Link>
            ))
          ) : (
            <div className="h-full min-h-[140px] flex items-center justify-center text-xs text-ink-muted text-center p-4 border border-dashed border-line-subtle rounded-md">
              Nenhuma questão com risco elevado de esquecimento no momento.
            </div>
          )}
        </div>
      </section>

      <section className="bg-surface border border-line-subtle rounded-lg overflow-hidden flex flex-col">
        <div className="p-5 border-b border-line-subtle bg-elevated/60">
          <h3 className="font-bold text-lg text-ink-primary">Tópicos Fracos & Armadilhas</h3>
          <p className="text-xs text-ink-muted mt-1">
            Ordenados por acurácia, com amostra visível e padrão de distratores.
          </p>
        </div>
        <div className="divide-y divide-line-subtle">
          {weakTopics && weakTopics.length > 0 ? (
            weakTopics.slice(0, 8).map((wt, idx) => {
              const distractor = distractorsBySubtema.get(wt.topic);
              const worstChoice = distractor?.wrong_choices?.[0];

              return (
                <Link
                  key={`${wt.topic}-${idx}`}
                  href={`/estudar?subtema=${encodeURIComponent(wt.topic)}&status=all&limit=10`}
                  className="p-4 hover:bg-elevated/40 transition-colors flex items-center justify-between gap-4 group"
                >
                  <div className="min-w-0 flex-1">
                    <p
                      className="font-medium text-sm text-ink-primary truncate group-hover:text-primary transition-colors"
                      title={wt.topic}
                    >
                      {wt.topic}
                    </p>
                    <p className="text-xs text-ink-muted mt-0.5 font-mono-lab tabular-nums">
                      {wt.correct} acertos em {wt.attempts} tentativas
                      {wt.attempts < 10 ? " · amostra inicial" : ""}
                    </p>

                    {worstChoice && worstChoice.count >= 2 && wt.attempts >= 5 && (
                      <div className="mt-2 flex items-center gap-1.5 flex-wrap bg-destructive/5 w-fit px-2 py-1 rounded-xs border border-destructive/20 text-xs">
                        <span className="text-ink-muted">Distrator recorrente:</span>
                        <span className="inline-flex items-center justify-center bg-canvas font-mono-lab font-bold text-ink-primary w-5 h-5 rounded-xs text-[10px] uppercase border border-line-subtle">
                          {worstChoice.letter}
                        </span>
                        <span className="font-mono-lab font-semibold text-destructive">
                          ({worstChoice.count}x)
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span
                      className={clsx(
                        "font-mono-lab tabular-nums font-bold text-base",
                        (wt.accuracy || 0) < 0.5 ? "text-destructive" : "text-warning"
                      )}
                    >
                      {((wt.accuracy || 0) * 100).toFixed(0)}%
                    </span>
                    <span className="text-[11px] font-semibold text-accent">
                      Treinar (10q) →
                    </span>
                  </div>
                </Link>
              );
            })
          ) : (
            <div className="p-8 text-center text-xs text-ink-muted">
              Nenhum tópico fraco identificado ainda (mínimo de 5 tentativas por tema).
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
