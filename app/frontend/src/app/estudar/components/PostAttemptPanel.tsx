"use client";

import React from "react";
import dynamic from "next/dynamic";
import clsx from "clsx";
import toast from "react-hot-toast";
import { ArrowRight, BookOpen, CheckCircle2, Clock, RotateCcw } from "lucide-react";
import { AttemptResult, QuestionDetail } from "@/types/api";
import { ClinicalIcon } from "@/components/ui/ClinicalIcon";
import { AlternativeContent } from "@/components/AlternativeContent";
import { PreceptorSection, ChatMessage } from "./PreceptorSection";
import { DiscursiveAssessmentSection } from "./DiscursiveAssessmentSection";
import { buildAnkiCardFromQuestion, sendCardToAnki } from "@/lib/ankiExport";

const ExplanationViewer = dynamic(
  () => import("@/components/ExplanationViewer").then((mod) => mod.ExplanationViewer),
  {
    ssr: false,
    loading: () => <div className="h-32 w-full rounded-xl bg-surface-subtle animate-pulse" />,
  }
);

function formatReviewDatePtBr(dateStr?: string | null): string {
  if (!dateStr) return "Em breve";
  const parsed = new Date(dateStr);
  if (Number.isNaN(parsed.getTime())) return "Em breve";
  return parsed.toLocaleDateString("pt-BR");
}

interface PostAttemptPanelProps {
  question: QuestionDetail;
  attemptResult: AttemptResult;
  zenMode: boolean;
  userWrittenAnswer: string;
  selectedLetter: string | null;
  attendingTip: string | null;
  currentIndex: number;
  queueLength: number;
  chatMessages: ChatMessage[];
  preceptorInput: string;
  askingPreceptor: boolean;
  onImageClick: (src: string) => void;
  onRequestFinish: () => void;
  onNextQuestion: () => void;
  onSendMessage: (overrideText?: string) => void;
  onClearChat: () => void;
  onReviewFSRS: (conf: string, explicitIsCorrect?: boolean) => void;
  onReopenDiscursiveAssessment: () => void;
}

