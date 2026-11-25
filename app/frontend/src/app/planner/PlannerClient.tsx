"use client";
import { useRouter } from "next/navigation";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  PlannerWeek,
  PlannerProgressMap,
  PlannerTopic,
  PlannerConfig,
  PlannerTopicProgressMap,
  PlannerOrganizationMode,
  PlannerScheduleMode,
} from "@/types/api";
import { api, OfflineQueuedError } from "@/lib/api";
import { useLessonsAccess } from "@/hooks/useLessonsAccess";
import { CalendarDays, Loader2, RotateCcw, AlertTriangle, Zap, Settings2, Layers, CalendarRange, ChevronDown, ChevronUp, CheckCircle2 } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { PlannerWeekCard, getAreaColorClass } from "./components/PlannerWeekCard";
import { PlannerModals } from "./components/PlannerModals";

interface PlannerClientProps {
  plan: PlannerWeek[];
  completedTopicsOutside?: PlannerTopic[];
  initialProgress: PlannerProgressMap;
  initialTopicProgress: PlannerTopicProgressMap;
  warning?: string;
  isIntensive?: boolean;
  organizationMode?: PlannerOrganizationMode;
  config?: PlannerConfig | null;
}

export function PlannerClient({
  plan,
  completedTopicsOutside = [],
  initialProgress,
  initialTopicProgress,
  warning,
  isIntensive,
  organizationMode = "geral",
  config,
}: PlannerClientProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { canAccessLessons } = useLessonsAccess();
  const { data: lessonsSummaryData } = useQuery({
    queryKey: ["lessons-summary-by-subtema"],
    queryFn: () => api.lessons.summaryBySubtema(),
    enabled: canAccessLessons,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const lessonsSummaryBySubtema = lessonsSummaryData?.subtemas;
  const [currentPlan, setCurrentPlan] = useState<PlannerWeek[]>(plan);
  const [progress, setProgress] = useState<PlannerProgressMap>(initialProgress);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [topicProgress, setTopicProgress] = useState<PlannerTopicProgressMap>(initialTopicProgress);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showCalendarModal, setShowCalendarModal] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showInternatoModal, setShowInternatoModal] = useState(false);
  const [showCompletedOutside, setShowCompletedOutside] = useState(false);
  const [switchingOrg, setSwitchingOrg] = useState(false);
  const [exportingIcs, setExportingIcs] = useState(false);
  const [copiedFeed, setCopiedFeed] = useState(false);

  const scheduleMode: PlannerScheduleMode = `${organizationMode === "internato" ? "internato" : "geral"}_${isIntensive ? "intensive" : "standard"}`;

  // Estados para Drag & Drop e reordenação entre semanas
  const [draggedTopic, setDraggedTopic] = useState<{ week: number; subtema: string; index: number } | null>(null);
  const [dragOverWeek, setDragOverWeek] = useState<number | null>(null);
  const [dragOverTopicIndex, setDragOverTopicIndex] = useState<{ week: number; index: number } | null>(null);
  const [isMoving, setIsMoving] = useState(false);
  const [moveModalTopic, setMoveModalTopic] = useState<{ subtema: string; currentWeek: number; targetWeek: number } | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setCurrentPlan(plan);
    }, 0);
    return () => clearTimeout(timer);
  }, [plan]);

  const handleExportIcs = async () => {
    setExportingIcs(true);
    try {
      await api.planner.exportIcs();
      toast.success("Arquivo de calendário (.ics) gerado com sucesso!");
    } catch {
      toast.error("Erro ao exportar cronograma.");
    } finally {
      setExportingIcs(false);
    }
  };

  const handleCopyFeedUrl = async () => {
    try {
      const feedUrl = api.planner.getCalendarFeedUrl();
      await navigator.clipboard.writeText(feedUrl);
      setCopiedFeed(true);
      toast.success("URL do feed iCalendar copiada!");
      setTimeout(() => setCopiedFeed(false), 2000);
    } catch {
      toast.error("Não foi possível copiar a URL do feed.");
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      setProgress(initialProgress);
    }, 0);
    return () => clearTimeout(timer);
  }, [initialProgress]);

  useEffect(() => {
    const timer = setTimeout(() => setTopicProgress(initialTopicProgress), 0);
    return () => clearTimeout(timer);
  }, [initialTopicProgress]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showResetConfirm) setShowResetConfirm(false);
        if (showSettingsModal) setShowSettingsModal(false);
        if (showCalendarModal) setShowCalendarModal(false);
        if (showInternatoModal) setShowInternatoModal(false);
        if (moveModalTopic) setMoveModalTopic(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showResetConfirm, showSettingsModal, showCalendarModal, showInternatoModal, moveModalTopic]);

  useEffect(() => {
    const synced = (event: Event) => {
      const endpoint = (event as CustomEvent<{ endpoint?: string }>).detail?.endpoint;
      if (endpoint?.includes("/api/planner/")) router.refresh();
    };
    window.addEventListener("sync-item-success", synced);
    return () => window.removeEventListener("sync-item-success", synced);
  }, [router]);

  const handleMoveTopic = useCallback(async (
    subtema: string,
    sourceWeek: number,
    targetWeek: number,
    targetIndex?: number
  ) => {
    const sourceWeekObj = currentPlan.find(w => w.week === sourceWeek);
    const curIdx = sourceWeekObj?.topics.findIndex(t => t.subtema === subtema);

    // Evitar no-op quando solto na mesma posição dentro da mesma semana
    if (sourceWeek === targetWeek && targetIndex !== undefined && (curIdx === targetIndex || curIdx === targetIndex - 1)) {
      setDraggedTopic(null);
      setDragOverWeek(null);
      setDragOverTopicIndex(null);
      return;
    }

    const previousPlan = currentPlan;
    const previousTopicProgress = topicProgress;
    const effectiveTargetIndex =
      sourceWeek === targetWeek && targetIndex !== undefined && curIdx !== undefined && curIdx >= 0 && curIdx < targetIndex
        ? targetIndex - 1
        : targetIndex;
    let topicToMove: PlannerTopic | null = null;

    // 1. Atualizar currentPlan de forma otimista
    const newPlan = currentPlan.map(w => {
      if (w.week === sourceWeek) {
        const found = w.topics.find(t => t.subtema === subtema);
        if (found) topicToMove = found;
        const filtered = w.topics.filter(t => t.subtema !== subtema);
        const allocated = filtered.reduce((acc, t) => acc + (t.estimated_hours || 0), 0);
        return {
          ...w,
          topics: filtered,
          allocated_hours: Math.round(allocated * 10) / 10
        };
      }
      return w;
    }).map(w => {
      if (w.week === targetWeek && topicToMove) {
        const updatedTopics = [...w.topics];
        if (effectiveTargetIndex !== undefined && effectiveTargetIndex >= 0 && effectiveTargetIndex <= updatedTopics.length) {
          updatedTopics.splice(effectiveTargetIndex, 0, topicToMove);
        } else {
          updatedTopics.push(topicToMove);
        }
        const allocated = updatedTopics.reduce((acc, t) => acc + (t.estimated_hours || 0), 0);
        return {
          ...w,
          topics: updatedTopics,
          allocated_hours: Math.round(allocated * 10) / 10
        };
      }
      return w;
    });

    setCurrentPlan(newPlan);

    // 2. Atualizar topicProgress se mudou de semana
    if (sourceWeek !== targetWeek) {
      setTopicProgress(prev => {
        const wasCompleted = Boolean(prev[`${sourceWeek}:${subtema}`] || prev[subtema]);
        const nextProg = { ...prev };
        delete nextProg[`${sourceWeek}:${subtema}`];
        if (wasCompleted) {
          nextProg[`${targetWeek}:${subtema}`] = true;
          nextProg[subtema] = true;
        }
        return nextProg;
      });
    }

    setDraggedTopic(null);
    setDragOverWeek(null);
    setDragOverTopicIndex(null);

    // 3. Chamada de API com tratamento offline
    try {
      setIsMoving(true);
      await api.planner.moveTopic({
        subtema,
        source_week: sourceWeek,
        target_week: targetWeek,
        target_index: effectiveTargetIndex,
        mode: scheduleMode
      });
      toast.success(`"${subtema}" movido para a Semana ${targetWeek}!`);
    } catch (error) {
      if (error instanceof OfflineQueuedError) {
        toast("Alteração salva offline. Sincronizará ao reconectar.", { icon: "📶" });
        return;
      }
      setCurrentPlan(previousPlan);
      setTopicProgress(previousTopicProgress);
      toast.error("Erro ao mover tema de semana.");
    } finally {
      setIsMoving(false);
    }
  }, [currentPlan, topicProgress, scheduleMode]);

  const handleDragStart = useCallback((week: number, subtema: string, index: number, e: React.DragEvent) => {
    e.dataTransfer.setData("application/json", JSON.stringify({ week, subtema, index }));
    e.dataTransfer.effectAllowed = "move";
    setDraggedTopic({ week, subtema, index });
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedTopic(null);
    setDragOverWeek(null);
    setDragOverTopicIndex(null);
  }, []);

  const handleWeekDragOver = useCallback((e: React.DragEvent, weekNum: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverWeek((prev) => (prev === weekNum ? prev : weekNum));
  }, []);

  const handleWeekDrop = useCallback((e: React.DragEvent, targetWeek: number) => {
    e.preventDefault();
    let item = draggedTopic;
    if (!item) {
      try {
        const raw = e.dataTransfer.getData("application/json");
        if (raw) item = JSON.parse(raw);
      } catch {
        // fallback
      }
    }
    if (item) {
      void handleMoveTopic(item.subtema, item.week, targetWeek);
    }
    setDraggedTopic(null);
    setDragOverWeek(null);
    setDragOverTopicIndex(null);
  }, [draggedTopic, handleMoveTopic]);

  const handleTopicDragOver = useCallback((weekNum: number, topicIdx: number, e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "move";
    setDragOverTopicIndex((prev) =>
      prev?.week === weekNum && prev?.index === topicIdx
        ? prev
        : { week: weekNum, index: topicIdx }
    );
  }, []);

  const handleTopicDrop = useCallback((targetWeek: number, targetIdx: number, e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    let item = draggedTopic;
    if (!item) {
      try {
        const raw = e.dataTransfer.getData("application/json");
        if (raw) item = JSON.parse(raw);
      } catch {
        // fallback
      }
    }
    if (item) {
      void handleMoveTopic(item.subtema, item.week, targetWeek, targetIdx);
    }
    setDraggedTopic(null);
    setDragOverWeek(null);
    setDragOverTopicIndex(null);
  }, [draggedTopic, handleMoveTopic]);

  const handleOpenMoveModalTopic = useCallback((subtema: string, currentWeek: number) => {
    setMoveModalTopic({ subtema, currentWeek, targetWeek: currentWeek });
  }, []);

  const toggleTopic = useCallback(async (week: number, subtema: string, currentStatus: boolean) => {
    const key = `${week}:${subtema}`;
    const completed = !currentStatus;
    setTopicProgress(prev => {
      if (completed) {
        return { ...prev, [key]: true, [subtema]: true };
      }
      const next: PlannerTopicProgressMap = { ...prev };
      delete next[key];
      delete next[subtema];
      for (const k of Object.keys(next)) {
        if (k.endsWith(`:${subtema}`)) {
          delete next[k];
        }
      }
      return next;
    });
    try {
      await api.planner.markTopic(week, subtema, completed);
      void queryClient.invalidateQueries({ queryKey: ["planner-bundle"] });
    } catch (error) {
      if (error instanceof OfflineQueuedError) {
        toast("Alteração salva offline. Sincronizará ao reconectar.", { icon: "📶" });
        return;
      }
      setTopicProgress(prev => ({ ...prev, [key]: currentStatus, [subtema]: currentStatus }));
      toast.error("Erro ao salvar o tema concluído.");
    }
  }, [queryClient]);

  const handleResetScope = async (scope: "schedule" | "progress" | "all") => {
    setShowResetConfirm(false);
    setLoadingAction("reset");
    try {
      await api.planner.resetConfig({
        scope,
        mode: scope === "schedule" ? scheduleMode : undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["planner-bundle"] });
      if (scope === "schedule") {
        toast.success("Cronograma reorganizado mantendo suas aulas feitas!");
      } else if (scope === "progress") {
        toast.success("Aulas concluídas zeradas com sucesso.");
      } else {
        toast.success("Planner reiniciado por completo.");
      }
      router.refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erro ao reiniciar planner.";
      toast.error(message);
    } finally {
      setLoadingAction(null);
    }
  };

  const buildPlannerUrl = (intensiveVal: boolean, orgVal: PlannerOrganizationMode) => {
    const params = new URLSearchParams();
    if (intensiveVal) params.set("intensive", "true");
    params.set("org", orgVal);
    return `/planner?${params.toString()}`;
  };

  const handleToggleIntensive = () => {
    router.push(buildPlannerUrl(!isIntensive, organizationMode));
  };

  const handleSwitchOrganization = async (nextOrg: PlannerOrganizationMode) => {
    if (nextOrg === organizationMode || switchingOrg) return;
    setSwitchingOrg(true);
    try {
      if (config) {
        await api.planner.saveConfig({
          exam_date: config.exam_date,
          start_date: config.start_date,
          days_per_week: config.days_per_week,
          hours_per_day: config.hours_per_day,
          target_score: config.target_score,
          target_institution: config.target_institution,
          target_institutions: config.target_institutions,
          target_specialty: config.target_specialty,
          organization_mode: nextOrg,
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["planner-bundle"] });
      router.push(buildPlannerUrl(Boolean(isIntensive), nextOrg));
    } catch {
      toast.error("Erro ao trocar modo de organização.");
    } finally {
      setSwitchingOrg(false);
    }
  };

  const handleToggleStudy = async (week: number, currentStatus: boolean) => {
    const actionKey = `study-${week}`;
    if (loadingAction) return;
    setLoadingAction(actionKey);

    const newStatus = !currentStatus;
    // Optimistic UI
    setProgress(prev => ({
      ...prev,
      [week.toString()]: { ...prev[week.toString()], studied: newStatus, studied_at: newStatus ? new Date().toISOString() : null }
    }));

    try {
      await api.planner.markStudy(week, newStatus);
    } catch (error) {
      if (error instanceof OfflineQueuedError) {
        toast("Status salvo offline. Sincronizará ao reconectar.", { icon: "📶" });
        return;
      }
      toast.error("Erro ao salvar progresso.");
      // Revert on error
      setProgress(prev => ({
        ...prev,
        [week.toString()]: {
          ...prev[week.toString()],
          studied: currentStatus,
          studied_at: currentStatus ? prev[week.toString()]?.studied_at ?? null : null,
        }
      }));
    } finally {
      setLoadingAction(null);
    }
  };

  const [todayTimestamp] = useState(() => Date.now());
  const visibleCompletedOutside = completedTopicsOutside.filter(
    (t) => Boolean(topicProgress[t.subtema])
  );
  const scheduledTopicsCount = currentPlan.reduce((total, week) => total + week.topics.length, 0);
  const completedInScheduleCount = currentPlan.reduce(
    (total, week) =>
      total +
      week.topics.filter(
        (t) => Boolean(topicProgress[`${week.week}:${t.subtema}`]) || Boolean(topicProgress[t.subtema])
      ).length,
    0
  );
  const totalTopics = scheduledTopicsCount + visibleCompletedOutside.length;
  const completedTopics = completedInScheduleCount + visibleCompletedOutside.length;
  const defaultWeeklyHours = Math.min(168, (config?.days_per_week || 6) * (config?.hours_per_day || 2));

  const areaDistribution = useMemo(() => {
    const order = [
      "Clínica Médica",
      "Cirurgia",
      "Ginecologia e Obstetrícia",
      "Pediatria",
      "Preventiva",
    ];
    const stats = new Map<string, { total: number; completed: number }>();
    for (const area of order) stats.set(area, { total: 0, completed: 0 });
    for (const week of currentPlan) {
      for (const t of week.topics) {
        const entry = stats.get(t.area) ?? { total: 0, completed: 0 };
        entry.total += 1;
        if (Boolean(topicProgress[`${week.week}:${t.subtema}`]) || Boolean(topicProgress[t.subtema])) {
          entry.completed += 1;
        }
        stats.set(t.area, entry);
      }
    }
    return Array.from(stats.entries())
      .filter(([, v]) => v.total > 0)
      .map(([area, v]) => ({
        area,
        shortLabel: area === "Ginecologia e Obstetrícia" ? "GO" : area,
        total: v.total,
        completed: v.completed,
        pct: scheduledTopicsCount > 0 ? Math.round((v.total / scheduledTopicsCount) * 100) : 0,
      }));
  }, [currentPlan, topicProgress, scheduledTopicsCount]);

  return (
    <>
    <div className="flex flex-col gap-6 pb-12">
      {warning && !isIntensive && (
        <div className="bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 p-4 rounded-xl flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
          <div className="flex gap-3">
            <AlertTriangle className="shrink-0 mt-0.5" size={20} />
            <div>
              <p className="font-semibold text-sm">Alerta de Tempo</p>
              <p className="text-sm opacity-90">{warning}</p>
            </div>
          </div>
          <button 
            onClick={handleToggleIntensive}
            className="shrink-0 bg-amber-500 text-white font-medium px-4 py-2 rounded-lg text-sm flex items-center gap-2 hover:bg-amber-600 transition-colors"
          >
            <Zap size={16} /> Ativar Plano Intensivo
          </button>
        </div>
      )}

      {isIntensive && (
        <div className="bg-primary/10 border border-primary/20 text-primary p-4 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Zap className="shrink-0" size={20} />
            <p className="text-sm font-medium">Modo Intensivo Ativado: Exibindo apenas temas de Alto Rendimento.</p>
          </div>
          <button 
            onClick={handleToggleIntensive}
            className="text-xs font-medium hover:underline opacity-80"
          >
            Voltar ao plano normal
          </button>
        </div>
      )}

      <div className="mq-page-hero p-5 sm:p-6 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between mb-2 gap-4">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-ink-primary flex items-center gap-2">
            <CalendarDays className="text-accent" size={28} />
            Seu Cronograma de Estudos
          </h2>
          <p className="text-ink-secondary text-sm">Cronograma estruturado por carga, cobertura e temas de alta incidência. Arraste matérias para mover entre semanas.</p>
          {config?.target_institution && (
            <div className="flex items-center gap-1.5 text-xs text-ink-secondary mt-1.5 flex-wrap">
              {config.target_institution.split(",").map((instName, idx) => (
                <span key={idx} className="font-bold bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-md">
                  {instName.trim()}
                </span>
              ))}
              {config.target_specialty && (
                <>
                  <span>•</span>
                  <span><strong className="text-ink-primary">Especialidade:</strong> {config.target_specialty}</span>
                </>
              )}
              {config.target_score && (
                <>
                  <span>•</span>
                  <span><strong className="text-ink-primary">Meta:</strong> {config.target_score}%</span>
                </>
              )}
              {config.days_per_week && config.hours_per_day && (
                <>
                  <span>•</span>
                  <span>{config.days_per_week} dias/sem ({config.hours_per_day}h/dia)</span>
                </>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 sm:gap-4 w-full sm:w-auto flex-wrap justify-between sm:justify-end">
          <div className="flex-1 sm:w-44">
            <div className="flex justify-between text-[11px] uppercase tracking-wider font-semibold mb-1">
              <span className="text-ink-muted">Temas concluídos</span>
              <span className="text-primary">{completedTopics} / {totalTopics}</span>
            </div>
            <div className="h-2 w-full bg-elevated rounded-full overflow-hidden ring-1 ring-inset ring-black/5 dark:ring-white/5">
              <div 
                className="h-full bg-primary transition-all duration-500 shadow-inner" 
                style={{ width: `${(completedTopics / Math.max(1, totalTopics)) * 100}%` }}
              />
            </div>
          </div>
          <div
            role="group"
            aria-label="Organização do cronograma"
            className="inline-flex items-center rounded-lg border border-line-subtle bg-elevated p-0.5 shadow-sm"
          >
            <button
              type="button"
              disabled={switchingOrg}
              onClick={() => void handleSwitchOrganization("geral")}
              aria-pressed={organizationMode === "geral"}
              className={clsx(
                "flex items-center gap-1.5 min-h-[34px] text-xs font-semibold px-2.5 py-1 rounded-md transition-colors cursor-pointer",
                organizationMode === "geral"
                  ? "bg-surface text-primary shadow-2xs"
                  : "text-ink-secondary hover:text-ink-primary"
              )}
            >
              <Layers size={14} />
              Geral (Misturado)
            </button>
            <button
              type="button"
              disabled={switchingOrg}
              onClick={() => void handleSwitchOrganization("internato")}
              aria-pressed={organizationMode === "internato"}
              className={clsx(
                "flex items-center gap-1.5 min-h-[34px] text-xs font-semibold px-2.5 py-1 rounded-md transition-colors cursor-pointer",
                organizationMode === "internato"
                  ? "bg-surface text-primary shadow-2xs"
                  : "text-ink-secondary hover:text-ink-primary"
              )}
            >
              <CalendarRange size={14} />
              Por Bloco do Internato
            </button>
          </div>
          {organizationMode === "internato" && (
            <button
              type="button"
              onClick={() => setShowInternatoModal(true)}
              aria-haspopup="dialog"
              aria-expanded={showInternatoModal}
              className="flex items-center gap-1.5 min-h-[38px] text-xs sm:text-sm font-semibold text-ink-primary bg-surface hover:bg-elevated border border-line-subtle px-3 py-1.5 rounded-lg transition-colors shadow-sm cursor-pointer"
              title="Editar datas e áreas dos rodízios do internato"
            >
              <CalendarRange size={15} className="text-primary" />
              Blocos
            </button>
          )}
          <button
            type="button"
            onClick={handleToggleIntensive}
            aria-pressed={isIntensive}
            title="Filtrar o cronograma para exibir apenas temas prioritários de alta incidência"
            className={`flex items-center gap-1.5 min-h-[38px] text-xs sm:text-sm font-semibold px-3 py-1.5 rounded-lg border transition-colors shadow-sm cursor-pointer ${
              isIntensive
                ? "bg-warning/15 text-warning border-warning/40"
                : "bg-surface text-ink-primary border-line-subtle hover:bg-elevated"
            }`}
          >
            <Zap size={15} />
            {isIntensive ? "Reta Final: Ativa" : "Modo Reta Final"}
          </button>
          <button 
            type="button"
            onClick={() => setShowSettingsModal(true)}
            aria-haspopup="dialog"
            aria-expanded={showSettingsModal}
            className="flex items-center gap-1.5 min-h-[38px] text-xs sm:text-sm font-semibold text-primary bg-primary/10 hover:bg-primary/20 border border-primary/25 px-3 py-1.5 rounded-lg transition-colors shadow-sm cursor-pointer"
          >
            <Settings2 size={15} />
            Calibrar Perfil
          </button>
          <button 
            type="button"
            onClick={() => setShowCalendarModal(true)}
            aria-haspopup="dialog"
            aria-expanded={showCalendarModal}
            className="flex items-center gap-1.5 min-h-[38px] text-xs sm:text-sm font-medium text-ink-primary bg-elevated hover:bg-elevated/80 px-2.5 py-1.5 rounded-lg border border-line-subtle transition-colors shadow-sm cursor-pointer"
            title="Sincronizar cronograma com Google Agenda, Apple Calendar ou baixar arquivo .ics"
          >
            <CalendarDays size={15} className="text-primary" />
            Sincronizar com Agenda
          </button>
          <button 
            type="button"
            onClick={() => setShowResetConfirm(true)}
            disabled={loadingAction === "reset"}
            aria-haspopup="dialog"
            aria-expanded={showResetConfirm}
            className="flex items-center gap-1.5 min-h-[38px] text-xs sm:text-sm font-medium text-ink-secondary hover:text-ink-primary bg-elevated hover:bg-elevated/80 px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
          >
            {loadingAction === "reset" ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
            Refazer
          </button>
        </div>
      </div>

      {areaDistribution.length > 0 && (
        <div className="bg-surface border border-line-subtle rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between gap-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {areaDistribution.map((item) => (
              <div key={item.area} className="inline-flex items-center gap-1.5">
                <span className={clsx("w-2 h-2 rounded-full shrink-0", getAreaColorClass(item.area).split(" ")[0])} />
                <span className="font-semibold text-ink-primary">{item.shortLabel}</span>
                <span className="font-mono-lab text-ink-secondary tabular-nums">
                  {item.completed}/{item.total}
                </span>
                <span className="text-[11px] text-ink-muted tabular-nums">({item.pct}%)</span>
              </div>
            ))}
          </div>
          {organizationMode === "geral" && (
            <span className="text-[11px] text-ink-muted">
              Rodízio ponderado das 5 áreas • High-Yield + Essenciais do Internato
            </span>
          )}
        </div>
      )}

      {visibleCompletedOutside.length > 0 && (
        <div className="bg-surface border border-line-subtle rounded-xl overflow-hidden shadow-1">
          <button
            type="button"
            onClick={() => setShowCompletedOutside((prev) => !prev)}
            aria-expanded={showCompletedOutside}
            className="w-full px-5 py-3.5 flex items-center justify-between gap-3 hover:bg-elevated/50 transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-2.5 text-left">
              <CheckCircle2 size={18} className="text-success shrink-0" />
              <div>
                <span className="text-sm font-bold text-ink-primary">
                  Temas já concluídos ({visibleCompletedOutside.length})
                </span>
                <p className="text-xs text-ink-secondary">
                  Mantidos fora das semanas futuras para não poluir sua carga semanal pendente.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-ink-secondary shrink-0">
              {showCompletedOutside ? "Recolher" : "Ver lista"}
              {showCompletedOutside ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </span>
          </button>
          {showCompletedOutside && (
            <div className="px-5 pb-4 pt-1 border-t border-line-subtle divide-y divide-line-subtle/60">
              {visibleCompletedOutside.map((t) => (
                <div key={t.subtema} className="py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-muted-foreground line-through block truncate">
                      {t.subtema}
                    </span>
                    <span className={clsx("text-xs font-medium", getAreaColorClass(t.area).split(" ")[1])}>
                      {t.area}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void toggleTopic(0, t.subtema, true)}
                    className="shrink-0 text-xs font-semibold px-2.5 py-1 rounded-md border border-line-subtle bg-elevated hover:bg-elevated/80 text-ink-secondary hover:text-ink-primary transition-colors cursor-pointer"
                    title="Desmarcar conclusão (reorganize o cronograma para reagendar)"
                  >
                    Desmarcar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="space-y-4">
        {currentPlan.map((week) => (
          <PlannerWeekCard
            key={week.week}
            week={week}
            weekProgress={
              progress[week.week.toString()] || {
                studied: false,
                rev24h: false,
                rev7d: false,
                rev30d: false,
              }
            }
            topicProgress={topicProgress}
            todayTimestamp={todayTimestamp}
            organizationMode={organizationMode}
            draggedTopic={draggedTopic}
            dragOverWeek={dragOverWeek}
            dragOverTopicIndex={dragOverTopicIndex}
            loadingAction={loadingAction}
            canAccessLessons={canAccessLessons}
            lessonsSummaryBySubtema={lessonsSummaryBySubtema}
            toggleTopic={toggleTopic}
            handleToggleStudy={handleToggleStudy}
            handleWeekDragOver={handleWeekDragOver}
            handleWeekDrop={handleWeekDrop}
            handleDragStart={handleDragStart}
            handleDragEnd={handleDragEnd}
            handleTopicDragOver={handleTopicDragOver}
            handleTopicDrop={handleTopicDrop}
            handleOpenMoveModalTopic={handleOpenMoveModalTopic}
          />
        ))}
      </div>
    </div>

      <PlannerModals
        config={config}
        currentPlan={currentPlan}
        defaultWeeklyHours={defaultWeeklyHours}
        showResetConfirm={showResetConfirm}
        showInternatoModal={showInternatoModal}
        showSettingsModal={showSettingsModal}
        showCalendarModal={showCalendarModal}
        moveModalTopic={moveModalTopic}
        exportingIcs={exportingIcs}
        copiedFeed={copiedFeed}
        isMoving={isMoving}
        onCloseResetConfirm={() => setShowResetConfirm(false)}
        onResetScope={handleResetScope}
        onCloseInternatoModal={() => setShowInternatoModal(false)}
        onSavedInternato={() => {
          void queryClient.invalidateQueries({ queryKey: ["planner-bundle"] });
          router.refresh();
        }}
        onCloseSettingsModal={() => setShowSettingsModal(false)}
        onCloseCalendarModal={() => setShowCalendarModal(false)}
        onExportIcs={() => void handleExportIcs()}
        onCopyFeedUrl={() => void handleCopyFeedUrl()}
        onChangeMoveTargetWeek={(targetWeek) =>
          setMoveModalTopic((prev) => (prev ? { ...prev, targetWeek } : null))
        }
        onCloseMoveModal={() => setMoveModalTopic(null)}
        onConfirmMoveTopic={handleMoveTopic}
      />
    </>
  );
}
