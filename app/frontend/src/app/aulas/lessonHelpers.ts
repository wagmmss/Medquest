import type { LessonItem } from "@/types/api";

export type ViewTab =
  | "trilha_r1"
  | "medway_pratica_2026"
  | "radiologia_2026"
  | "medcof_r1_2026";

export type StatusFilter = "all" | "pending" | "in_progress" | "completed";
export type MedcofGroupMode = "area_tema" | "bloco";
export type AreaPill = "current_week" | "all" | string;

export const VIEW_TABS: ReadonlyArray<{ key: ViewTab; label: string }> = [
  { key: "trilha_r1", label: "Trilha R1" },
  { key: "medway_pratica_2026", label: "Prática / OSCE" },
  { key: "radiologia_2026", label: "Radiologia" },
  { key: "medcof_r1_2026", label: "Acervo MedCof" },
];

export const AREA_ORDER: Record<string, number> = {
  "Clínica Médica": 1,
  Cirurgia: 2,
  "Ginecologia e Obstetrícia": 3,
  Pediatria: 4,
  Preventiva: 5,
};

export function getShortAreaLabel(area: string): string {
  if (area === "Ginecologia e Obstetrícia") return "GO";
  return area;
}

export function getAreaDotClass(area: string): string {
  const name = area.toLowerCase();
  if (name.includes("preventiva")) return "bg-area-preventiva";
  if (name.includes("pediatria")) return "bg-area-pediatria";
  if (name.includes("go") || name.includes("ginecologia")) return "bg-area-go";
  if (name.includes("cirurgia")) return "bg-area-cirurgia";
  return "bg-area-clinica";
}

export function resolveViewTab(rawCourse: string | null): ViewTab {
  if (
    rawCourse === "medway_pratica_2026" ||
    rawCourse === "radiologia_2026" ||
    rawCourse === "medcof_r1_2026"
  ) {
    return rawCourse;
  }
  return "trilha_r1";
}

export function isMedwayMain(lesson: LessonItem): boolean {
  return lesson.course_key === "medway_r1_2026" && lesson.is_essential;
}

export function isMedwayOptional(lesson: LessonItem): boolean {
  return lesson.course_key === "medway_r1_2026" && !lesson.is_essential;
}

export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return "";
  const totalMin = Math.max(1, Math.round(seconds / 60));
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${Math.round(mb)} MB`;
}

export function formatSecondsToMmSs(sec: number): string {
  if (!sec || sec <= 0) return "";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function parseMmSsToSeconds(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return 0;
  if (/^\d+$/.test(trimmed)) {
    const mins = Number(trimmed);
    return Number.isFinite(mins) && mins >= 0 ? Math.min(86400, mins * 60) : null;
  }
  const parts = trimmed.split(":");
  if (parts.length === 2 || parts.length === 3) {
    const nums = parts.map((p) => Number(p));
    if (nums.some((n) => !Number.isInteger(n) || n < 0)) return null;
    if (parts.length === 2) {
      const [m, s] = nums;
      if (s >= 60) return null;
      return Math.min(86400, m * 60 + s);
    }
    const [h, m, s] = nums;
    if (m >= 60 || s >= 60) return null;
    return Math.min(86400, h * 3600 + m * 60 + s);
  }
  return null;
}

export function normSearch(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function kindBadge(
  kind: string
): { label: string; tone: "accent" | "primary" | "neutral" } | null {
  switch (kind) {
    case "cofexpress":
      return { label: "CofExpress", tone: "accent" };
    case "aula_extra":
      return { label: "Completa", tone: "primary" };
    case "flash":
      return { label: "Flash", tone: "accent" };
    case "revisao":
      return { label: "Revisão", tone: "neutral" };
    case "como_cai":
      return { label: "Como cai", tone: "neutral" };
    case "radiologia":
      return { label: "Radiologia", tone: "primary" };
    case "pratica":
      return { label: "Prática", tone: "primary" };
    case "extra":
      return { label: "MedCof", tone: "neutral" };
    default:
      return null;
  }
}

export interface SubtemaGroup {
  subtema: string;
  area: string;
  isCurrentWeek: boolean;
  mainLessons: LessonItem[];
  optionalMedwayLessons: LessonItem[];
  extraMedcofLessons: LessonItem[];
  mainTotal: number;
  mainCompleted: number;
  mainRemainingSeconds: number;
  hasSecondaryMatch: boolean;
}
