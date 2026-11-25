"use client";

import React from "react";
import Link from "next/link";
import { Clock } from "lucide-react";

interface LessonNotesEditorProps {
  bookmarkInput: string;
  notesInput: string;
  savingProgress: boolean;
  onChangeBookmark: (nextBookmark: string) => void;
  onChangeNotes: (nextNotes: string) => void;
  onSave: () => void;
}

export const LessonNotesEditor = React.memo(function LessonNotesEditor({
  bookmarkInput,
  notesInput,
  savingProgress,
  onChangeBookmark,
  onChangeNotes,
  onSave,
}: LessonNotesEditorProps) {
  return (
    <div className="rounded-md border border-line-subtle bg-canvas p-4 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-accent" />
          <label htmlFor="lesson-bookmark" className="text-xs font-semibold text-ink-primary">
            Parei em (mm:ss):
          </label>
          <input
            id="lesson-bookmark"
            type="text"
            value={bookmarkInput}
            onChange={(e) => onChangeBookmark(e.target.value)}
            placeholder="ex: 24:15"
            className="w-24 px-2.5 py-1 rounded-xs border border-line-subtle bg-surface text-xs font-mono-lab text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Link
            href="/caderno"
            className="px-2.5 py-1.5 rounded-md border border-line-subtle bg-surface hover:bg-elevated text-ink-secondary hover:text-ink-primary text-xs font-medium transition-colors"
          >
            Ver no Caderno
          </Link>
          <button
            type="button"
            disabled={savingProgress}
            onClick={onSave}
            className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors cursor-pointer"
          >
            Salvar ponto e anotações
          </button>
        </div>
      </div>
      <textarea
        value={notesInput}
        onChange={(e) => onChangeNotes(e.target.value)}
        rows={3}
        placeholder="Anote pontos-chave da aula, pegadinhas de prova ou dúvidas para revisar..."
        className="w-full px-3 py-2 rounded-md border border-line-subtle bg-surface text-xs text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent resize-y"
      />
    </div>
  );
});
