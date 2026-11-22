"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Film,
  Filter,
  Lock,
  Maximize2,
  Minimize2,
  PlayCircle,
  Search,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { useLessonsAccess } from "@/hooks/useLessonsAccess";
import { getThemeUrls } from "@/lib/themeJourney";
import type {
  LessonDetailResponse,
  LessonItem,
  LessonProgressStatus,
  LessonsListResponse,
} from "@/types/api";

type CourseFilter =
  | "medway_r1_2026"
  | "medcof_r1_2026"
  | "radiologia_2026"
  | "medway_pratica_2026"
  | "all";
type StatusFilter = "all" | "pending" | "in_progress" | "completed";
type MedcofGroupMode = "area_tema" | "bloco";

const COURSE_TABS: ReadonlyArray<{ key: CourseFilter; label: string }> = [
  { key: "medway_r1_2026", label: "Extensivo R1" },
  { key: "medcof_r1_2026", label: "MedCof (Extras)" },
  { key: "radiologia_2026", label: "Radiologia" },
  { key: "medway_pratica_2026", label: "Prática / OSCE" },
  { key: "all", label: "Todos" },
];

const VALID_COURSES = new Set<string>(COURSE_TABS.map((t) => t.key));

function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return "";
  const totalMin = Math.max(1, Math.round(seconds / 60));
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${Math.round(mb)} MB`;
}

function formatSecondsToMmSs(sec: number): string {
  if (!sec || sec <= 0) return "";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function parseMmSsToSeconds(value: string): number | null {
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

function normSearch(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function kindBadge(kind: string): { label: string; tone: "accent" | "primary" | "neutral" } | null {
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

export default function LessonsClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { canAccessLessons, isLoading: checkingAccess } = useLessonsAccess();

  const rawParamLesson = Number(searchParams.get("lesson") || 0);
  const paramLessonId = Number.isInteger(rawParamLesson) && rawParamLesson > 0 ? rawParamLesson : null;
  const paramSubtema = searchParams.get("subtema") || "";
  const paramCourse = searchParams.get("course");

  const courseFilter: CourseFilter =
    paramCourse && VALID_COURSES.has(paramCourse)
      ? (paramCourse as CourseFilter)
      : paramSubtema
      ? "all"
      : "medway_r1_2026";

  const [areaFilter, setAreaFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [essentialOnly, setEssentialOnly] = useState<boolean>(false);
  const [onlyCurrentWeek, setOnlyCurrentWeek] = useState<boolean>(false);
  const [medcofGroupMode, setMedcofGroupMode] = useState<MedcofGroupMode>("area_tema");
  const [theaterMode, setTheaterMode] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>("");
  const deferredSearchText = useDeferredValue(searchText);
  const [expandedModules, setExpandedModules] = useState<Record<string, boolean>>({});
  const [draftEdit, setDraftEdit] = useState<{
    lessonId: number;
    bookmark: string;
    notes: string;
  } | null>(null);
  const [savingProgress, setSavingProgress] = useState<boolean>(false);

  // Atalho de teclado T para Modo Teatro
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
        return;
      }
      if (e.key.toLowerCase() === "t" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setTheaterMode((v) => !v);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const { data: currentWeekData } = useQuery({
    queryKey: ["lessons-current-week"],
    queryFn: () => api.lessons.getCurrentWeek(),
    enabled: canAccessLessons,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const currentWeekSubtemasSet = useMemo(
    () => new Set(currentWeekData?.subtemas ?? []),
    [currentWeekData]
  );

  const effectiveCourse: CourseFilter =
    onlyCurrentWeek && (courseFilter === "radiologia_2026" || courseFilter === "medway_pratica_2026")
      ? "all"
      : courseFilter;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["lessons", effectiveCourse, paramSubtema],
    queryFn: () =>
      api.lessons.list({
        course: effectiveCourse,
        subtema: paramSubtema || undefined,
      }),
    enabled: canAccessLessons,
    staleTime: 60_000,
  });

  const allFetchedLessons = useMemo(() => data?.lessons ?? [], [data]);
  const summary = data?.summary;

  const availableAreas = useMemo(() => {
    const set = new Set<string>();
    for (const l of allFetchedLessons) {
      if (l.area) set.add(l.area);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [allFetchedLessons]);

  const searchHaystackById = useMemo(() => {
    const map = new Map<number, string>();
    for (const l of allFetchedLessons) {
      map.set(
        l.id,
        normSearch(`${l.title} ${l.module_name} ${l.subtema || ""} ${l.specialty} ${l.area}`)
      );
    }
    return map;
  }, [allFetchedLessons]);

  const lessons = useMemo(() => {
    const qNorm = normSearch(deferredSearchText);
    return allFetchedLessons.filter((l) => {
      if (areaFilter && l.area !== areaFilter) return false;
      if (essentialOnly && !l.is_essential) return false;
      if (onlyCurrentWeek) {
        if (!l.subtema || !currentWeekSubtemasSet.has(l.subtema)) return false;
      }
      if (statusFilter === "pending") {
        if (l.progress.status === "completed") return false;
      } else if (statusFilter !== "all") {
        if (l.progress.status !== statusFilter) return false;
      }
      if (qNorm) {
        const hay = searchHaystackById.get(l.id) ?? "";
        if (!hay.includes(qNorm)) return false;
      }
      return true;
    });
  }, [
    allFetchedLessons,
    areaFilter,
    essentialOnly,
    onlyCurrentWeek,
    currentWeekSubtemasSet,
    statusFilter,
    deferredSearchText,
    searchHaystackById,
  ]);

  // Aula ativa nunca muda durante digitação/filtro: paramLessonId explícito tem precedência total
  const fallbackActiveLesson = useMemo(() => {
    if (!allFetchedLessons.length) return null;
    const inProg = allFetchedLessons.find((l) => l.progress.status === "in_progress");
    if (inProg) return inProg;
    const firstPending = allFetchedLessons.find((l) => l.progress.status !== "completed");
    return firstPending || allFetchedLessons[0];
  }, [allFetchedLessons]);

  const activeLessonId = paramLessonId ?? fallbackActiveLesson?.id ?? null;

  const {
    data: detailData,
    isError: isExplicitLessonError,
    isLoading: isDetailLoading,
  } = useQuery({
    queryKey: ["lesson-detail", activeLessonId],
    queryFn: () => api.lessons.get(activeLessonId!),
    enabled: Boolean(canAccessLessons && activeLessonId),
    staleTime: 60_000,
    retry: false,
  });

  const listActiveLesson = useMemo(
    () => (activeLessonId ? allFetchedLessons.find((l) => l.id === activeLessonId) ?? null : null),
    [allFetchedLessons, activeLessonId]
  );

  // Se ?lesson=ID veio explícito e deu 404/erro, NÃO substituir silenciosamente por outra aula
  const activeLesson: LessonItem | null =
    paramLessonId && isExplicitLessonError
      ? null
      : detailData?.lesson ?? (paramLessonId ? null : fallbackActiveLesson) ?? listActiveLesson;

  const activePlaylist = useMemo(() => {
    if (detailData?.playlist && detailData.playlist.length > 0 && activeLesson?.id === detailData.lesson.id) {
      return detailData.playlist;
    }
    return null;
  }, [detailData, activeLesson]);

  const bookmarkInput =
    activeLesson && draftEdit?.lessonId === activeLesson.id
      ? draftEdit.bookmark
      : activeLesson
      ? formatSecondsToMmSs(activeLesson.progress.bookmark_seconds)
      : "";
  const notesInput =
    activeLesson && draftEdit?.lessonId === activeLesson.id
      ? draftEdit.notes
      : activeLesson
      ? activeLesson.progress.notes || ""
      : "";

  const groupedModules = useMemo(() => {
    const useMedcofAreaTema = effectiveCourse === "medcof_r1_2026" && medcofGroupMode === "area_tema";
    const sortedSource = useMedcofAreaTema
      ? [...lessons].sort((a, b) => {
          const areaA = a.subtema ? a.area : "ZZZ";
          const areaB = b.subtema ? b.area : "ZZZ";
          if (areaA !== areaB) return areaA.localeCompare(areaB, "pt-BR");
          const subA = a.subtema || "Outros temas MedCof";
          const subB = b.subtema || "Outros temas MedCof";
          if (subA !== subB) return subA.localeCompare(subB, "pt-BR");
          return a.module_order - b.module_order || a.lesson_order - b.lesson_order;
        })
      : lessons;

    const groups: Array<{
      key: string;
      moduleName: string;
      area: string;
      isExtra: boolean;
      items: LessonItem[];
      completedCount: number;
      remainingSeconds: number;
    }> = [];
    const indexByKey = new Map<string, number>();

    for (const item of sortedSource) {
      const groupTitle = useMedcofAreaTema
        ? item.subtema || "Outros temas MedCof"
        : item.module_name;
      const key = useMedcofAreaTema
        ? `medcof-tema::${item.area}::${groupTitle}`
        : `${item.course_key}::${groupTitle}`;

      let idx = indexByKey.get(key);
      if (idx === undefined) {
        idx = groups.length;
        indexByKey.set(key, idx);
        groups.push({
          key,
          moduleName: groupTitle,
          area: item.area,
          isExtra: item.is_extra,
          items: [],
          completedCount: 0,
          remainingSeconds: 0,
        });
      }
      groups[idx].items.push(item);
      if (item.progress.status === "completed") {
        groups[idx].completedCount += 1;
      } else {
        groups[idx].remainingSeconds += item.duration_seconds || 0;
      }
    }
    return groups;
  }, [lessons, effectiveCourse, medcofGroupMode]);

  const flatOrderedLessons = useMemo(
    () => groupedModules.flatMap((g) => g.items),
    [groupedModules]
  );

  // Navegação Anterior/Próxima usa a lista visível se a aula estiver nela; senão usa a playlist do módulo do detalhe
  const navSource = useMemo(() => {
    if (activeLesson && flatOrderedLessons.some((l) => l.id === activeLesson.id)) {
      return flatOrderedLessons;
    }
    return activePlaylist ?? flatOrderedLessons;
  }, [activeLesson, flatOrderedLessons, activePlaylist]);

  const currentIdx = activeLesson ? navSource.findIndex((l) => l.id === activeLesson.id) : -1;
  const prevLesson = currentIdx > 0 ? navSource[currentIdx - 1] : null;
  const nextLesson =
    currentIdx >= 0 && currentIdx < navSource.length - 1 ? navSource[currentIdx + 1] : null;

  const updateUrlParams = (updates: Record<string, string | null>) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === null || v === "") {
        nextParams.delete(k);
      } else {
        nextParams.set(k, v);
      }
    }
    const qs = nextParams.toString();
    router.replace(qs ? `/aulas?${qs}` : "/aulas", { scroll: false });
  };

  const handleSelectLesson = (lesson: LessonItem) => {
    updateUrlParams({ lesson: String(lesson.id) });
  };

  const handleSelectCourseTab = (nextCourse: CourseFilter) => {
    setAreaFilter("");
    if (nextCourse === "radiologia_2026" || nextCourse === "medway_pratica_2026") {
      setOnlyCurrentWeek(false);
    }
    const keepLesson =
      activeLesson && (nextCourse === "all" || activeLesson.course_key === nextCourse)
        ? String(activeLesson.id)
        : null;
    updateUrlParams({ course: nextCourse, lesson: keepLesson });
  };

  const clearSubtemaFilter = () => {
    updateUrlParams({ subtema: null });
  };

  const handleSaveProgress = async (
    targetLesson: LessonItem,
    overrides: {
      status?: LessonProgressStatus;
      bookmark_seconds?: number;
      notes?: string;
    },
    advanceNext?: LessonItem | null
  ) => {
    setSavingProgress(true);
    try {
      const res = await api.lessons.saveProgress(targetLesson.id, overrides);

      // Atualiza listas já em cache sem re-baixar ~1 MB do backend
      queryClient.setQueriesData<LessonsListResponse>({ queryKey: ["lessons"] }, (old) => {
        if (!old) return old;
        let completedDelta = 0;
        const nextLessons = old.lessons.map((item) => {
          if (item.id !== targetLesson.id) return item;
          if (item.progress.status !== "completed" && res.status === "completed") completedDelta = 1;
          if (item.progress.status === "completed" && res.status !== "completed") completedDelta = -1;
          return {
            ...item,
            progress: {
              ...item.progress,
              status: res.status,
              bookmark_seconds: res.bookmark_seconds,
              has_notes: res.has_notes,
              completed_at: res.completed_at,
              updated_at: res.updated_at,
            },
          };
        });
        return {
          ...old,
          lessons: nextLessons,
          summary: {
            ...old.summary,
            completed: Math.max(0, old.summary.completed + completedDelta),
          },
        };
      });

      queryClient.setQueryData<LessonDetailResponse>(["lesson-detail", targetLesson.id], (old) => {
        if (!old) return old;
        const patchProgress = (item: LessonItem): LessonItem =>
          item.id === targetLesson.id
            ? {
                ...item,
                progress: {
                  ...item.progress,
                  status: res.status,
                  bookmark_seconds: res.bookmark_seconds,
                  notes: res.notes,
                  has_notes: res.has_notes,
                  completed_at: res.completed_at,
                  updated_at: res.updated_at,
                },
              }
            : item;
        return {
          lesson: patchProgress(old.lesson),
          playlist: old.playlist.map(patchProgress),
        };
      });

      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["lessons-summary-by-subtema"] }),
        queryClient.invalidateQueries({ queryKey: ["lessons-by-subtema"] }),
        queryClient.invalidateQueries({ queryKey: ["lessons-continue"] }),
        queryClient.invalidateQueries({ queryKey: ["theme-progress"] }),
      ]);

      if (res.theme_theory_completed && targetLesson.subtema) {
        toast.success(`Teoria de "${targetLesson.subtema}" concluída automaticamente!`);
      } else if (overrides.status === "completed") {
        toast.success("Aula marcada como concluída.");
      } else if (overrides.bookmark_seconds !== undefined || overrides.notes !== undefined) {
        toast.success("Anotações e ponto da aula salvos.");
      }
      if (advanceNext) {
        handleSelectLesson(advanceNext);
      }
    } catch {
      toast.error("Não foi possível salvar o progresso da aula.");
    } finally {
      setSavingProgress(false);
    }
  };

  const handleSaveNotesAndBookmark = async () => {
    if (!activeLesson) return;
    const parsedSeconds = parseMmSsToSeconds(bookmarkInput);
    if (parsedSeconds === null) {
      toast.error("Informe o tempo no formato mm:ss (ex: 14:30) ou minutos.");
      return;
    }
    const nextStatus: LessonProgressStatus =
      activeLesson.progress.status === "not_started" && (parsedSeconds > 0 || notesInput.trim().length > 0)
        ? "in_progress"
        : activeLesson.progress.status;
    await handleSaveProgress(activeLesson, {
      status: nextStatus,
      bookmark_seconds: parsedSeconds,
      notes: notesInput,
    });
  };

  if (checkingAccess) {
    return (
      <div className="space-y-4">
        <div className="h-24 rounded-md bg-surface border border-line-subtle animate-pulse" />
        <div className="h-[520px] rounded-md bg-surface border border-line-subtle animate-pulse" />
      </div>
    );
  }

  if (!canAccessLessons) {
    return (
      <div className="max-w-lg mx-auto my-12 rounded-md border border-line-subtle bg-surface p-8 text-center space-y-3 shadow-sm">
        <div className="w-11 h-11 rounded-full bg-elevated border border-line-subtle flex items-center justify-center mx-auto text-ink-muted">
          <Lock className="w-5 h-5" />
        </div>
        <h1 className="text-lg font-bold text-ink-primary">Área privada de aulas</h1>
        <p className="text-xs text-ink-secondary leading-relaxed">
          Esta videoteca é restrita à conta autorizada do proprietário. Faça login com a conta permitida para acessar suas aulas.
        </p>
        <div className="pt-2">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors"
          >
            Voltar ao Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const themeUrls = activeLesson?.subtema ? getThemeUrls(activeLesson.subtema) : null;
  const totalRemainingFormatted = formatDuration(
    lessons.reduce((acc, l) => acc + (l.progress.status === "completed" ? 0 : l.duration_seconds || 0), 0)
  );
  const completedCount = lessons.filter((l) => l.progress.status === "completed").length;
  const playerPreviewUrl = activeLesson
    ? activeLesson.preview_url || `https://drive.google.com/file/d/${activeLesson.drive_file_id}/preview`
    : "";
  const playerOpenUrl = activeLesson
    ? activeLesson.open_url || `https://drive.google.com/file/d/${activeLesson.drive_file_id}/view`
    : "";

  return (
    <div className="flex flex-col gap-5">
      {/* Header & Filtros */}
      <section className="rounded-md border border-line-subtle bg-surface p-4 sm:p-5 space-y-4">
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <PlayCircle className="w-5 h-5 text-accent" />
              <h1 className="text-lg sm:text-xl font-bold text-ink-primary tracking-tight">
                Videoteca de Aulas
              </h1>
              {summary && (
                <span className="text-xs font-mono-lab px-2 py-0.5 rounded-xs bg-elevated text-ink-secondary border border-line-subtle">
                  {completedCount}/{lessons.length} concluídas
                  {totalRemainingFormatted ? ` • ${totalRemainingFormatted} restantes` : ""}
                </span>
              )}
            </div>
            <p className="text-xs text-ink-secondary mt-1">
              Extensivo R1 (Medway) integrado aos 170 subtemas + MedCof, Radiologia e Prática/OSCE.
            </p>
          </div>

          {/* Abas de Curso */}
          <div className="inline-flex flex-wrap gap-1 bg-canvas p-1 rounded-md border border-line-subtle self-start">
            {COURSE_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => handleSelectCourseTab(tab.key)}
                className={clsx(
                  "px-2.5 py-1.5 rounded-xs text-xs font-semibold transition-colors cursor-pointer",
                  effectiveCourse === tab.key
                    ? "bg-primary text-primary-foreground shadow-2xs"
                    : "text-ink-secondary hover:text-ink-primary hover:bg-elevated"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Barra de Busca e Filtros Secundários */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-3.5 h-3.5 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Buscar aula, módulo ou subtema..."
              className="w-full pl-8 pr-8 py-2 rounded-md border border-line-subtle bg-canvas text-xs text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent"
            />
            {searchText && (
              <button
                type="button"
                onClick={() => setSearchText("")}
                aria-label="Limpar busca"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <select
            value={areaFilter}
            onChange={(e) => setAreaFilter(e.target.value)}
            aria-label="Filtrar por grande área"
            className="px-3 py-2 rounded-md border border-line-subtle bg-canvas text-xs text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <option value="">Todas as áreas</option>
            {availableAreas.map((area) => (
              <option key={area} value={area}>
                {area}
              </option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            aria-label="Filtrar por status"
            className="px-3 py-2 rounded-md border border-line-subtle bg-canvas text-xs text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <option value="all">Todos os status</option>
            <option value="pending">Pendentes</option>
            <option value="in_progress">Em andamento</option>
            <option value="completed">Concluídas</option>
          </select>

          <button
            type="button"
            onClick={() => setEssentialOnly((v) => !v)}
            aria-pressed={essentialOnly}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-2 rounded-md border text-xs font-semibold transition-colors cursor-pointer",
              essentialOnly
                ? "bg-accent/15 text-accent border-accent/40"
                : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary"
            )}
          >
            <Filter className="w-3.5 h-3.5" />
            {essentialOnly ? "Só principais" : "Todas (c/ Flash)"}
          </button>

          {currentWeekData && currentWeekData.week !== null && (
            <button
              type="button"
              onClick={() => setOnlyCurrentWeek((v) => !v)}
              aria-pressed={onlyCurrentWeek}
              className={clsx(
                "inline-flex items-center gap-1.5 px-3 py-2 rounded-md border text-xs font-semibold transition-colors cursor-pointer",
                onlyCurrentWeek
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary"
              )}
            >
              <Calendar className="w-3.5 h-3.5" />
              Semana {currentWeekData.week} (Planner)
            </button>
          )}

          {effectiveCourse === "medcof_r1_2026" && (
            <div className="inline-flex rounded-md border border-line-subtle bg-canvas p-0.5">
              {(
                [
                  { key: "area_tema", label: "Por Área/Tema" },
                  { key: "bloco", label: "Por Bloco" },
                ] as const
              ).map((m) => (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setMedcofGroupMode(m.key)}
                  className={clsx(
                    "px-2.5 py-1.5 rounded-xs text-[11px] font-semibold transition-colors cursor-pointer",
                    medcofGroupMode === m.key
                      ? "bg-elevated text-ink-primary shadow-2xs"
                      : "text-ink-muted hover:text-ink-primary"
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {paramSubtema && (
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-md bg-accent/10 border border-accent/25 text-xs">
            <div className="flex items-center gap-2 min-w-0">
              <BookOpen className="w-3.5 h-3.5 text-accent shrink-0" />
              <span className="text-ink-secondary">Filtrando pelo tema:</span>
              <span className="font-semibold text-ink-primary truncate">{paramSubtema}</span>
            </div>
            <button
              type="button"
              onClick={clearSubtemaFilter}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-xs bg-surface border border-line-subtle text-ink-secondary hover:text-ink-primary cursor-pointer"
            >
              <X className="w-3 h-3" /> Ver catálogo completo
            </button>
          </div>
        )}
      </section>

      {/* Main Split View: Player + Playlist */}
      <div
        className={clsx(
          "grid grid-cols-1 gap-5 items-start",
          !theaterMode && "lg:grid-cols-[minmax(0,1fr)_390px]"
        )}
      >
        {/* Player & Estudo */}
        <section className="rounded-md border border-line-subtle bg-surface overflow-hidden flex flex-col">
          {paramLessonId && isExplicitLessonError ? (
            <div className="p-10 text-center space-y-3">
              <Film className="w-8 h-8 text-warning mx-auto" />
              <p className="text-sm font-semibold text-ink-primary">
                Aula #{paramLessonId} não encontrada ou indisponível.
              </p>
              <button
                type="button"
                onClick={() => updateUrlParams({ lesson: null })}
                className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold cursor-pointer"
              >
                Abrir aula sugerida
              </button>
            </div>
          ) : isLoading || (paramLessonId && isDetailLoading && !activeLesson) ? (
            <div className="p-6 space-y-4">
              <div className="aspect-video w-full rounded-md bg-elevated animate-pulse" />
              <div className="h-24 rounded-md bg-elevated animate-pulse" />
            </div>
          ) : isError ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-sm font-semibold text-ink-primary">Erro ao carregar catálogo de aulas.</p>
              <button
                type="button"
                onClick={() => void refetch()}
                className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold cursor-pointer"
              >
                Tentar novamente
              </button>
            </div>
          ) : !activeLesson ? (
            <div className="p-10 text-center space-y-2">
              <Film className="w-8 h-8 text-ink-muted mx-auto" />
              <p className="text-sm font-semibold text-ink-primary">Nenhuma aula encontrada.</p>
              <p className="text-xs text-ink-secondary">
                {onlyCurrentWeek
                  ? "Sua semana atual do Planner não possui temas com aulas neste filtro."
                  : "Ajuste a busca, troque a aba do curso ou limpe os filtros."}
              </p>
            </div>
          ) : (
            <>
              {/* Player Embed Google Drive */}
              <div className="relative w-full aspect-video bg-black">
                <iframe
                  key={activeLesson.drive_file_id}
                  src={playerPreviewUrl}
                  title={activeLesson.title}
                  allow="autoplay; fullscreen"
                  allowFullScreen
                  className="w-full h-full border-0"
                />
              </div>

              {/* Meta + Controles da Aula */}
              <div className="p-4 sm:p-5 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-line-subtle pb-4">
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      <span className="px-2 py-0.5 rounded-xs bg-elevated text-ink-secondary border border-line-subtle font-semibold">
                        {activeLesson.course_name}
                      </span>
                      <span className="px-2 py-0.5 rounded-xs bg-elevated text-ink-secondary border border-line-subtle">
                        {activeLesson.area}
                      </span>
                      {(() => {
                        const badge = kindBadge(activeLesson.lesson_kind);
                        if (!badge) return null;
                        return (
                          <span
                            className={clsx(
                              "px-2 py-0.5 rounded-xs border font-semibold",
                              badge.tone === "accent"
                                ? "bg-accent/10 text-accent border-accent/25"
                                : badge.tone === "primary"
                                ? "bg-primary/10 text-primary border-primary/25"
                                : "bg-elevated text-ink-secondary border-line-subtle"
                            )}
                          >
                            {badge.label}
                          </span>
                        );
                      })()}
                      {activeLesson.duration_seconds ? (
                        <span className="font-mono-lab text-ink-secondary">
                          {formatDuration(activeLesson.duration_seconds)}
                        </span>
                      ) : activeLesson.size_bytes && activeLesson.size_bytes > 0 ? (
                        <span className="font-mono-lab text-ink-muted">
                          {formatSize(activeLesson.size_bytes)}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="text-base sm:text-lg font-bold text-ink-primary leading-snug break-words">
                      {activeLesson.title}
                    </h2>
                    <p className="text-xs text-ink-secondary">
                      Módulo: <span className="font-medium text-ink-primary">{activeLesson.module_name}</span>
                      {activeLesson.subtema && (
                        <>
                          {" • "}Tema canônico:{" "}
                          <Link
                            href={`/analise?tab=cobertura&subtema=${encodeURIComponent(activeLesson.subtema)}`}
                            className="text-accent hover:underline font-medium"
                          >
                            {activeLesson.subtema}
                          </Link>
                        </>
                      )}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => setTheaterMode((v) => !v)}
                      title="Alternar Modo Teatro (atalho: T)"
                      className="hidden lg:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-line-subtle bg-canvas hover:bg-elevated text-xs font-medium text-ink-primary transition-colors cursor-pointer"
                    >
                      {theaterMode ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                      {theaterMode ? "Sair Teatro" : "Modo Teatro"}
                    </button>
                    <a
                      href={playerOpenUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-line-subtle bg-canvas hover:bg-elevated text-xs font-medium text-ink-primary transition-colors"
                    >
                      Abrir no Drive <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>

                {/* Barra de Status + Navegação Anterior/Próxima */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {(
                      [
                        { key: "not_started", label: "Não iniciada" },
                        { key: "in_progress", label: "Em andamento" },
                        { key: "completed", label: "Concluída" },
                      ] as const
                    ).map((st) => {
                      const active = activeLesson.progress.status === st.key;
                      return (
                        <button
                          key={st.key}
                          type="button"
                          disabled={savingProgress}
                          onClick={() => void handleSaveProgress(activeLesson, { status: st.key })}
                          className={clsx(
                            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors cursor-pointer",
                            active && st.key === "completed"
                              ? "bg-success/15 text-success border-success/40"
                              : active && st.key === "in_progress"
                              ? "bg-warning/15 text-warning border-warning/40"
                              : active
                              ? "bg-primary text-primary-foreground border-primary"
                              : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary"
                          )}
                        >
                          {st.key === "completed" && <CheckCircle2 className="w-3.5 h-3.5" />}
                          {st.label}
                        </button>
                      );
                    })}

                    {nextLesson && (
                      <button
                        type="button"
                        disabled={savingProgress}
                        onClick={() =>
                          void handleSaveProgress(activeLesson, { status: "completed" }, nextLesson)
                        }
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-success text-white hover:opacity-90 text-xs font-semibold transition-opacity cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Concluir e próxima →
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={!prevLesson}
                      onClick={() => prevLesson && handleSelectLesson(prevLesson)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-line-subtle bg-canvas text-xs font-medium text-ink-primary hover:bg-elevated disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                    >
                      <ArrowLeft className="w-3.5 h-3.5" /> Anterior
                    </button>
                    <button
                      type="button"
                      disabled={!nextLesson}
                      onClick={() => nextLesson && handleSelectLesson(nextLesson)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-line-subtle bg-canvas text-xs font-medium text-ink-primary hover:bg-elevated disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                    >
                      Próxima <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Bookmark manual (mm:ss) + Anotações */}
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
                        onChange={(e) =>
                          setDraftEdit({
                            lessonId: activeLesson.id,
                            bookmark: e.target.value,
                            notes: notesInput,
                          })
                        }
                        placeholder="ex: 24:15"
                        className="w-24 px-2.5 py-1 rounded-xs border border-line-subtle bg-surface text-xs font-mono-lab text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <button
                      type="button"
                      disabled={savingProgress}
                      onClick={() => void handleSaveNotesAndBookmark()}
                      className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors cursor-pointer self-start sm:self-auto"
                    >
                      Salvar ponto e anotações
                    </button>
                  </div>
                  <textarea
                    value={notesInput}
                    onChange={(e) =>
                      setDraftEdit({
                        lessonId: activeLesson.id,
                        bookmark: bookmarkInput,
                        notes: e.target.value,
                      })
                    }
                    rows={3}
                    placeholder="Anote pontos-chave da aula, pegadinhas de prova ou dúvidas para revisar..."
                    className="w-full px-3 py-2 rounded-md border border-line-subtle bg-surface text-xs text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent resize-y"
                  />
                </div>

                {/* Ponte direta para Questões do Tema */}
                {themeUrls && activeLesson.subtema && (
                  <div className="rounded-md border border-primary/25 bg-primary/5 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-primary" /> Fechar o ciclo: Aula → Questões
                      </p>
                      <p className="text-xs text-ink-secondary mt-0.5">
                        Fixe &ldquo;{activeLesson.subtema}&rdquo; direto com bateria adaptativa no FSRS.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      <Link
                        href={themeUrls.practice(10)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors"
                      >
                        <Zap className="w-3.5 h-3.5" /> Treinar 10q
                      </Link>
                      <Link
                        href={themeUrls.practice(20)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-primary/30 bg-surface hover:bg-elevated text-primary text-xs font-semibold transition-colors"
                      >
                        Treinar 20q
                      </Link>
                      <Link
                        href={`/analise?tab=cobertura&subtema=${encodeURIComponent(activeLesson.subtema)}`}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-line-subtle bg-surface hover:bg-elevated text-ink-secondary text-xs font-medium transition-colors"
                      >
                        Análise
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        {/* Playlist lateral agrupada por módulo (recolhida por padrão para performance) */}
        <aside
          className={clsx(
            "rounded-md border border-line-subtle bg-surface overflow-hidden flex flex-col",
            !theaterMode && "lg:max-h-[calc(100vh-12rem)]"
          )}
        >
          <div className="px-4 py-3 border-b border-line-subtle flex items-center justify-between bg-canvas/60">
            <span className="text-xs font-bold uppercase tracking-wider text-ink-secondary">
              Módulos e Aulas ({lessons.length})
            </span>
            <span className="text-[11px] font-mono-lab text-ink-muted">
              {groupedModules.length} grupos
            </span>
          </div>

          <div className="overflow-y-auto divide-y divide-line-subtle">
            {groupedModules.length === 0 ? (
              <div className="p-6 text-center text-xs text-ink-secondary">
                {onlyCurrentWeek
                  ? "Nenhuma aula vinculada aos subtemas desta semana do Planner."
                  : "Nenhuma aula corresponde aos filtros selecionados."}
              </div>
            ) : (
              groupedModules.map((group) => {
                const containsActive = Boolean(activeLesson && group.items.some((i) => i.id === activeLesson.id));
                const forceExpanded =
                  Boolean(paramSubtema) ||
                  onlyCurrentWeek ||
                  deferredSearchText.trim().length >= 2 ||
                  groupedModules.length <= 3;
                const isExpanded =
                  expandedModules[group.key] !== undefined
                    ? expandedModules[group.key]
                    : containsActive || forceExpanded;
                const remDur = formatDuration(group.remainingSeconds);

                return (
                  <div key={group.key} className="flex flex-col">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedModules((prev) => ({
                          ...prev,
                          [group.key]: !isExpanded,
                        }))
                      }
                      className={clsx(
                        "w-full px-3.5 py-2.5 text-left flex items-start justify-between gap-2 hover:bg-elevated/60 transition-colors cursor-pointer",
                        containsActive && "bg-accent/5"
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-[10px] font-medium text-ink-muted">
                          <span>{group.area}</span>
                          {group.isExtra && (
                            <span className="px-1.5 py-0.2 rounded-xs bg-elevated text-ink-secondary">
                              Extra
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-semibold text-ink-primary leading-snug break-words mt-0.5">
                          {group.moduleName}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                        <span className="text-[11px] font-mono-lab text-ink-secondary text-right">
                          {group.completedCount}/{group.items.length}
                          {remDur ? ` • ${remDur}` : ""}
                        </span>
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-ink-muted" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-ink-muted" />
                        )}
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="bg-canvas/40 divide-y divide-line-subtle/60 border-t border-line-subtle/60">
                        {group.items.map((item) => {
                          const isActive = activeLesson?.id === item.id;
                          const isDone = item.progress.status === "completed";
                          const isInProg = item.progress.status === "in_progress";
                          const badge = kindBadge(item.lesson_kind);
                          const durLabel = formatDuration(item.duration_seconds);
                          return (
                            <div
                              key={item.id}
                              className={clsx(
                                "flex items-start gap-2 px-3.5 py-2 transition-colors",
                                isActive ? "bg-accent/10 border-l-2 border-accent" : "hover:bg-elevated/50"
                              )}
                            >
                              <button
                                type="button"
                                title={isDone ? "Desmarcar conclusão" : "Marcar aula concluída"}
                                disabled={savingProgress}
                                onClick={() =>
                                  void handleSaveProgress(item, {
                                    status: isDone ? "not_started" : "completed",
                                  })
                                }
                                className={clsx(
                                  "mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center shrink-0 cursor-pointer transition-colors",
                                  isDone
                                    ? "bg-success border-success text-white"
                                    : isInProg
                                    ? "border-warning text-warning"
                                    : "border-line-subtle hover:border-accent"
                                )}
                              >
                                {isDone && <CheckCircle2 className="w-3 h-3" />}
                              </button>

                              <button
                                type="button"
                                onClick={() => handleSelectLesson(item)}
                                className="flex-1 min-w-0 text-left cursor-pointer"
                              >
                                <p
                                  className={clsx(
                                    "text-xs leading-snug break-words",
                                    isActive
                                      ? "font-semibold text-accent"
                                      : isDone
                                      ? "text-ink-muted line-through"
                                      : "text-ink-primary"
                                  )}
                                >
                                  {item.title}
                                </p>
                                <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px] text-ink-muted">
                                  {badge && (
                                    <span
                                      className={clsx(
                                        "px-1.5 py-0.2 rounded-xs border",
                                        badge.tone === "accent"
                                          ? "bg-accent/10 text-accent border-accent/25"
                                          : badge.tone === "primary"
                                          ? "bg-primary/10 text-primary border-primary/25"
                                          : "bg-elevated border-line-subtle text-ink-secondary"
                                      )}
                                    >
                                      {badge.label}
                                    </span>
                                  )}
                                  {item.progress.bookmark_seconds > 0 && (
                                    <span className="font-mono-lab text-warning">
                                      ⏱ {formatSecondsToMmSs(item.progress.bookmark_seconds)}
                                    </span>
                                  )}
                                  {durLabel ? (
                                    <span className="font-mono-lab">{durLabel}</span>
                                  ) : item.size_bytes && item.size_bytes > 0 ? (
                                    <span className="font-mono-lab">{formatSize(item.size_bytes)}</span>
                                  ) : null}
                                </div>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
