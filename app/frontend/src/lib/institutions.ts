/**
 * Utilitários e listas canônicas compartilhadas para agrupamento e seleção de bancas/instituições.
 */

export const CANONICAL_SP_INSTITUTIONS: readonly string[] = [
  "USP-SP",
  "USP-RP",
  "UNICAMP",
  "UNIFESP",
  "SUS-SP",
];

export const DEFAULT_INSTITUTION_OPTIONS: Array<{ key: string; label: string }> = [
  { key: "USP-SP", label: "USP - São Paulo" },
  { key: "USP-RP", label: "USP - Ribeirão Preto" },
  { key: "UNICAMP", label: "Unicamp" },
  { key: "UNIFESP", label: "Unifesp / EPM" },
  { key: "SUS-SP", label: "SUS-SP" },
];

export const DEFAULT_SIMULADO_INSTITUTION_CODES: readonly string[] = [
  "SCMSP",
  "USP-SP",
  "SUS-SP",
  "USP-RP",
  "UNIFESP",
  "HSL",
  "EINSTEIN",
  "UNICAMP",
  "HRAC-USP",
];

export interface GroupedInstitution {
  base: string;
  codes: string[];
  n: number;
}

/** Agrupa variações anuais e siglas equivalentes de uma mesma instituição em ordem decrescente de volume. */
export function groupInstitutions(
  institutions?: Array<{ institution_code: string; n: number }> | null,
  fallbackCodes?: readonly string[]
): GroupedInstitution[] {
  if (!institutions || institutions.length === 0) {
    return (fallbackCodes ?? []).map((code) => ({ base: code, codes: [code], n: 0 }));
  }

  const map = new Map<string, { codes: string[]; n: number }>();
  for (const item of institutions) {
    let base = item.institution_code.replace(/\s+\d{4}$/, "").replace(/\s+\d$/, "").trim();
    if (base === "FAMEMA SP") base = "FAMEMA";
    if (base === "SCMRP") base = "SCM-RP";
    if (base === "SCM") base = "SCM-SP";

    const existing = map.get(base);
    if (existing) {
      existing.codes.push(item.institution_code);
      existing.n += item.n;
    } else {
      map.set(base, { codes: [item.institution_code], n: item.n });
    }
  }

  return Array.from(map.entries())
    .map(([base, data]) => ({ base, codes: data.codes, n: data.n }))
    .sort((a, b) => b.n - a.n);
}
