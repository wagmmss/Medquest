"use client";

import dynamic from "next/dynamic";
import { SessionAnswer } from "../quizSessionReducer";

const QuizSessionReportModal = dynamic(
  () => import("./QuizSessionReportModal").then((m) => m.QuizSessionReportModal),
  { ssr: false }
);

export function QuizLoadingView() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <div className="w-8 h-8 border-4 border-accent/30 border-t-accent rounded-full animate-spin" />
      <p className="text-ink-secondary text-sm font-medium">Montando sua sessão...</p>
    </div>
  );
}

export function QuizSummaryView({
  sessionAnswers,
  onBackToFilters,
  onRestartSession,
}: {
  sessionAnswers: Record<number, SessionAnswer>;
  onBackToFilters: () => void;
  onRestartSession: () => void;
}) {
  const totalAnswered = Object.keys(sessionAnswers).length;
  const correctCount = Object.values(sessionAnswers).filter((a) => a.result?.is_correct).length;
  const wrongItems = Object.entries(sessionAnswers)
    .filter(([, ans]) => ans.result && !ans.result.is_correct)
    .map(([qid, ans]) => ({ question_id: Number(qid), wrong_letter: ans.letter }));
  const accuracy = totalAnswered > 0 ? Math.round((correctCount / totalAnswered) * 100) : 0;

  return (
    <QuizSessionReportModal
      totalAnswered={totalAnswered}
      correctCount={correctCount}
      accuracy={accuracy}
      wrongItems={wrongItems}
      onBackToFilters={onBackToFilters}
      onRestartSession={onRestartSession}
    />
  );
}