export function PostAttemptPanel({
  question: q,
  attemptResult,
  zenMode,
  userWrittenAnswer,
  selectedLetter,
  attendingTip,
  currentIndex,
  queueLength,
  chatMessages,
  preceptorInput,
  askingPreceptor,
  onImageClick,
  onRequestFinish,
  onNextQuestion,
  onSendMessage,
  onClearChat,
  onReviewFSRS,
  onReopenDiscursiveAssessment,
}: PostAttemptPanelProps) {
  const isDiscursive = Boolean(q.is_discursive || (q.alternatives || []).length <= 1);

  return (
    <div
      className={clsx(
        "w-full flex flex-col gap-5 animate-in slide-in-from-bottom-2 fade-in duration-200",
        !zenMode && "lg:col-span-12"
      )}
    >
      {isDiscursive && (
        <div className="bg-surface border border-line-subtle shadow-xs rounded-sm p-4 md:p-5 flex flex-col gap-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {userWrittenAnswer ? (
              <div className="flex flex-col gap-1.5 bg-canvas p-3 rounded-xs border border-line-subtle">
                <div className="flex items-center gap-1.5 text-[11px] font-bold text-ink-muted uppercase tracking-wider font-mono-lab">
                  <ClinicalIcon name="notes" size={13} />
                  <span>Sua Resposta Anotada</span>
                </div>
                <div className="text-ink text-sm leading-relaxed whitespace-pre-wrap font-normal">
                  {userWrittenAnswer}
                </div>
              </div>
            ) : null}
            {q.alternatives?.[0]?.text &&
              !/^(?:anote sua|questão dissertativa|ver padrão)/i.test(q.alternatives[0].text) && (
                <div
                  className={clsx(
                    "flex flex-col gap-1.5 bg-normal/10 p-3 rounded-xs border border-normal/25",
                    !userWrittenAnswer && "md:col-span-2"
                  )}
                >
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-normal uppercase tracking-wider font-mono-lab">
                    <ClinicalIcon name="checkCircle" size={13} />
                    <span>Resposta Curta Esperada pela Banca</span>
                  </div>
                  <div className="text-ink text-sm leading-relaxed font-bold">
                    <AlternativeContent content={q.alternatives[0].text} onImageClick={onImageClick} />
                  </div>
                </div>
              )}
          </div>
        </div>
      )}

      <div
        className={clsx(
          "rounded-sm border shadow-xs overflow-hidden",
          attemptResult.is_correct === true
            ? "bg-normal/5 border-normal/25"
            : attemptResult.is_correct === false
            ? "bg-critical/5 border-critical/25"
            : "bg-surface border-line-subtle"
        )}
      >
        <div
          className={clsx(
            "px-4 py-3 border-b flex items-center justify-between",
            attemptResult.is_correct === true
              ? "border-normal/20 bg-normal/10"
              : attemptResult.is_correct === false
              ? "border-critical/20 bg-critical/10"
              : "border-line-subtle bg-canvas"
          )}
        >
          <div className="flex flex-wrap items-center gap-2 font-bold text-sm">
            {attemptResult.is_correct === true ? (
              <>
                <ClinicalIcon name="checkCircle" size={16} className="text-normal" />
                <span className="text-normal font-mono-lab uppercase tracking-wide">
                  {attemptResult.assisted || Boolean(attendingTip)
                    ? "Resposta Correta (com ajuda)"
                    : "Resposta Correta"}
                </span>
                {(attemptResult.assisted || Boolean(attendingTip)) && (
                  <span className="text-[10px] font-mono-lab px-2 py-0.5 rounded-xs bg-warning/15 text-warning border border-warning/30">
                    Dica do Preceptor usada • FSRS calibrado
                  </span>
                )}
              </>
            ) : attemptResult.is_correct === false ? (
              <>
                <ClinicalIcon name="crossCircle" size={16} className="text-critical" />
                <span className="text-critical font-mono-lab uppercase tracking-wide">Resposta Incorreta</span>
              </>
            ) : (
              <>
                <ClinicalIcon name="checkCircle" size={16} className="text-accent" />
                <span className="text-ink font-mono-lab uppercase tracking-wide">Padrão Oficial da Banca</span>
              </>
            )}
          </div>
          {attemptResult.is_correct !== null && (
            <div className="flex items-center gap-2">
              {currentIndex < queueLength - 1 && (
                <button
                  type="button"
                  onClick={onRequestFinish}
                  className="flex items-center gap-1 bg-surface border border-line-subtle hover:bg-elevated font-mono-lab text-ink-muted hover:text-ink px-2.5 py-1 rounded-xs transition-colors text-[11px] cursor-pointer"
                  title="Finalizar sessão agora"
                >
                  <CheckCircle2 size={12} /> Finalizar
                </button>
              )}
              <button
                onClick={onNextQuestion}
                className="flex items-center gap-1.5 bg-surface border border-line-subtle hover:bg-elevated font-mono-lab font-bold text-ink px-3 py-1 rounded-xs transition-colors text-xs cursor-pointer"
              >
                {currentIndex === queueLength - 1 ? (
                  <>
                    Finalizar <CheckCircle2 size={14} className="text-normal" />
                  </>
                ) : (
                  <>
                    Próxima <ArrowRight size={14} />
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        <div className="p-4 md:p-6 flex flex-col gap-5">
          <h3 className="text-sm font-bold text-ink flex items-center gap-2 uppercase tracking-wider font-mono-lab">
            <ClinicalIcon name="notes" size={16} className="text-accent" />
            {isDiscursive ? "Padrão de Resposta da Banca & Comentário" : "Comentário do Professor"}
          </h3>
          <ExplanationViewer
            explanation={attemptResult.explanation}
            correctLetter={isDiscursive ? null : attemptResult.correct_letter}
            questionId={q.id}
            userLetter={selectedLetter || attemptResult.correct_letter || undefined}
            isDiscursive={isDiscursive}
          />

          {q.times_wrong && q.times_wrong > 0 ? (
            <div className="flex items-center gap-1.5 text-xs text-critical font-mono-lab font-semibold bg-critical/10 border border-critical/20 px-2.5 py-1 rounded-xs w-fit">
              Você já errou esta questão {q.times_wrong} {q.times_wrong === 1 ? "vez" : "vezes"} no passado.
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                const card = buildAnkiCardFromQuestion(q, attemptResult);
                const mode = await sendCardToAnki(card);
                toast.success(
                  mode === "ankiconnect"
                    ? "Card enviado para o Anki Desktop!"
                    : "AnkiConnect offline: arquivo .tsv baixado para importar no Anki!"
                );
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xs border border-line-subtle bg-elevated hover:bg-canvas hover:border-accent text-xs font-semibold text-ink-primary transition-colors cursor-pointer"
            >
              <BookOpen size={13} className="text-accent" />
              Enviar para o Anki (.tsv / AnkiConnect)
            </button>
          </div>

          <div className="w-full">
            <PreceptorSection
              messages={chatMessages}
              preceptorInput={preceptorInput}
              askingPreceptor={askingPreceptor}
              onSendMessage={onSendMessage}
              onClearChat={onClearChat}
            />
          </div>

          {attemptResult.is_correct === null ? (
            <DiscursiveAssessmentSection onReviewFSRS={onReviewFSRS} />
          ) : attemptResult.next_review_date ? (
            <div className="pt-3 border-t border-line-subtle flex items-center justify-between flex-wrap gap-2 text-xs font-mono-lab text-ink-muted">
              <div className="flex items-center gap-1.5">
                <Clock size={14} />
                Próxima revisão FSRS: {formatReviewDatePtBr(attemptResult.next_review_date)}
              </div>
              {isDiscursive && (
                <button
                  onClick={onReopenDiscursiveAssessment}
                  className="text-xs text-accent hover:underline font-semibold cursor-pointer"
                >
                  Alterar autoavaliação
                </button>
              )}
            </div>
          ) : (
            <div className="pt-3 border-t border-line-subtle flex flex-col gap-2.5">
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-bold text-ink uppercase tracking-wider font-mono-lab">
                  {attemptResult.is_correct
                    ? "Como foi resolver essa questão?"
                    : "Revisão agendada (FSRS v6):"}
                </span>
                <span className="text-[11px] text-ink-muted">
                  {attemptResult.is_correct
                    ? "Classifique seu nível de domínio para calibrar a repetição espaçada."
                    : "Questões erradas retornam na próxima semana (D+7) para consolidação clínica."}
                </span>
              </div>

              {attemptResult.is_correct ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <button
                    title="Acertei no chute ou com grande insegurança. Intervalo FSRS: ~15 dias."
                    onClick={() => onReviewFSRS("chutei")}
                    className="bg-warning/10 hover:bg-warning/20 text-ink border border-warning/30 font-bold py-2.5 px-2 rounded-xs transition-colors text-xs flex flex-col items-center justify-center gap-0.5 cursor-pointer font-mono-lab"
                  >
                    <span className="flex items-center gap-1 font-semibold">Chutei</span>
                    <span className="text-[10px] text-ink-muted font-normal">+15 dias • [1]</span>
                  </button>
                  <button
                    title="Raciocínio correto, mas exigiu esforço ou dica. Intervalo FSRS calibrado."
                    onClick={() => onReviewFSRS("duvida")}
                    className="bg-accent/10 hover:bg-accent/20 text-ink border border-accent/40 shadow-xs font-bold py-2.5 px-2 rounded-xs transition-colors text-xs flex flex-col items-center justify-center gap-0.5 cursor-pointer font-mono-lab ring-1 ring-accent/20"
                  >
                    <span className="flex items-center gap-1 font-semibold">Com Esforço</span>
                    <span className="text-[10px] text-accent font-normal">
                      {attemptResult.assisted || Boolean(attendingTip)
                        ? "+15 dias (c/ dica) • [2]"
                        : "+34 dias • [2]"}
                    </span>
                  </button>
                  {attemptResult.assisted || Boolean(attendingTip) ? (
                    <button
                      title="Como a Dica do Preceptor (/dica) foi consultada antes da resposta, o intervalo máximo é calibrado como Hard (~15 dias)."
                      onClick={() => onReviewFSRS("certeza")}
                      className="bg-surface-subtle hover:bg-elevated text-ink-secondary border border-line-subtle font-bold py-2.5 px-2 rounded-xs transition-colors text-xs flex flex-col items-center justify-center gap-0.5 cursor-pointer font-mono-lab"
                    >
                      <span className="flex items-center gap-1 font-semibold">Com Ajuda (Máx. Hard)</span>
                      <span className="text-[10px] text-warning font-normal">+15 dias • [3]</span>
                    </button>
                  ) : (
                    <button
                      title="Questão dominada com total convicção. Intervalo FSRS: ~76 dias."
                      onClick={() => onReviewFSRS("certeza")}
                      className="bg-normal/10 hover:bg-normal/20 text-ink border border-normal/30 font-bold py-2.5 px-2 rounded-xs transition-colors text-xs flex flex-col items-center justify-center gap-0.5 cursor-pointer font-mono-lab"
                    >
                      <span className="flex items-center gap-1 font-semibold">Domino</span>
                      <span className="text-[10px] text-normal font-normal">+76 dias • [3]</span>
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row gap-2">
                  <button
                    title="Agendada para 7 dias no FSRS v6."
                    onClick={() => onReviewFSRS("duvida")}
                    className="flex-1 bg-critical/10 hover:bg-critical/20 text-critical border border-critical/30 font-bold py-2.5 px-3 rounded-xs transition-colors text-xs flex items-center justify-center gap-2 cursor-pointer font-mono-lab shadow-xs"
                  >
                    <RotateCcw size={14} />
                    <span>Revisar na Próxima Semana</span>
                    <span className="text-[10px] font-normal py-0.5 px-1.5 bg-critical/15 rounded-xs">
                      D+7 • [Enter]
                    </span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
