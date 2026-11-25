"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Film,
  Lock,
  Maximize2,
  Minimize2,
  Play,
  PlayCircle,
  Sparkles,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import { LessonNotesEditor } from "./components/LessonNotesEditor";
import { useLessonsAccess } from "@/hooks/useLessonsAccess";
import {
  buildLessonCycleQuizUrl,
  DEFAULT_LESSON_POST_QUESTIONS,
  DEFAULT_LESSON_PRE_QUESTIONS,
} from "@/lib/themeJourney";
import type {
  LessonCyclePhase,
  LessonCycleResponse,
  LessonDetailResponse,
  LessonItem,
  LessonProgressStatus,
  LessonsListResponse,
  LessonStudyCycle,
} from "@/types/api";
import {
  type AreaPill,
  type MedcofGroupMode,
  type StatusFilter,
  type SubtemaGroup,
  type ViewTab,
  AREA_ORDER,
  formatDuration,
  formatSecondsToMmSs,
  formatSize,
  getAreaDotClass,
  getShortAreaLabel,
  isMedwayMain,
  isMedwayOptional,
  kindBadge,
  normSearch,
  parseMmSsToSeconds,
  resolveViewTab,
} from "./lessonHelpers";
import { LessonRowCompact } from "./components/LessonRowCompact";
import { LessonsHeader, type AreaPillStat } from "./components/LessonsHeader";
import { SubtemaRow } from "./components/SubtemaRow";

