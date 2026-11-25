"use client";

import React from "react";
import Image from "next/image";
import { BookOpen } from "lucide-react";
import clsx from "clsx";
import { HighlightColor } from "@/types/api";
import { normalizeImageSrc } from "@/components/FormattedContent";
import { HighlightableContent } from "@/components/HighlightableContent";
import { type TextHighlight } from "@/lib/textHighlights";

const EMPTY_HIGHLIGHTS: TextHighlight[] = [];

interface QuestionClinicalCaseBlockProps {
  stem: string;
  extraImages: string[];
  highlights?: TextHighlight[];
  highlightColor: HighlightColor;
  highlightEnabled: boolean;
  onAddHighlight: (range: Omit<TextHighlight, "id">) => void;
  onRemoveHighlight: (id: string) => void;
  onImageClick: (src: string) => void;
  variant?: "study" | "exam";
  zenMode?: boolean;
}

export const QuestionClinicalCaseBlock = React.memo(function QuestionClinicalCaseBlock({
  stem,
  extraImages,
  highlights = EMPTY_HIGHLIGHTS,
  highlightColor,
  highlightEnabled,
  onAddHighlight,
  onRemoveHighlight,
  onImageClick,
  variant = "study",
  zenMode = false,
}: QuestionClinicalCaseBlockProps) {
  const isExam = variant === "exam";

  return (
    <div
      className={clsx(
        isExam
          ? "bg-elevated/30 border-l-4 border-primary rounded-r-xl p-5 mb-6"
          : "bg-surface border border-accent/35 shadow-2xs rounded-md p-5 md:p-6 flex flex-col gap-4",
        !isExam && !zenMode && "lg:col-span-6 lg:sticky lg:top-20 h-fit max-h-[calc(100vh-6rem)] overflow-y-auto"
      )}
    >
      <h4
        className={clsx(
          isExam
            ? "text-sm font-bold text-primary mb-3 uppercase tracking-wider"
            : "text-xs font-bold text-accent uppercase tracking-wider flex items-center gap-2 font-mono-lab"
        )}
      >
        {!isExam && <BookOpen size={16} />}
        {isExam ? "Caso Clínico" : "Caso Clínico Associado"}
      </h4>
      <HighlightableContent
        content={stem}
        onImageClick={onImageClick}
        className={
          isExam
            ? "text-ink-primary text-lg leading-relaxed"
            : "text-ink text-base md:text-lg leading-relaxed font-normal"
        }
        highlights={highlights}
        activeColor={highlightColor}
        enabled={highlightEnabled}
        onAddHighlight={onAddHighlight}
        onRemoveHighlight={onRemoveHighlight}
      />
      {extraImages.length > 0 && (
        <div
          className={clsx(
            "flex flex-col sm:flex-row flex-wrap",
            isExam ? "gap-4 mt-4" : "gap-3 mt-1"
          )}
        >
          {extraImages.map((img, i) => (
            <div
              key={i}
              className={clsx(
                "relative group overflow-hidden border border-line-subtle cursor-zoom-in transition-all sm:max-w-xs",
                isExam
                  ? "rounded-lg bg-elevated/20 hover:shadow-md"
                  : "rounded-sm bg-canvas hover:border-line-strong"
              )}
              onClick={() => onImageClick(img)}
            >
              <Image
                src={normalizeImageSrc(img)}
                alt={`Imagem do Caso ${i + 1}`}
                width={800}
                height={600}
                unoptimized
                className={clsx(
                  "max-w-full h-auto object-cover transition-transform",
                  isExam ? "hover:scale-[1.02] duration-300" : "hover:scale-[1.01] duration-200"
                )}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
