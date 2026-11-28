// Parser puro de datas coladas para cadastro em lote de plantões (dd/mm, dd/mm/aaaa, aaaa-mm-dd).

export interface ParsedPasteDate {
  raw: string;
  dateIso: string;
  inferredYear: boolean;
}

export interface DatePasteParseResult {
  valid: ParsedPasteDate[];
  invalid: string[];
  duplicatesRemoved: number;
}

export interface DatePasteOptions {
  /** Data de referência YYYY-MM-DD (padrão: hoje local). */
  referenceDateIso: string;
  /** Limites opcionais do rodízio vigente para desambiguar dd/mm sem ano. */
  rodizioStartIso?: string | null;
  rodizioEndIso?: string | null;
}

function isValidCalendarDate(year: number, month: number, day: number): boolean {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return false;
  }
  if (year < 2000 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }
  const d = new Date(Date.UTC(year, month - 1, day));
  return (
    d.getUTCFullYear() === year &&
    d.getUTCMonth() === month - 1 &&
    d.getUTCDate() === day
  );
}

function toIso(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function resolveImplicitYear(
  month: number,
  day: number,
  opts: DatePasteOptions
): string | null {
  const refYear = Number(opts.referenceDateIso.slice(0, 4)) || new Date().getFullYear();
  const candidates: string[] = [];
  for (const y of [refYear, refYear + 1]) {
    if (isValidCalendarDate(y, month, day)) {
      candidates.push(toIso(y, month, day));
    }
  }
  if (candidates.length === 0) return null;

  // 1) Se cair dentro do rodízio vigente, priorizar esse ano
  if (opts.rodizioStartIso && opts.rodizioEndIso) {
    const inside = candidates.find(
      (iso) => iso >= opts.rodizioStartIso! && iso <= opts.rodizioEndIso!
    );
    if (inside) return inside;
  }

  // 2) Senão, próxima ocorrência a partir da data de referência
  const upcoming = candidates.find((iso) => iso >= opts.referenceDateIso);
  if (upcoming) return upcoming;

  // 3) Fallback para o ano seguinte (ex.: 29/02 em ano bissexto futuro ou fim de ano)
  for (let y = refYear + 1; y <= refYear + 4; y++) {
    if (isValidCalendarDate(y, month, day)) {
      return toIso(y, month, day);
    }
  }
  return candidates[0];
}

export function parsePastedDates(
  rawText: string,
  opts: DatePasteOptions
): DatePasteParseResult {
  const tokens = rawText
    .split(/[\n,;|\s]+/)
    .map((t) => t.trim())
    .filter(Boolean);

  const valid: ParsedPasteDate[] = [];
  const invalid: string[] = [];
  const seen = new Set<string>();
  let duplicatesRemoved = 0;

  for (const token of tokens) {
    let resolvedIso: string | null = null;
    let inferredYear = false;

    const isoMatch = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(token);
    if (isoMatch) {
      const y = Number(isoMatch[1]);
      const m = Number(isoMatch[2]);
      const d = Number(isoMatch[3]);
      if (isValidCalendarDate(y, m, d)) {
        resolvedIso = toIso(y, m, d);
      }
    } else {
      const brFull = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(token);
      if (brFull) {
        const d = Number(brFull[1]);
        const m = Number(brFull[2]);
        const y = Number(brFull[3]);
        if (isValidCalendarDate(y, m, d)) {
          resolvedIso = toIso(y, m, d);
        }
      } else {
        const brShort = /^(\d{1,2})\/(\d{1,2})$/.exec(token);
        if (brShort) {
          const d = Number(brShort[1]);
          const m = Number(brShort[2]);
          const iso = resolveImplicitYear(m, d, opts);
          if (iso) {
            resolvedIso = iso;
            inferredYear = true;
          }
        }
      }
    }

    if (!resolvedIso) {
      invalid.push(token);
      continue;
    }

    if (seen.has(resolvedIso)) {
      duplicatesRemoved += 1;
      continue;
    }
    seen.add(resolvedIso);
    valid.push({ raw: token, dateIso: resolvedIso, inferredYear });
  }

  valid.sort((a, b) => a.dateIso.localeCompare(b.dateIso));
  return { valid, invalid, duplicatesRemoved };
}