export default function LessonsClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { canAccessLessons, isLoading: checkingAccess } = useLessonsAccess();

  const rawParamLesson = Number(searchParams.get("lesson") || 0);
  const paramLessonId = Number.isInteger(rawParamLesson) && rawParamLesson > 0 ? rawParamLesson : null;
  const paramSubtema = searchParams.get("subtema") || "";
  const paramCourse = searchParams.get("course");

  const activeTab: ViewTab = resolveViewTab(paramCourse);
  const isClassroomMode = paramLessonId !== null;

  const [selectedAreaPill, setSelectedAreaPill] = useState<AreaPill | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [medcofGroupMode, setMedcofGroupMode] = useState<MedcofGroupMode>("area_tema");
  const [theaterMode, setTheaterMode] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>("");
  const deferredSearchText = useDeferredValue(searchText);

  const [expandedSubtemas, setExpandedSubtemas] = useState<Record<string, boolean>>({});
  const [expandedComplements, setExpandedComplements] = useState<Record<string, boolean>>({});
  const [expandedModules, setExpandedModules] = useState<Record<string, boolean>>({});
  const [showSidebarMain, setShowSidebarMain] = useState<boolean>(true);
  const [showSidebarOptional, setShowSidebarOptional] = useState<boolean>(true);
  const [showSidebarExtras, setShowSidebarExtras] = useState<boolean>(false);

  const [draftEdit, setDraftEdit] = useState<{
    lessonId: number;
    bookmark: string;
    notes: string;
  } | null>(null);
  const [savingProgress, setSavingProgress] = useState<boolean>(false);
  const [savingCycle, setSavingCycle] = useState<boolean>(false);
  const [showCycleSettings, setShowCycleSettings] = useState<boolean>(false);
  const [draftCyclePre, setDraftCyclePre] = useState<string>("");
  const [draftCyclePost, setDraftCyclePost] = useState<string>("");
  const [forceDriveEmbed, setForceDriveEmbed] = useState<boolean>(false);
  const [failedStreamLessonId, setFailedStreamLessonId] = useState<number | null>(null);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const seekAppliedForLessonRef = useRef<number | null>(null);
  const lastAutoSavedRef = useRef<{ lessonId: number; seconds: number }>({
    lessonId: 0,
    seconds: 0,
  });

  // Atalho de teclado T para Modo Teatro no Modo Sala de Aula
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isClassroomMode) return;
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
  }, [isClassroomMode]);

  const { data: currentWeekData } = useQuery({
    queryKey: ["lessons-current-week"],
    queryFn: () => api.lessons.getCurrentWeek(),
    enabled: canAccessLessons,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const { data: continueData } = useQuery({
    queryKey: ["lessons-continue"],
    queryFn: () => api.lessons.getContinue(),
    enabled: canAccessLessons,
    staleTime: 60_000,
    retry: false,
  });

  const { data: cycleData } = useQuery({
    queryKey: ["lessons-cycle"],
    queryFn: () => api.lessons.getCycle(),
    enabled: canAccessLessons,
    staleTime: 60_000,
    retry: false,
  });

  const defaultPreQuestions =
    cycleData?.settings?.default_pre_questions ?? DEFAULT_LESSON_PRE_QUESTIONS;
  const defaultPostQuestions =
    cycleData?.settings?.default_post_questions ?? DEFAULT_LESSON_POST_QUESTIONS;
  const cyclesBySubtema = useMemo<Record<string, LessonStudyCycle>>(
    () => cycleData?.cycles ?? {},
    [cycleData]
  );

  const currentWeekSubtemasSet = useMemo(
    () => new Set(currentWeekData?.subtemas ?? []),
    [currentWeekData]
  );

  const apiCourseQuery = activeTab === "trilha_r1" ? "all" : activeTab;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["lessons", apiCourseQuery, paramSubtema],
    queryFn: () =>
      api.lessons.list({
        course: apiCourseQuery,
        subtema: paramSubtema || undefined,
      }),
    enabled: canAccessLessons && !isClassroomMode,
    staleTime: 60_000,
  });

  const allFetchedLessons = useMemo(() => data?.lessons ?? [], [data]);

  // Escopo da aba atual (na Trilha R1 ficam Medway R1 + MedCof vinculados a subtemas canônicos)
  const scopedLessons = useMemo(() => {
    if (activeTab !== "trilha_r1") return allFetchedLessons;
    return allFetchedLessons.filter((l) => {
      if (paramSubtema) return l.subtema === paramSubtema;
      return Boolean(l.subtema) && (l.course_key === "medway_r1_2026" || l.course_key === "medcof_r1_2026");
    });
  }, [allFetchedLessons, activeTab, paramSubtema]);

  const areaPillStats = useMemo<AreaPillStat[]>(() => {
    const map = new Map<string, { completed: number; total: number }>();
    for (const l of scopedLessons) {
      if (!l.area) continue;
      const entry = map.get(l.area) ?? { completed: 0, total: 0 };
      if (activeTab === "trilha_r1") {
        if (isMedwayMain(l)) {
          entry.total += 1;
          if (l.progress.status === "completed") entry.completed += 1;
        }
      } else {
        entry.total += 1;
        if (l.progress.status === "completed") entry.completed += 1;
      }
      map.set(l.area, entry);
    }
    return Array.from(map.entries())
      .map(([area, st]) => ({ area, ...st }))
      .sort(
        (a, b) =>
          (AREA_ORDER[a.area] ?? 99) - (AREA_ORDER[b.area] ?? 99) ||
          a.area.localeCompare(b.area, "pt-BR")
      );
  }, [scopedLessons, activeTab]);

  // Métrica rápida da Semana Atual do Planner (apenas Principais Medway)
  const currentWeekMainStats = useMemo(() => {
    if (!currentWeekSubtemasSet.size) return { total: 0, completed: 0, remainingSeconds: 0, hasAnySubtema: false };
    let total = 0;
    let completed = 0;
    let remainingSeconds = 0;
    let hasAnySubtema = false;
    for (const l of scopedLessons) {
      if (!l.subtema || !currentWeekSubtemasSet.has(l.subtema)) continue;
      hasAnySubtema = true;
      if (!isMedwayMain(l)) continue;
      total += 1;
      if (l.progress.status === "completed") {
        completed += 1;
      } else {
        remainingSeconds += l.duration_seconds || 0;
      }
    }
    return { total, completed, remainingSeconds, hasAnySubtema };
  }, [scopedLessons, currentWeekSubtemasSet]);

  const effectiveAreaPill = useMemo<AreaPill>(() => {
    if (activeTab !== "trilha_r1") {
      if (
        selectedAreaPill &&
        (selectedAreaPill === "all" || areaPillStats.some((a) => a.area === selectedAreaPill))
      ) {
        return selectedAreaPill;
      }
      return "all";
    }
    if (selectedAreaPill !== null) {
      if (
        selectedAreaPill === "all" ||
        selectedAreaPill === "current_week" ||
        areaPillStats.some((a) => a.area === selectedAreaPill)
      ) {
        return selectedAreaPill;
      }
    }
    if (
      currentWeekData &&
      currentWeekData.week !== null &&
      currentWeekMainStats.hasAnySubtema
    ) {
      return "current_week";
    }
    return areaPillStats[0]?.area ?? "all";
  }, [
    activeTab,
    selectedAreaPill,
    areaPillStats,
    currentWeekData,
    currentWeekMainStats.hasAnySubtema,
  ]);

  const searchHaystackById = useMemo(() => {
    const map = new Map<number, string>();
    for (const l of scopedLessons) {
      map.set(
        l.id,
        normSearch(`${l.title} ${l.module_name} ${l.subtema || ""} ${l.specialty} ${l.area}`)
      );
    }
    return map;
  }, [scopedLessons]);

  const hasSearch = normSearch(deferredSearchText).length > 0;

  // Para as abas fora da Trilha R1, mantém filtro por aula
  const filteredModuleLessons = useMemo(() => {
    if (activeTab === "trilha_r1") return [];
    const qNorm = normSearch(deferredSearchText);
    return scopedLessons.filter((l) => {
      if (!qNorm && effectiveAreaPill !== "all" && l.area !== effectiveAreaPill) {
        return false;
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
    activeTab,
    scopedLessons,
    effectiveAreaPill,
    statusFilter,
    deferredSearchText,
    searchHaystackById,
  ]);

  // Agrupamento da aba Trilha R1: Subtemas Canônicos (busca sempre global, pílula controla área/semana)
  const trilhaGroups = useMemo(() => {
    if (activeTab !== "trilha_r1") {
      return {
        allSubtemas: [] as SubtemaGroup[],
        byArea: [] as Array<{
          area: string;
          subtemas: SubtemaGroup[];
          mainTotal: number;
          mainCompleted: number;
          mainRemainingSeconds: number;
        }>,
      };
    }

    const qNorm = normSearch(deferredSearchText);
    const bySubtema = new Map<string, SubtemaGroup>();

    for (const l of scopedLessons) {
      if (!paramSubtema && !qNorm) {
        if (effectiveAreaPill === "current_week") {
          if (!l.subtema || !currentWeekSubtemasSet.has(l.subtema)) continue;
        } else if (effectiveAreaPill !== "all") {
          if (l.area !== effectiveAreaPill) continue;
        }
      }

      const sub = l.subtema || "Outros temas";
      let group = bySubtema.get(sub);
      if (!group) {
        group = {
          subtema: sub,
          area: l.area || "Outros",
          isCurrentWeek: currentWeekSubtemasSet.has(sub),
          mainLessons: [],
          optionalMedwayLessons: [],
          extraMedcofLessons: [],
          mainTotal: 0,
          mainCompleted: 0,
          mainRemainingSeconds: 0,
          hasSecondaryMatch: false,
        };
        bySubtema.set(sub, group);
      }

      if (isMedwayMain(l)) {
        group.mainLessons.push(l);
        group.mainTotal += 1;
        if (l.progress.status === "completed") {
          group.mainCompleted += 1;
        } else {
          group.mainRemainingSeconds += l.duration_seconds || 0;
        }
      } else if (isMedwayOptional(l)) {
        group.optionalMedwayLessons.push(l);
      } else {
        group.extraMedcofLessons.push(l);
      }
    }

    // Aplica busca e filtro de status no nível de subtema (preservando contagens reais de principais)
    const filteredSubtemas: SubtemaGroup[] = [];
    for (const group of bySubtema.values()) {
      const allLessons = [
        ...group.mainLessons,
        ...group.optionalMedwayLessons,
        ...group.extraMedcofLessons,
      ];

      if (qNorm) {
        const subtemaMatches = normSearch(`${group.subtema} ${group.area}`).includes(qNorm);
        const mainMatches = group.mainLessons.some((l) =>
          (searchHaystackById.get(l.id) ?? "").includes(qNorm)
        );
        const secondaryMatches =
          group.optionalMedwayLessons.some((l) =>
            (searchHaystackById.get(l.id) ?? "").includes(qNorm)
          ) ||
          group.extraMedcofLessons.some((l) =>
            (searchHaystackById.get(l.id) ?? "").includes(qNorm)
          );

        if (!subtemaMatches && !mainMatches && !secondaryMatches) continue;
        if (secondaryMatches && !mainMatches && !subtemaMatches) {
          group.hasSecondaryMatch = true;
        }
      }

      if (statusFilter !== "all") {
        const hasMain = group.mainTotal > 0;
        const isAllCompleted = hasMain
          ? group.mainCompleted >= group.mainTotal
          : allLessons.length > 0 && allLessons.every((l) => l.progress.status === "completed");
        const hasInProgress = allLessons.some((l) => l.progress.status === "in_progress") ||
          (hasMain && group.mainCompleted > 0 && group.mainCompleted < group.mainTotal);

        if (statusFilter === "pending" && isAllCompleted) continue;
        if (statusFilter === "completed" && !isAllCompleted) continue;
        if (statusFilter === "in_progress" && !hasInProgress) continue;
      }

      filteredSubtemas.push(group);
    }

    filteredSubtemas.sort((x, y) => {
      if (x.isCurrentWeek !== y.isCurrentWeek) return x.isCurrentWeek ? -1 : 1;
      return x.subtema.localeCompare(y.subtema, "pt-BR");
    });

    const byAreaMap = new Map<
      string,
      {
        area: string;
        subtemas: SubtemaGroup[];
        mainTotal: number;
        mainCompleted: number;
        mainRemainingSeconds: number;
      }
    >();

    for (const g of filteredSubtemas) {
      let areaEntry = byAreaMap.get(g.area);
      if (!areaEntry) {
        areaEntry = {
          area: g.area,
          subtemas: [],
          mainTotal: 0,
          mainCompleted: 0,
          mainRemainingSeconds: 0,
        };
        byAreaMap.set(g.area, areaEntry);
      }
      areaEntry.subtemas.push(g);
      areaEntry.mainTotal += g.mainTotal;
      areaEntry.mainCompleted += g.mainCompleted;
      areaEntry.mainRemainingSeconds += g.mainRemainingSeconds;
    }

    const byArea = Array.from(byAreaMap.values()).sort(
      (a, b) =>
        (AREA_ORDER[a.area] ?? 99) - (AREA_ORDER[b.area] ?? 99) ||
        a.area.localeCompare(b.area, "pt-BR")
    );

    return { allSubtemas: filteredSubtemas, byArea };
  }, [
    activeTab,
    scopedLessons,
    paramSubtema,
    deferredSearchText,
    effectiveAreaPill,
    currentWeekSubtemasSet,
    searchHaystackById,
    statusFilter,
  ]);

  // Métricas no cabeçalho: na Trilha R1 contabiliza as Aulas Principais da Medway visíveis
  const headerStats = useMemo(() => {
    if (activeTab === "trilha_r1") {
      let total = 0;
      let completed = 0;
      let remainingSeconds = 0;
      for (const g of trilhaGroups.allSubtemas) {
        total += g.mainTotal;
        completed += g.mainCompleted;
        remainingSeconds += g.mainRemainingSeconds;
      }
      return {
        total,
        completed,
        remainingSeconds,
        labelSuffix: "principais Medway",
      };
    }

    let completed = 0;
    let remainingSeconds = 0;
    for (const l of filteredModuleLessons) {
      if (l.progress.status === "completed") {
        completed += 1;
      } else {
        remainingSeconds += l.duration_seconds || 0;
      }
    }
    return {
      total: filteredModuleLessons.length,
      completed,
      remainingSeconds,
      labelSuffix: "aulas",
    };
  }, [activeTab, trilhaGroups.allSubtemas, filteredModuleLessons]);

  // Agrupamento das abas Prática, Radiologia e Acervo MedCof
  const groupedModules = useMemo(() => {
    if (activeTab === "trilha_r1") return [];
    const useMedcofAreaTema = activeTab === "medcof_r1_2026" && medcofGroupMode === "area_tema";
    const sortedSource = useMedcofAreaTema
      ? [...filteredModuleLessons].sort((a, b) => {
          const areaA = a.subtema ? a.area : "ZZZ";
          const areaB = b.subtema ? b.area : "ZZZ";
          if (areaA !== areaB) return areaA.localeCompare(areaB, "pt-BR");
          const subA = a.subtema || "Outros temas MedCof";
          const subB = b.subtema || "Outros temas MedCof";
          if (subA !== subB) return subA.localeCompare(subB, "pt-BR");
          return a.module_order - b.module_order || a.lesson_order - b.lesson_order;
        })
      : filteredModuleLessons;

    const groups: Array<{
      key: string;
      moduleName: string;
      area: string;
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
  }, [activeTab, filteredModuleLessons, medcofGroupMode]);

  // Modo Sala de Aula: busca detalhe da aula selecionada (?lesson=<id>)
  const {
    data: detailData,
    isError: isExplicitLessonError,
    isLoading: isDetailLoading,
  } = useQuery({
    queryKey: ["lesson-detail", paramLessonId],
    queryFn: () => api.lessons.get(paramLessonId!),
    enabled: Boolean(canAccessLessons && paramLessonId),
    staleTime: 60_000,
    retry: false,
  });

  const listActiveLesson = useMemo(
    () => (paramLessonId ? allFetchedLessons.find((l) => l.id === paramLessonId) ?? null : null),
    [allFetchedLessons, paramLessonId]
  );

  const activeLesson: LessonItem | null =
    paramLessonId && isExplicitLessonError
      ? null
      : detailData?.lesson ?? listActiveLesson;

  const activePlaylist = useMemo(() => {
    if (detailData?.playlist && detailData.playlist.length > 0 && activeLesson?.id === detailData.lesson.id) {
      return detailData.playlist;
    }
    if (activeLesson?.subtema) {
      return scopedLessons.filter((l) => l.subtema === activeLesson.subtema);
    }
    if (activeLesson) {
      return scopedLessons.filter(
        (l) => l.course_key === activeLesson.course_key && l.module_name === activeLesson.module_name
      );
    }
    return [];
  }, [detailData, activeLesson, scopedLessons]);

  const sidebarSections = useMemo(() => {
    if (!activeLesson?.subtema) {
      return {
        isSubtemaMode: false,
        main: activePlaylist,
        optionalMedway: [] as LessonItem[],
        extraMedcof: [] as LessonItem[],
      };
    }
    const main: LessonItem[] = [];
    const optionalMedway: LessonItem[] = [];
    const extraMedcof: LessonItem[] = [];
    for (const item of activePlaylist) {
      if (isMedwayMain(item)) main.push(item);
      else if (isMedwayOptional(item)) optionalMedway.push(item);
      else extraMedcof.push(item);
    }
    return {
      isSubtemaMode: true,
      main,
      optionalMedway,
      extraMedcof,
    };
  }, [activeLesson, activePlaylist]);

  // Navegação Anterior / Próxima prioriza as Principais Medway quando a aula atual é principal
  const navList = useMemo(() => {
    if (!activeLesson) return [];
    if (sidebarSections.isSubtemaMode && isMedwayMain(activeLesson)) {
      if (sidebarSections.main.some((l) => l.id === activeLesson.id)) {
        return sidebarSections.main;
      }
    }
    if (activePlaylist.some((l) => l.id === activeLesson.id)) {
      return activePlaylist;
    }
    return scopedLessons;
  }, [activeLesson, sidebarSections, activePlaylist, scopedLessons]);

  const currentIdx = activeLesson ? navList.findIndex((l) => l.id === activeLesson.id) : -1;
  const prevLesson = currentIdx > 0 ? navList[currentIdx - 1] : null;
  const nextLesson =
    currentIdx >= 0 && currentIdx < navList.length - 1 ? navList[currentIdx + 1] : null;

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

  const handleSelectLesson = (lesson: LessonItem, preserveSubtema?: string) => {
    const updates: Record<string, string | null> = { lesson: String(lesson.id) };
    if (preserveSubtema !== undefined) {
      updates.subtema = preserveSubtema || null;
    }
    updateUrlParams(updates);
  };

  const handleSelectViewTab = (nextTab: ViewTab) => {
    setSelectedAreaPill(null);
    updateUrlParams({
      course: nextTab === "trilha_r1" ? null : nextTab,
      lesson: null,
      subtema: nextTab === "trilha_r1" ? paramSubtema || null : null,
    });
  };

  const handleSaveProgress = async (
    targetLesson: LessonItem,
    overrides: {
      status?: LessonProgressStatus;
      bookmark_seconds?: number;
      notes?: string;
    },
    advanceNext?: LessonItem | null,
    silent?: boolean
  ) => {
    if (!silent) setSavingProgress(true);
    try {
      const res = await api.lessons.saveProgress(targetLesson.id, overrides);

      const statusChanged = targetLesson.progress.status !== res.status;

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

      queryClient.setQueryData<{ lesson?: LessonItem | null; stats?: unknown } | undefined>(
        ["lessons-continue"],
        (old) => {
          if (!old || !old.lesson || old.lesson.id !== targetLesson.id) return old;
          return {
            ...old,
            lesson: {
              ...old.lesson,
              progress: {
                ...old.lesson.progress,
                status: res.status,
                bookmark_seconds: res.bookmark_seconds,
                notes: res.notes,
                has_notes: res.has_notes,
                completed_at: res.completed_at,
                updated_at: res.updated_at,
              },
            },
          };
        }
      );

      if (!silent || statusChanged) {
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ["lessons-summary-by-subtema"] }),
          queryClient.invalidateQueries({ queryKey: ["lessons-by-subtema"] }),
          queryClient.invalidateQueries({ queryKey: ["lessons-continue"] }),
          queryClient.invalidateQueries({ queryKey: ["theme-progress"] }),
          queryClient.invalidateQueries({ queryKey: ["smart-notebook-lessons"] }),
        ]);
      }

      if (!silent) {
        if (res.theme_theory_completed && targetLesson.subtema) {
          toast.success(
            `Teoria de "${targetLesson.subtema}" concluída! Próximo passo: ${defaultPostQuestions}q de fixação pós-aula.`
          );
        } else if (overrides.status === "completed") {
          toast.success("Aula marcada como concluída.");
        } else if (overrides.bookmark_seconds !== undefined || overrides.notes !== undefined) {
          toast.success("Ponto salvo e anotações sincronizadas com o Caderno Inteligente.");
        }
      }
      if (advanceNext) {
        handleSelectLesson(advanceNext);
      }
    } catch {
      if (!silent) {
        toast.error("Não foi possível salvar o progresso da aula.");
      }
    } finally {
      if (!silent) setSavingProgress(false);
    }
  };

  const handleAutoBookmarkFromVideo = (lesson: LessonItem, currentSeconds: number, immediate: boolean) => {
    const sec = Math.max(0, Math.floor(currentSeconds));
    if (sec < 5) return;
    const prev =
      lastAutoSavedRef.current.lessonId === lesson.id
        ? lastAutoSavedRef.current.seconds
        : lesson.progress.bookmark_seconds || 0;
    const minDelta = immediate ? 3 : 25;
    if (Math.abs(sec - prev) < minDelta) return;

    lastAutoSavedRef.current = { lessonId: lesson.id, seconds: sec };
    const nextStatus: LessonProgressStatus =
      lesson.progress.status === "not_started" ? "in_progress" : lesson.progress.status;
    void handleSaveProgress(
      lesson,
      {
        status: nextStatus,
        bookmark_seconds: sec,
      },
      undefined,
      true
    );
  };

  const handleToggleQuickComplete = (lesson: LessonItem) => {
    const isDone = lesson.progress.status === "completed";
    void handleSaveProgress(lesson, { status: isDone ? "not_started" : "completed" });
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

  const handleToggleCyclePhase = async (
    subtema: string,
    phase: LessonCyclePhase,
    currentlyDone: boolean
  ) => {
    setSavingCycle(true);
    try {
      const target = phase === "pre" ? defaultPreQuestions : defaultPostQuestions;
      const res = await api.lessons.saveCyclePhase({
        subtema,
        phase,
        target,
        done: !currentlyDone,
      });
      queryClient.setQueryData<LessonCycleResponse>(["lessons-cycle"], (old) => ({
        settings: res.settings,
        cycles: {
          ...(old?.cycles ?? {}),
          [subtema]: res.cycle,
        },
      }));
      if (activeLesson && activeLesson.subtema === subtema) {
        queryClient.setQueryData<LessonDetailResponse>(["lesson-detail", activeLesson.id], (old) =>
          old ? { ...old, cycle: res.cycle, cycle_settings: res.settings } : old
        );
      }
      void queryClient.invalidateQueries({ queryKey: ["lessons-summary-by-subtema"] });
      const label = phase === "pre" ? "Pré-aula" : "Pós-aula";
      toast.success(!currentlyDone ? `${label} marcada como concluída.` : `${label} reaberta.`);
    } catch {
      toast.error("Não foi possível atualizar a etapa do ciclo.");
    } finally {
      setSavingCycle(false);
    }
  };

  const handleOpenCycleSettings = () => {
    setDraftCyclePre(String(defaultPreQuestions));
    setDraftCyclePost(String(defaultPostQuestions));
    setShowCycleSettings((v) => !v);
  };

  const handleSaveCycleSettings = async (overridePre?: number, overridePost?: number) => {
    const preVal = overridePre ?? Number(draftCyclePre);
    const postVal = overridePost ?? Number(draftCyclePost);
    if (!Number.isInteger(preVal) || preVal < 0 || preVal > 30) {
      toast.error("Pré-aula deve ser um número inteiro entre 0 e 30.");
      return;
    }
    if (!Number.isInteger(postVal) || postVal < 1 || postVal > 100) {
      toast.error("Pós-aula deve ser um número inteiro entre 1 e 100.");
      return;
    }
    setSavingCycle(true);
    try {
      const saved = await api.lessons.saveCycleSettings({
        default_pre_questions: preVal,
        default_post_questions: postVal,
      });
      queryClient.setQueryData<LessonCycleResponse>(["lessons-cycle"], (old) => ({
        settings: saved,
        cycles: old?.cycles ?? {},
      }));
      void queryClient.invalidateQueries({ queryKey: ["lessons-summary-by-subtema"] });
      void queryClient.invalidateQueries({ queryKey: ["lesson-detail"] });
      setDraftCyclePre(String(saved.default_pre_questions));
      setDraftCyclePost(String(saved.default_post_questions));
      setShowCycleSettings(false);
      toast.success(
        `Padrão do ciclo salvo: ${saved.default_pre_questions}q antes → Aula → ${saved.default_post_questions}q depois.`
      );
    } catch {
      toast.error("Não foi possível salvar o padrão do ciclo.");
    } finally {
      setSavingCycle(false);
    }
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

  // ============================================================================
  // MODO SALA DE AULA (?lesson=<id> presente na URL)
  // ============================================================================
  if (isClassroomMode) {
    const activeCycle = activeLesson?.subtema
      ? cyclesBySubtema[activeLesson.subtema] ??
        (detailData?.lesson.id === activeLesson.id ? detailData.cycle : null) ??
        null
      : null;
    const classroomPreTarget =
      activeCycle?.pre_done && activeCycle.pre_target > 0
        ? activeCycle.pre_target
        : defaultPreQuestions;
    const classroomPostTarget =
      activeCycle?.post_done && activeCycle.post_target > 0
        ? activeCycle.post_target
        : defaultPostQuestions;
    const classroomMainTotal = sidebarSections.isSubtemaMode ? sidebarSections.main.length : 0;
    const classroomMainCompleted = sidebarSections.isSubtemaMode
      ? sidebarSections.main.filter((l) => l.progress.status === "completed").length
      : 0;
    const classroomLessonDone =
      classroomMainTotal > 0
        ? classroomMainCompleted >= classroomMainTotal
        : activeLesson?.progress.status === "completed";
    const classroomDelta =
      activeCycle?.pre_accuracy != null && activeCycle?.post_accuracy != null
        ? activeCycle.post_accuracy - activeCycle.pre_accuracy
        : null;
    const playerPreviewUrl = activeLesson
      ? activeLesson.preview_url || `https://drive.google.com/file/d/${activeLesson.drive_file_id}/preview`
      : "";
    const playerOpenUrl = activeLesson
      ? activeLesson.open_url || `https://drive.google.com/file/d/${activeLesson.drive_file_id}/view`
      : "";
    const extrasExpanded = showSidebarExtras || Boolean(activeLesson && !isMedwayMain(activeLesson) && !isMedwayOptional(activeLesson));

    return (
      <div className="flex flex-col gap-4">
        {/* Barra superior da Sala de Aula */}
        <div className="rounded-md border border-line-subtle bg-surface px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5 min-w-0">
            <button
              type="button"
              onClick={() => updateUrlParams({ lesson: null })}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-line-subtle bg-canvas hover:bg-elevated text-xs font-semibold text-ink-primary transition-colors cursor-pointer shrink-0"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Voltar para a trilha
            </button>
            {activeLesson && (
              <div className="flex items-center gap-1.5 text-xs text-ink-secondary min-w-0 truncate">
                <span className="font-medium text-ink-muted">{activeLesson.area}</span>
                <ChevronRight className="w-3.5 h-3.5 text-ink-muted shrink-0" />
                <span className="font-semibold text-ink-primary truncate">
                  {activeLesson.subtema || activeLesson.module_name}
                </span>
              </div>
            )}
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
            {activeLesson && (
              <a
                href={playerOpenUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-line-subtle bg-canvas hover:bg-elevated text-xs font-medium text-ink-primary transition-colors"
              >
                Abrir no Drive <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        </div>

        {/* Player + Playlist do Subtema/Módulo */}
        <div
          className={clsx(
            "grid grid-cols-1 gap-5 items-start",
            !theaterMode && "lg:grid-cols-[minmax(0,1fr)_390px]"
          )}
        >
          <section className="rounded-md border border-line-subtle bg-surface overflow-hidden flex flex-col">
            {isExplicitLessonError ? (
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
                  Voltar para a trilha
                </button>
              </div>
            ) : (isDetailLoading && !activeLesson) || !activeLesson ? (
              <div className="p-6 space-y-4">
                <div className="aspect-video w-full rounded-md bg-elevated animate-pulse" />
                <div className="h-24 rounded-md bg-elevated animate-pulse" />
              </div>
            ) : (
              <>
                {(() => {
                  const canUseNativeStream =
                    Boolean(activeLesson.stream_url) &&
                    !forceDriveEmbed &&
                    failedStreamLessonId !== activeLesson.id;

                  return (
                    <>
                      <div className="relative w-full aspect-video bg-black">
                        {canUseNativeStream ? (
                          <video
                            ref={videoRef}
                            key={`native-${activeLesson.id}`}
                            src={activeLesson.stream_url!}
                            controls
                            playsInline
                            preload="metadata"
                            className="w-full h-full bg-black"
                            onLoadedMetadata={(e) => {
                              const vid = e.currentTarget;
                              vid.playbackRate = playbackRate;
                              if (
                                seekAppliedForLessonRef.current !== activeLesson.id &&
                                activeLesson.progress.bookmark_seconds > 5
                              ) {
                                seekAppliedForLessonRef.current = activeLesson.id;
                                const maxSeek = Math.max(
                                  0,
                                  (Number.isFinite(vid.duration) ? vid.duration : 86400) - 8
                                );
                                vid.currentTime = Math.min(
                                  activeLesson.progress.bookmark_seconds,
                                  maxSeek
                                );
                              }
                            }}
                            onTimeUpdate={(e) => {
                              handleAutoBookmarkFromVideo(
                                activeLesson,
                                e.currentTarget.currentTime,
                                false
                              );
                            }}
                            onPause={(e) => {
                              const sec = Math.floor(e.currentTarget.currentTime);
                              if (sec >= 5) {
                                setDraftEdit((prev) => ({
                                  lessonId: activeLesson.id,
                                  bookmark: formatSecondsToMmSs(sec),
                                  notes:
                                    prev?.lessonId === activeLesson.id
                                      ? prev.notes
                                      : activeLesson.progress.notes || "",
                                }));
                              }
                              handleAutoBookmarkFromVideo(activeLesson, sec, true);
                            }}
                            onError={() => {
                              setFailedStreamLessonId(activeLesson.id);
                            }}
                          />
                        ) : (
                          <iframe
                            key={activeLesson.drive_file_id}
                            src={playerPreviewUrl}
                            title={activeLesson.title}
                            allow="autoplay; fullscreen"
                            allowFullScreen
                            className="w-full h-full border-0"
                          />
                        )}
                      </div>

                      {/* Barra de Qualidade HD / Velocidade / Alternância de Player */}
                      <div className="px-4 py-2 bg-canvas border-b border-line-subtle flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span
                            className={clsx(
                              "px-2 py-0.5 rounded-xs font-semibold border text-[11px]",
                              canUseNativeStream
                                ? "bg-success/10 text-success border-success/30"
                                : "bg-elevated text-ink-secondary border-line-subtle"
                            )}
                          >
                            {canUseNativeStream
                              ? "HD Original (720p/1080p • Auto-save ativo)"
                              : "Player Google Drive (Embed)"}
                          </span>

                          {canUseNativeStream && (
                            <div className="inline-flex items-center gap-1 ml-1">
                              <span className="text-[11px] text-ink-muted">Velocidade:</span>
                              {[1, 1.25, 1.5, 1.75, 2].map((rate) => (
                                <button
                                  key={rate}
                                  type="button"
                                  onClick={() => {
                                    setPlaybackRate(rate);
                                    if (videoRef.current) {
                                      videoRef.current.playbackRate = rate;
                                    }
                                  }}
                                  className={clsx(
                                    "px-1.5 py-0.5 rounded-xs font-mono-lab text-[11px] border transition-colors cursor-pointer",
                                    playbackRate === rate
                                      ? "bg-primary text-primary-foreground border-primary font-bold"
                                      : "bg-surface text-ink-secondary border-line-subtle hover:text-ink-primary"
                                  )}
                                >
                                  {rate}x
                                </button>
                              ))}
                            </div>
                          )}
                        </div>

                        {activeLesson.stream_url && (
                          <button
                            type="button"
                            onClick={() => {
                              setFailedStreamLessonId(null);
                              setForceDriveEmbed((v) => !v);
                            }}
                            className="text-[11px] font-semibold text-accent hover:underline cursor-pointer"
                          >
                            {canUseNativeStream
                              ? "Alternar para player do Drive"
                              : "Usar Player HD Original (720p/1080p)"}
                          </button>
                        )}
                      </div>
                    </>
                  );
                })()}

                <div className="p-4 sm:p-5 space-y-5">
                  <div className="space-y-1.5 border-b border-line-subtle pb-4">
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
                    <h1 className="text-base sm:text-lg font-bold text-ink-primary leading-snug break-words">
                      {activeLesson.title}
                    </h1>
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

                  {/* Controles de Status + Navegação */}
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

                  {/* Bookmark + Anotações */}
                  <LessonNotesEditor
                    bookmarkInput={bookmarkInput}
                    notesInput={notesInput}
                    savingProgress={savingProgress}
                    onChangeBookmark={(nextBookmark) =>
                      setDraftEdit({
                        lessonId: activeLesson.id,
                        bookmark: nextBookmark,
                        notes: notesInput,
                      })
                    }
                    onChangeNotes={(nextNotes) =>
                      setDraftEdit({
                        lessonId: activeLesson.id,
                        bookmark: bookmarkInput,
                        notes: nextNotes,
                      })
                    }
                    onSave={() => void handleSaveNotesAndBookmark()}
                  />

                  {/* Ciclo Medway: Pré-aula (5q) → Aula → Pós-aula (25q) */}
                  {activeLesson.subtema && (
                    <div className="rounded-md border border-primary/25 bg-primary/5 p-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5 text-primary" />
                            Ciclo Medway do Tema ({classroomPreTarget > 0 ? `${classroomPreTarget}q → ` : ""}Aula → {classroomPostTarget}q)
                          </p>
                          <p className="text-[11px] text-ink-secondary mt-0.5">
                            Estudo ativo em 3 etapas para &ldquo;{activeLesson.subtema}&rdquo;, sem bloquear sua ordem.
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {classroomDelta !== null && (
                            <span
                              className={clsx(
                                "px-2 py-0.5 rounded-xs text-[11px] font-mono-lab font-bold border",
                                classroomDelta >= 0
                                  ? "bg-success/10 text-success border-success/30"
                                  : "bg-warning/10 text-warning border-warning/30"
                              )}
                            >
                              Pré {activeCycle?.pre_accuracy}% → Pós {activeCycle?.post_accuracy}% ({classroomDelta >= 0 ? "+" : ""}{classroomDelta}pp)
                            </span>
                          )}
                          <Link
                            href={`/analise?tab=cobertura&subtema=${encodeURIComponent(activeLesson.subtema)}`}
                            className="inline-flex items-center px-2.5 py-1 rounded-xs border border-line-subtle bg-surface hover:bg-elevated text-ink-secondary text-[11px] font-medium transition-colors"
                          >
                            Análise
                          </Link>
                        </div>
                      </div>

                      <div className={clsx("grid grid-cols-1 gap-2.5", classroomPreTarget > 0 ? "md:grid-cols-3" : "md:grid-cols-2")}>
                        {/* Etapa 1: Pré-aula */}
                        {classroomPreTarget > 0 && (
                          <div
                            className={clsx(
                              "rounded-md border p-3 flex flex-col justify-between gap-2.5 bg-surface",
                              activeCycle?.pre_done
                                ? "border-success/35 bg-success/5"
                                : !classroomLessonDone
                                ? "border-primary/35"
                                : "border-line-subtle"
                            )}
                          >
                            <div className="space-y-1">
                              <div className="flex items-center justify-between gap-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider font-mono-lab text-ink-muted">
                                  1. Pré-aula
                                </span>
                                {activeCycle?.pre_done ? (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-success">
                                    <CheckCircle2 className="w-3 h-3" /> Feito
                                  </span>
                                ) : (
                                  <span className="text-[10px] font-mono-lab text-ink-muted">
                                    {classroomPreTarget}q
                                  </span>
                                )}
                              </div>
                              <p className="text-xs font-semibold text-ink-primary">
                                {activeCycle?.pre_done
                                  ? activeCycle.pre_completed > 0
                                    ? `${activeCycle.pre_correct}/${activeCycle.pre_completed} acertos (${activeCycle.pre_accuracy ?? 0}%)`
                                    : "Concluído manualmente"
                                  : `Aquecimento com ${classroomPreTarget} questões`}
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-1.5">
                              <Link
                                href={buildLessonCycleQuizUrl({
                                  subtema: activeLesson.subtema,
                                  phase: "pre",
                                  target: defaultPreQuestions,
                                  returnLessonId: activeLesson.id,
                                })}
                                className={clsx(
                                  "inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs text-[11px] font-semibold transition-colors",
                                  !activeCycle?.pre_done && !classroomLessonDone
                                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                                    : "border border-primary/30 bg-canvas hover:bg-elevated text-primary"
                                )}
                              >
                                <Zap className="w-3 h-3" />
                                {activeCycle?.pre_done ? `Refazer ${defaultPreQuestions}q` : `Fazer ${defaultPreQuestions}q`}
                              </Link>
                              <button
                                type="button"
                                disabled={savingCycle}
                                onClick={() =>
                                  void handleToggleCyclePhase(
                                    activeLesson.subtema!,
                                    "pre",
                                    Boolean(activeCycle?.pre_done)
                                  )
                                }
                                className="px-2 py-1.5 rounded-xs border border-line-subtle bg-canvas hover:bg-elevated text-[11px] text-ink-secondary cursor-pointer"
                              >
                                {activeCycle?.pre_done ? "Desmarcar" : "Já fiz"}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Etapa 2: Aula */}
                        <div
                          className={clsx(
                            "rounded-md border p-3 flex flex-col justify-between gap-2.5 bg-surface",
                            classroomLessonDone
                              ? "border-success/35 bg-success/5"
                              : "border-accent/45 ring-1 ring-accent/15"
                          )}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center justify-between gap-1">
                              <span className="text-[10px] font-bold uppercase tracking-wider font-mono-lab text-accent">
                                {classroomPreTarget > 0 ? "2. Aula" : "1. Aula"} • Você está aqui
                              </span>
                              {classroomLessonDone && (
                                <span className="inline-flex items-center gap-1 text-[10px] font-bold text-success">
                                  <CheckCircle2 className="w-3 h-3" /> Feito
                                </span>
                              )}
                            </div>
                            <p className="text-xs font-semibold text-ink-primary">
                              {classroomMainTotal > 0
                                ? `${classroomMainCompleted}/${classroomMainTotal} aulas principais concluídas`
                                : activeLesson.progress.status === "completed"
                                ? "Aula concluída"
                                : "Assistindo aula do tema"}
                            </p>
                          </div>
                          <div>
                            {activeLesson.progress.status === "completed" ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-success">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Esta aula está concluída
                              </span>
                            ) : (
                              <button
                                type="button"
                                disabled={savingProgress}
                                onClick={() => void handleSaveProgress(activeLesson, { status: "completed" })}
                                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs border border-success/35 bg-success/10 hover:bg-success/20 text-success text-[11px] font-semibold transition-colors cursor-pointer"
                              >
                                <CheckCircle2 className="w-3 h-3" /> Concluir esta aula
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Etapa 3: Pós-aula */}
                        <div
                          className={clsx(
                            "rounded-md border p-3 flex flex-col justify-between gap-2.5 bg-surface",
                            activeCycle?.post_done
                              ? "border-success/35 bg-success/5"
                              : classroomLessonDone
                              ? "border-primary/45 ring-1 ring-primary/15"
                              : "border-line-subtle"
                          )}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center justify-between gap-1">
                              <span className="text-[10px] font-bold uppercase tracking-wider font-mono-lab text-ink-muted">
                                {classroomPreTarget > 0 ? "3. Pós-aula" : "2. Pós-aula"}
                              </span>
                              {activeCycle?.post_done ? (
                                <span className="inline-flex items-center gap-1 text-[10px] font-bold text-success">
                                  <CheckCircle2 className="w-3 h-3" /> Feito
                                </span>
                              ) : (
                                <span className="text-[10px] font-mono-lab text-ink-muted">
                                  {classroomPostTarget}q
                                </span>
                              )}
                            </div>
                            <p className="text-xs font-semibold text-ink-primary">
                              {activeCycle?.post_done
                                ? activeCycle.post_completed > 0
                                  ? `${activeCycle.post_correct}/${activeCycle.post_completed} acertos (${activeCycle.post_accuracy ?? 0}%)`
                                  : "Concluído manualmente"
                                : `Fixação com ${classroomPostTarget} questões (FSRS)`}
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Link
                              href={buildLessonCycleQuizUrl({
                                subtema: activeLesson.subtema,
                                phase: "post",
                                target: defaultPostQuestions,
                                returnLessonId: activeLesson.id,
                              })}
                              className={clsx(
                                "inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xs text-[11px] font-semibold transition-colors",
                                classroomLessonDone && !activeCycle?.post_done
                                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                                  : "border border-primary/30 bg-canvas hover:bg-elevated text-primary"
                              )}
                            >
                              <Zap className="w-3 h-3" />
                              {activeCycle?.post_done ? `Refazer ${defaultPostQuestions}q` : `Fazer ${defaultPostQuestions}q →`}
                            </Link>
                            <button
                              type="button"
                              disabled={savingCycle}
                              onClick={() =>
                                void handleToggleCyclePhase(
                                  activeLesson.subtema!,
                                  "post",
                                  Boolean(activeCycle?.post_done)
                                )
                              }
                              className="px-2 py-1.5 rounded-xs border border-line-subtle bg-canvas hover:bg-elevated text-[11px] text-ink-secondary cursor-pointer"
                            >
                              {activeCycle?.post_done ? "Desmarcar" : "Já fiz"}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </section>

          {/* Playlist lateral focada no Subtema (ou Módulo) */}
          <aside
            className={clsx(
              "rounded-md border border-line-subtle bg-surface overflow-hidden flex flex-col",
              !theaterMode && "lg:max-h-[calc(100vh-10rem)]"
            )}
          >
            <div className="px-4 py-3 border-b border-line-subtle bg-canvas/60">
              <p className="text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                {sidebarSections.isSubtemaMode ? "Aulas do Tema" : "Playlist do Módulo"}
              </p>
              {activeLesson && (
                <p className="text-xs font-semibold text-ink-primary truncate mt-0.5">
                  {activeLesson.subtema || activeLesson.module_name}
                </p>
              )}
            </div>

            <div className="overflow-y-auto p-3 space-y-3">
              {sidebarSections.isSubtemaMode ? (
                <>
                  {sidebarSections.main.length > 0 && (
                    <div>
                      <button
                        type="button"
                        onClick={() => setShowSidebarMain((v) => !v)}
                        className="w-full flex items-center justify-between px-1 py-1 text-[11px] font-bold uppercase tracking-wider text-primary hover:opacity-85 cursor-pointer"
                      >
                        <span>Principais Medway ({sidebarSections.main.length})</span>
                        {showSidebarMain ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>
                      {showSidebarMain && (
                        <div className="space-y-1 mt-1.5">
                          {sidebarSections.main.map((item) => (
                            <LessonRowCompact
                              key={item.id}
                              item={item}
                              isActive={activeLesson?.id === item.id}
                              savingProgress={savingProgress}
                              onSelect={(l) => handleSelectLesson(l)}
                              onToggleComplete={handleToggleQuickComplete}
                              showKindBadge={false}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {sidebarSections.optionalMedway.length > 0 && (
                    <div className="pt-2 border-t border-line-subtle">
                      <button
                        type="button"
                        onClick={() => setShowSidebarOptional((v) => !v)}
                        className="w-full flex items-center justify-between px-1 py-1 text-[11px] font-bold uppercase tracking-wider text-ink-secondary hover:text-ink-primary cursor-pointer"
                      >
                        <span>Flash &amp; Revisão Medway ({sidebarSections.optionalMedway.length})</span>
                        {showSidebarOptional ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>
                      {showSidebarOptional && (
                        <div className="space-y-1 mt-1.5">
                          {sidebarSections.optionalMedway.map((item) => (
                            <LessonRowCompact
                              key={item.id}
                              item={item}
                              isActive={activeLesson?.id === item.id}
                              savingProgress={savingProgress}
                              onSelect={(l) => handleSelectLesson(l)}
                              onToggleComplete={handleToggleQuickComplete}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {sidebarSections.extraMedcof.length > 0 && (
                    <div className="pt-2 border-t border-line-subtle">
                      <button
                        type="button"
                        onClick={() => setShowSidebarExtras((v) => !v)}
                        className="w-full flex items-center justify-between px-1 py-1 text-[11px] font-bold uppercase tracking-wider text-ink-secondary hover:text-ink-primary cursor-pointer"
                      >
                        <span>Extras MedCof ({sidebarSections.extraMedcof.length})</span>
                        {extrasExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>
                      {extrasExpanded && (
                        <div className="space-y-1 mt-1.5">
                          {sidebarSections.extraMedcof.map((item) => (
                            <LessonRowCompact
                              key={item.id}
                              item={item}
                              isActive={activeLesson?.id === item.id}
                              savingProgress={savingProgress}
                              onSelect={(l) => handleSelectLesson(l)}
                              onToggleComplete={handleToggleQuickComplete}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <div className="space-y-1">
                  {sidebarSections.main.map((item) => (
                    <LessonRowCompact
                      key={item.id}
                      item={item}
                      isActive={activeLesson?.id === item.id}
                      savingProgress={savingProgress}
                      onSelect={(l) => handleSelectLesson(l)}
                      onToggleComplete={handleToggleQuickComplete}
                    />
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    );
  }

  // ============================================================================
  // VISÃO DA TRILHA / CATÁLOGO LIMPO (!paramLessonId)
  // ============================================================================
  const showAllAreaDividers =
    activeTab === "trilha_r1" && !paramSubtema && !hasSearch && effectiveAreaPill === "all";
  const singleSubtemaMatch =
    (Boolean(paramSubtema) || hasSearch) && trilhaGroups.allSubtemas.length === 1;

  return (
    <div className="flex flex-col gap-4">
      <LessonsHeader
        activeTab={activeTab}
        onSelectTab={handleSelectViewTab}
        hasData={Boolean(data)}
        headerStats={headerStats}
        searchText={searchText}
        onChangeSearch={setSearchText}
        statusFilter={statusFilter}
        onChangeStatusFilter={setStatusFilter}
        medcofGroupMode={medcofGroupMode}
        onChangeMedcofGroupMode={setMedcofGroupMode}
        activeAreaPill={effectiveAreaPill}
        onSelectAreaPill={setSelectedAreaPill}
        areaPillStats={areaPillStats}
        currentWeek={currentWeekData?.week ?? null}
        currentWeekStats={currentWeekMainStats}
        paramSubtema={paramSubtema}
        onClearSubtema={() => updateUrlParams({ subtema: null })}
        defaultPreQuestions={defaultPreQuestions}
        defaultPostQuestions={defaultPostQuestions}
        showCycleSettings={showCycleSettings}
        onToggleCycleSettings={handleOpenCycleSettings}
        draftCyclePre={draftCyclePre}
        onChangeDraftCyclePre={setDraftCyclePre}
        draftCyclePost={draftCyclePost}
        onChangeDraftCyclePost={setDraftCyclePost}
        savingCycle={savingCycle}
        onSaveCycleSettings={(pre, post) => void handleSaveCycleSettings(pre, post)}
      />

      {/* Banner fino: Continuar estudando / Próxima aula */}
      {activeTab === "trilha_r1" && !paramSubtema && continueData?.lesson && (
        <section className="rounded-md border border-primary/25 bg-surface px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="min-w-0 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 font-bold text-accent">
                <PlayCircle className="w-3.5 h-3.5" />
                {continueData.reason === "in_progress"
                  ? "Continuar de onde parou"
                  : continueData.reason === "planner_week"
                  ? `Próxima da Semana ${continueData.planner_week ?? ""}`
                  : "Próxima aula principal"}
              </span>
              {continueData.lesson.progress.bookmark_seconds > 0 && (
                <span className="px-1.5 py-0.2 rounded-xs bg-warning/15 text-warning font-mono-lab font-semibold">
                  {formatSecondsToMmSs(continueData.lesson.progress.bookmark_seconds)}
                </span>
              )}
              {continueData.lesson.duration_seconds && (
                <span className="font-mono-lab text-ink-muted">
                  {formatDuration(continueData.lesson.duration_seconds)}
                </span>
              )}
            </div>
            <p className="text-sm font-bold text-ink-primary truncate">{continueData.lesson.title}</p>
            <p className="text-xs text-ink-secondary truncate">
              {continueData.lesson.subtema || continueData.lesson.module_name}
              {continueData.stats.primary_total > 0 && (
                <>
                  {" • "}
                  {continueData.stats.primary_completed}/{continueData.stats.primary_total} principais Medway
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0 self-start sm:self-auto">
            {continueData.lesson.subtema &&
              defaultPreQuestions > 0 &&
              continueData.lesson.progress.status === "not_started" &&
              !cyclesBySubtema[continueData.lesson.subtema]?.pre_done && (
                <Link
                  href={buildLessonCycleQuizUrl({
                    subtema: continueData.lesson.subtema,
                    phase: "pre",
                    target: defaultPreQuestions,
                    returnLessonId: continueData.lesson.id,
                  })}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-primary/35 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold transition-colors"
                >
                  <Zap className="w-3.5 h-3.5" />
                  Pré ({defaultPreQuestions}q)
                </Link>
              )}
            <button
              type="button"
              onClick={() =>
                handleSelectLesson(
                  continueData.lesson!,
                  continueData.lesson!.subtema || undefined
                )
              }
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-colors cursor-pointer"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              Assistir agora →
            </button>
          </div>
        </section>
      )}

      {/* Conteúdo Principal */}
      {isLoading ? (
        <div className="space-y-3">
          <div className="h-24 rounded-md bg-surface border border-line-subtle animate-pulse" />
          <div className="h-44 rounded-md bg-surface border border-line-subtle animate-pulse" />
        </div>
      ) : isError ? (
        <div className="rounded-md border border-line-subtle bg-surface p-8 text-center space-y-3">
          <p className="text-sm font-semibold text-ink-primary">Erro ao carregar catálogo de aulas.</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold cursor-pointer"
          >
            Tentar novamente
          </button>
        </div>
      ) : activeTab === "trilha_r1" ? (
        trilhaGroups.allSubtemas.length === 0 ? (
          <div className="rounded-md border border-line-subtle bg-surface p-10 text-center space-y-2">
            <Film className="w-8 h-8 text-ink-muted mx-auto" />
            <p className="text-sm font-semibold text-ink-primary">Nenhum tema encontrado.</p>
            <p className="text-xs text-ink-secondary">
              {effectiveAreaPill === "current_week" && !hasSearch
                ? "Sua semana atual do Planner não possui temas pendentes neste filtro. Selecione outra área acima."
                : "Ajuste a busca ou limpe os filtros para ver os 170 subtemas."}
            </p>
          </div>
        ) : showAllAreaDividers ? (
          <div className="space-y-4">
            {trilhaGroups.byArea.map((areaGroup) => (
              <section
                key={areaGroup.area}
                className="rounded-md border border-line-subtle bg-surface overflow-hidden"
              >
                <div className="px-4 py-2.5 bg-canvas/70 border-b border-line-subtle flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={clsx(
                        "w-2 h-2 rounded-full shrink-0",
                        getAreaDotClass(areaGroup.area)
                      )}
                    />
                    <h2 className="text-sm font-bold text-ink-primary truncate">
                      {areaGroup.area}
                    </h2>
                    <span className="text-xs text-ink-muted">
                      ({areaGroup.subtemas.length}{" "}
                      {areaGroup.subtemas.length === 1 ? "tema" : "temas"})
                    </span>
                  </div>
                  <span className="text-xs font-mono-lab text-ink-secondary shrink-0 tabular-nums">
                    {areaGroup.mainCompleted}/{areaGroup.mainTotal} principais
                    {areaGroup.mainRemainingSeconds > 0
                      ? ` • ${formatDuration(areaGroup.mainRemainingSeconds)}`
                      : ""}
                  </span>
                </div>

                <div className="divide-y divide-line-subtle">
                  {areaGroup.subtemas.map((subGroup) => {
                    const isExpanded =
                      expandedSubtemas[subGroup.subtema] !== undefined
                        ? expandedSubtemas[subGroup.subtema]
                        : singleSubtemaMatch;
                    const isComplementsOpen =
                      expandedComplements[subGroup.subtema] !== undefined
                        ? expandedComplements[subGroup.subtema]
                        : subGroup.hasSecondaryMatch;

                    return (
                      <SubtemaRow
                        key={subGroup.subtema}
                        subGroup={subGroup}
                        subCycle={cyclesBySubtema[subGroup.subtema]}
                        isExpanded={isExpanded}
                        onToggleExpand={() =>
                          setExpandedSubtemas((prev) => ({
                            ...prev,
                            [subGroup.subtema]: !isExpanded,
                          }))
                        }
                        isComplementsOpen={isComplementsOpen}
                        onToggleComplements={() =>
                          setExpandedComplements((prev) => ({
                            ...prev,
                            [subGroup.subtema]: !isComplementsOpen,
                          }))
                        }
                        showWeekBadge
                        showAreaBadge={false}
                        currentWeek={currentWeekData?.week ?? null}
                        defaultPreQuestions={defaultPreQuestions}
                        defaultPostQuestions={defaultPostQuestions}
                        savingProgress={savingProgress}
                        savingCycle={savingCycle}
                        onSelectLesson={handleSelectLesson}
                        onToggleQuickComplete={handleToggleQuickComplete}
                        onToggleCyclePhase={(sub, phase, done) =>
                          void handleToggleCyclePhase(sub, phase, done)
                        }
                      />
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <section className="rounded-md border border-line-subtle bg-surface divide-y divide-line-subtle overflow-hidden">
            {trilhaGroups.allSubtemas.map((subGroup) => {
              const isExpanded =
                expandedSubtemas[subGroup.subtema] !== undefined
                  ? expandedSubtemas[subGroup.subtema]
                  : singleSubtemaMatch;
              const isComplementsOpen =
                expandedComplements[subGroup.subtema] !== undefined
                  ? expandedComplements[subGroup.subtema]
                  : subGroup.hasSecondaryMatch;

              return (
                <SubtemaRow
                  key={subGroup.subtema}
                  subGroup={subGroup}
                  subCycle={cyclesBySubtema[subGroup.subtema]}
                  isExpanded={isExpanded}
                  onToggleExpand={() =>
                    setExpandedSubtemas((prev) => ({
                      ...prev,
                      [subGroup.subtema]: !isExpanded,
                    }))
                  }
                  isComplementsOpen={isComplementsOpen}
                  onToggleComplements={() =>
                    setExpandedComplements((prev) => ({
                      ...prev,
                      [subGroup.subtema]: !isComplementsOpen,
                    }))
                  }
                  showWeekBadge={hasSearch || effectiveAreaPill !== "current_week"}
                  showAreaBadge={hasSearch || effectiveAreaPill === "current_week"}
                  currentWeek={currentWeekData?.week ?? null}
                  defaultPreQuestions={defaultPreQuestions}
                  defaultPostQuestions={defaultPostQuestions}
                  savingProgress={savingProgress}
                  savingCycle={savingCycle}
                  onSelectLesson={handleSelectLesson}
                  onToggleQuickComplete={handleToggleQuickComplete}
                  onToggleCyclePhase={(sub, phase, done) =>
                    void handleToggleCyclePhase(sub, phase, done)
                  }
                />
              );
            })}
          </section>
        )
      ) : groupedModules.length === 0 ? (
        <div className="rounded-md border border-line-subtle bg-surface p-10 text-center space-y-2">
          <Film className="w-8 h-8 text-ink-muted mx-auto" />
          <p className="text-sm font-semibold text-ink-primary">Nenhuma aula encontrada.</p>
          <p className="text-xs text-ink-secondary">
            Ajuste a busca ou limpe os filtros desta aba.
          </p>
        </div>
      ) : (
        <section className="rounded-md border border-line-subtle bg-surface divide-y divide-line-subtle overflow-hidden">
          {groupedModules.map((group) => {
            const forceExpand =
              deferredSearchText.trim().length >= 2 || groupedModules.length <= 3;
            const isExpanded =
              expandedModules[group.key] !== undefined
                ? expandedModules[group.key]
                : forceExpand;
            const remDur = formatDuration(group.remainingSeconds);
            const pct =
              group.items.length > 0
                ? Math.round((group.completedCount / group.items.length) * 100)
                : 0;
            const allDone = group.items.length > 0 && group.completedCount >= group.items.length;

            return (
              <div key={group.key} className={clsx(isExpanded && "bg-canvas/30")}>
                <button
                  type="button"
                  onClick={() =>
                    setExpandedModules((prev) => ({
                      ...prev,
                      [group.key]: !isExpanded,
                    }))
                  }
                  aria-expanded={isExpanded}
                  className="w-full px-4 py-3 flex items-center justify-between gap-3 hover:bg-elevated/35 transition-colors cursor-pointer text-left"
                >
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <span className="mt-0.5 text-ink-muted shrink-0">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </span>
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <h2 className="text-sm font-semibold text-ink-primary truncate">
                          {group.moduleName}
                        </h2>
                        {group.area && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.2 rounded-xs bg-elevated text-ink-secondary border border-line-subtle shrink-0">
                            <span
                              className={clsx(
                                "w-1.5 h-1.5 rounded-full",
                                getAreaDotClass(group.area)
                              )}
                            />
                            {getShortAreaLabel(group.area)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px]">
                        <div className="w-16 h-1 rounded-full bg-elevated overflow-hidden shrink-0">
                          <div
                            className={clsx(
                              "h-full rounded-full transition-all",
                              allDone ? "bg-success" : "bg-primary"
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span
                          className={clsx(
                            "font-mono-lab tabular-nums",
                            allDone ? "text-success font-medium" : "text-ink-secondary"
                          )}
                        >
                          {group.completedCount}/{group.items.length} aulas
                          {remDur ? ` • ${remDur}` : allDone ? " • Concluído" : ""}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-4 pb-3 pt-2 border-t border-line-subtle/60 bg-canvas/40 space-y-1">
                    {group.items.map((item) => (
                      <LessonRowCompact
                        key={item.id}
                        item={item}
                        savingProgress={savingProgress}
                        onSelect={(l) => handleSelectLesson(l)}
                        onToggleComplete={handleToggleQuickComplete}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
