"use client";

import React from "react";
import Image from "next/image";
import { ImageOff } from "lucide-react";
import clsx from "clsx";
import { normalizeImageSrc } from "@/components/FormattedContent";
import { ClinicalIcon } from "@/components/ui/ClinicalIcon";

interface QuestionExtraImagesProps {
  images: string[];
  onImageClick: (src: string) => void;
  variant?: "study" | "exam";
}

export const QuestionExtraImages = React.memo(function QuestionExtraImages({
  images,
  onImageClick,
  variant = "study",
}: QuestionExtraImagesProps) {
  if (images.length === 0) return null;
  const isExam = variant === "exam";

  return (
    <div
      className={clsx(
        "flex flex-col sm:flex-row flex-wrap",
        isExam ? "gap-4 mb-8" : "gap-3 mt-2"
      )}
    >
      {images.map((img, i) => (
        <div
          key={i}
          className={clsx(
            "relative group overflow-hidden border border-line-subtle cursor-zoom-in transition-all sm:max-w-sm",
            isExam
              ? "rounded-lg bg-elevated/20 hover:shadow-md"
              : "rounded-sm bg-canvas hover:border-line-strong"
          )}
          onClick={() => onImageClick(img)}
        >
          <Image
            src={normalizeImageSrc(img)}
            alt={`Imagem ${i + 1}`}
            width={800}
            height={600}
            unoptimized
            className={clsx(
              "max-w-full h-auto object-cover transition-transform",
              isExam ? "hover:scale-[1.02] duration-300" : "hover:scale-[1.01] duration-200"
            )}
            onError={(e) => {
              e.currentTarget.style.display = "none";
              if (e.currentTarget.nextElementSibling) {
                (e.currentTarget.nextElementSibling as HTMLElement).style.display = "flex";
              }
            }}
          />
          {!isExam && (
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center pointer-events-none">
              <ClinicalIcon
                name="maximize"
                size={18}
                className="text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-md"
              />
            </div>
          )}
          <div className="hidden flex-col items-center justify-center p-6 text-ink-muted gap-2">
            <ImageOff size={24} />
            <span className="text-xs font-mono-lab">Imagem indisponível</span>
          </div>
        </div>
      ))}
    </div>
  );
});
