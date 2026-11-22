import type { HighlightColor } from "@/types/api";

export interface TextHighlight {
  id: string;
  start: number;
  end: number;
  color: HighlightColor;
}

export const HIGHLIGHT_MARK_CLASSES: Record<HighlightColor, string> = {
  yellow: "bg-amber-300/65 dark:bg-amber-400/35 text-inherit rounded-[3px] px-0.5 cursor-pointer transition-opacity hover:opacity-75",
  green: "bg-emerald-300/60 dark:bg-emerald-400/35 text-inherit rounded-[3px] px-0.5 cursor-pointer transition-opacity hover:opacity-75",
  blue: "bg-sky-300/60 dark:bg-sky-400/35 text-inherit rounded-[3px] px-0.5 cursor-pointer transition-opacity hover:opacity-75",
  pink: "bg-rose-300/60 dark:bg-rose-400/35 text-inherit rounded-[3px] px-0.5 cursor-pointer transition-opacity hover:opacity-75",
};

/**
 * Insere um novo grifo mantendo intervalos estritamente disjuntos e ordenados:
 * - Se sobrepõe ou encosta em grifo da mesma cor, funde em um único intervalo.
 * - Se sobrepõe grifo de cor diferente, recorta o antigo e aplica a nova cor na faixa selecionada.
 */
export function addOrMergeHighlight(
  existing: TextHighlight[],
  incoming: { id?: string; start: number; end: number; color: HighlightColor }
): TextHighlight[] {
  const start = Math.floor(incoming.start);
  const end = Math.floor(incoming.end);
  if (end <= start) return existing;

  let mergedStart = start;
  let mergedEnd = end;
  const remaining: TextHighlight[] = [];

  for (const hl of existing) {
    if (hl.color === incoming.color) {
      // Mesma cor: funde se houver sobreposição ou adjacência
      if (hl.end >= mergedStart && hl.start <= mergedEnd) {
        mergedStart = Math.min(mergedStart, hl.start);
        mergedEnd = Math.max(mergedEnd, hl.end);
        continue;
      }
      remaining.push(hl);
    } else {
      // Cor diferente: sem sobreposição mantém intacto
      if (hl.end <= start || hl.start >= end) {
        remaining.push(hl);
        continue;
      }
      // Recorta partes que ficam fora da nova faixa
      if (hl.start < start) {
        remaining.push({
          ...hl,
          id: `${hl.id}-l`,
          end: start,
        });
      }
      if (hl.end > end) {
        remaining.push({
          ...hl,
          id: `${hl.id}-r`,
          start: end,
        });
      }
    }
  }

  const nextId = incoming.id ?? `hl-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  remaining.push({
    id: nextId,
    start: mergedStart,
    end: mergedEnd,
    color: incoming.color,
  });

  remaining.sort((a, b) => a.start - b.start);
  return remaining;
}

function getBoundaryTextOffset(
  container: HTMLElement,
  targetNode: Node,
  targetOffset: number
): number | null {
  if (targetNode.nodeType === Node.TEXT_NODE) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let acc = 0;
    let current = walker.nextNode();
    while (current) {
      if (current === targetNode) {
        return acc + targetOffset;
      }
      acc += current.nodeValue?.length ?? 0;
      current = walker.nextNode();
    }
    return null;
  }

  // Element boundary (ex.: clique triplo ou arrasto até o fim de um parágrafo)
  if (targetNode.nodeType === Node.ELEMENT_NODE) {
    const el = targetNode as Element;
    const childCount = el.childNodes.length;
    const clampedOffset = Math.max(0, Math.min(targetOffset, childCount));
    const boundaryRange = document.createRange();
    boundaryRange.setStart(container, 0);
    boundaryRange.setEnd(el, clampedOffset);

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let acc = 0;
    let current = walker.nextNode();
    while (current) {
      const cmp = boundaryRange.comparePoint(current, 0);
      if (cmp === 0) {
        // Text node starts inside or at end of boundaryRange
        const endCmp = boundaryRange.comparePoint(current, current.nodeValue?.length ?? 0);
        if (endCmp <= 0) {
          acc += current.nodeValue?.length ?? 0;
        }
      } else if (cmp < 0) {
        acc += current.nodeValue?.length ?? 0;
      } else {
        break;
      }
      current = walker.nextNode();
    }
    return acc;
  }

  return null;
}

/**
 * Calcula os offsets [start, end) da seleção atual em relação ao texto renderizado
 * dentro de `container`, aparando espaços nas bordas.
 */
export function getSelectionOffsetsWithin(
  container: HTMLElement,
  selection: Selection | null
): { start: number; end: number; text: string } | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    return null;
  }

  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
    return null;
  }

  const rawText = selection.toString();
  const trimmed = rawText.trim();
  if (trimmed.length < 2) {
    return null;
  }

  const rawStart = getBoundaryTextOffset(container, range.startContainer, range.startOffset);
  const rawEnd = getBoundaryTextOffset(container, range.endContainer, range.endOffset);
  if (rawStart === null || rawEnd === null || rawEnd <= rawStart) {
    return null;
  }

  const leadingSpaces = rawText.length - rawText.trimStart().length;
  const trailingSpaces = rawText.length - rawText.trimEnd().length;
  const start = rawStart + leadingSpaces;
  const end = rawEnd - trailingSpaces;
  if (end <= start) {
    return null;
  }

  return { start, end, text: trimmed };
}
