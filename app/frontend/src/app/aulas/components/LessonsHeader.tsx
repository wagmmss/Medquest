"use client";

import clsx from "clsx";
import {
  BookOpen,
  Calendar,
  PlayCircle,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { DEFAULT_LESSON_POST_QUESTIONS, DEFAULT_LESSON_PRE_QUESTIONS } from "@/lib/themeJourney";
import {
  type AreaPill,
  type MedcofGroupMode,
  type StatusFilter,
  type ViewTab,
  VIEW_TABS,
  formatDuration,
  getAreaDotClass,
  getShortAreaLabel,
} from "../lessonHelpers";

export interface AreaPillStat {
  area: string;
  completed: number;
  total: number;
}

export function LessonsHeader({
  activeTab,
  onSelectTab,
  hasData,
  headerStats,
  searchText,
  onChangeSearch,
  statusFilter,
  onChangeStatusFilter,
  medcofGroupMode,
  onChangeMedcofGroupMode,
  activeAreaPill,
  onSelectAreaPill,
  areaPillStats,
  currentWeek,
  currentWeekStats,
  paramSubtema,
  onClearSubtema,
  defaultPreQuestions,
  defaultPostQuestions,
  showCycleSettings,
  onToggleCycleSettings,
  draftCyclePre,
  onChangeDraftCyclePre,
  draftCyclePost,
  onChangeDraftCyclePost,
  savingCycle,
  onSaveCycleSettings,
}: {
  activeTab: ViewTab;
  onSelectTab: (tab: ViewTab) => void;
  hasData: boolean;
  headerStats: {
    total: number;
    completed: number;
    remainingSeconds: number;
    labelSuffix: string;
  };
  searchText: string;
  onChangeSearch: (value: string) => void;
  statusFilter: StatusFilter;
  onChangeStatusFilter: (value: StatusFilter) => void;
  medcofGroupMode: MedcofGroupMode;
  onChangeMedcofGroupMode: (value: MedcofGroupMode) => void;
  activeAreaPill: AreaPill;
  onSelectAreaPill: (pill: AreaPill) => void;
  areaPillStats: AreaPillStat[];
  currentWeek: number | null;
  currentWeekStats: { total: number; completed: number; remainingSeconds: number };
  paramSubtema: string;
  onClearSubtema: () => void;
  defaultPreQuestions: number;
  defaultPostQuestions: number;
  showCycleSettings: boolean;
  onToggleCycleSettings: () => void;
  draftCyclePre: string;
  onChangeDraftCyclePre: (value: string) => void;
  draftCyclePost: string;
  onChangeDraftCyclePost: (value: string) => void;
  savingCycle: boolean;
  onSaveCycleSettings: (overridePre?: number, overridePost?: number) => void;
}) {
  const headerRemainingFormatted = formatDuration(headerStats.remainingSeconds);
  const hasSearch = searchText.trim().length > 0;
  const showAreaPills =
    !paramSubtema &&
    (activeTab === "trilha_r1"
      ? areaPillStats.length > 0 || currentWeek !== null
      : areaPillStats.length > 1);

  return (
    <section className="rounded-md border border-line-subtle bg-surface p-4 space-y-3">
      {/* Linha 1: Título + Progresso | Abas + Engrenagem Ciclo */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5 min-w-0">
          <PlayCircle className="w-5 h-5 text-accent shrink-0" />
          <h1 className="text-lg font-bold text-ink-primary tracking-tight">
            Videoteca de Aulas
          </h1>
          {hasData && (
            <span className="text-[11px] font-mono-lab px-2 py-0.5 rounded-xs bg-canvas text-ink-secondary border border-line-subtle tabular-nums">
              {headerStats.completed}/{headerStats.total} {headerStats.labelSuffix}
              {headerRemainingFormatted ? ` • ${headerRemainingFormatted}` : ""}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 self-start lg:self-auto">
          <div className="inline-flex flex-wrap gap-1 bg-canvas p-1 rounded-md border border-line-subtle">
            {VIEW_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => onSelectTab(tab.key)}
                className={clsx(
                  "px-2.5 py-1 rounded-xs text-xs font-semibold transition-colors cursor-pointer",
                  activeTab === tab.key
                    ? "bg-primary text-primary-foreground shadow-2xs"
                    : "text-ink-secondary hover:text-ink-primary hover:bg-elevated"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === "trilha_r1" && (
            <button
              type="button"
              onClick={onToggleCycleSettings}
              aria-expanded={showCycleSettings}
              aria-label="Configurar padrão do ciclo de estudo"
              title={`Configurar ciclo (${defaultPreQuestions}q → Aula → ${defaultPostQuestions}q)`}
              className={clsx(
                "p-2 rounded-md border transition-colors cursor-pointer",
                showCycleSettings
                  ? "bg-accent/15 text-accent border-accent/35"
                  : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
              )}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Painel recolhível de configuração do Ciclo Medway */}
      {activeTab === "trilha_r1" && showCycleSettings && (
        <div className="rounded-md border border-accent/30 bg-canvas p-3 flex flex-col lg:flex-row lg:items-center justify-between gap-3 text-xs">
          <div className="space-y-0.5">
            <p className="font-bold text-ink-primary">
              Padrão do Ciclo Medway ({defaultPreQuestions}q → Aula → {defaultPostQuestions}q)
            </p>
            <p className="text-[11px] text-ink-secondary">
              Questões antes da aula (pré-teste) e depois da aula (fixação). Padrão: 5 pré e 25 pós.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-1.5 text-ink-secondary">
              <span>Pré:</span>
              <input
                type="number"
                min={0}
                max={30}
                value={draftCyclePre}
                onChange={(e) => onChangeDraftCyclePre(e.target.value)}
                className="w-14 px-2 py-1 rounded-xs border border-line-subtle bg-surface font-mono-lab text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <span>q</span>
            </label>
            <label className="inline-flex items-center gap-1.5 text-ink-secondary">
              <span>Pós:</span>
              <input
                type="number"
                min={1}
                max={100}
                value={draftCyclePost}
                onChange={(e) => onChangeDraftCyclePost(e.target.value)}
                className="w-14 px-2 py-1 rounded-xs border border-line-subtle bg-surface font-mono-lab text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <span>q</span>
            </label>
            <button
              type="button"
              disabled={savingCycle}
              onClick={() => onSaveCycleSettings()}
              className="px-3 py-1 rounded-xs bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
            >
              Salvar
            </button>
            <button
              type="button"
              disabled={savingCycle}
              onClick={() =>
                onSaveCycleSettings(
                  DEFAULT_LESSON_PRE_QUESTIONS,
                  DEFAULT_LESSON_POST_QUESTIONS
                )
              }
              className="px-2.5 py-1 rounded-xs border border-line-subtle bg-surface hover:bg-elevated text-ink-secondary font-medium cursor-pointer"
            >
              5 / 25
            </button>
          </div>
        </div>
      )}

      {/* Linha 2: Busca + Status (+ Modo MedCof quando aplicável) */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-3.5 h-3.5 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchText}
            onChange={(e) => onChangeSearch(e.target.value)}
            placeholder={
              activeTab === "trilha_r1"
                ? "Buscar tema, aula ou módulo em todas as áreas..."
                : "Buscar aula ou módulo..."
            }
            className="w-full pl-8 pr-8 py-1.5 rounded-md border border-line-subtle bg-canvas text-xs text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />
          {searchText && (
            <button
              type="button"
              onClick={() => onChangeSearch("")}
              aria-label="Limpar busca"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <select
          value={statusFilter}
          onChange={(e) => onChangeStatusFilter(e.target.value as StatusFilter)}
          aria-label="Filtrar por status"
          className="px-2.5 py-1.5 rounded-md border border-line-subtle bg-canvas text-xs text-ink-primary focus:outline-none focus:ring-1 focus:ring-accent"
        >
          <option value="all">Todos os status</option>
          <option value="pending">Pendentes</option>
          <option value="in_progress">Em andamento</option>
          <option value="completed">Concluídas</option>
        </select>

        {activeTab === "medcof_r1_2026" && (
          <div className="inline-flex rounded-md border border-line-subtle bg-canvas p-0.5">
            {(
              [
                { key: "area_tema", label: "Por Tema" },
                { key: "bloco", label: "Por Bloco" },
              ] as const
            ).map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => onChangeMedcofGroupMode(m.key)}
                className={clsx(
                  "px-2.5 py-1 rounded-xs text-[11px] font-semibold transition-colors cursor-pointer",
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

      {/* Pílulas de Área (e Semana Atual na Trilha R1) */}
      {showAreaPills && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 pt-0.5">
          {activeTab === "trilha_r1" && currentWeek !== null && (
            <button
              type="button"
              onClick={() => onSelectAreaPill("current_week")}
              className={clsx(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors cursor-pointer shrink-0",
                !hasSearch && activeAreaPill === "current_week"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
              )}
            >
              <Calendar className="w-3 h-3" />
              <span>Semana {currentWeek}</span>
              {currentWeekStats.total > 0 && (
                <span className="font-mono-lab text-[10px] opacity-80">
                  {currentWeekStats.completed}/{currentWeekStats.total}
                </span>
              )}
            </button>
          )}

          {activeTab !== "trilha_r1" && (
            <button
              type="button"
              onClick={() => onSelectAreaPill("all")}
              className={clsx(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors cursor-pointer shrink-0",
                !hasSearch && activeAreaPill === "all"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
              )}
            >
              Todas
            </button>
          )}

          {areaPillStats.map((item) => {
            const isActive = !hasSearch && activeAreaPill === item.area;
            return (
              <button
                key={item.area}
                type="button"
                onClick={() => onSelectAreaPill(item.area)}
                className={clsx(
                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors cursor-pointer shrink-0",
                  isActive
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
                )}
              >
                <span
                  className={clsx(
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    isActive ? "bg-primary-foreground" : getAreaDotClass(item.area)
                  )}
                />
                <span>{getShortAreaLabel(item.area)}</span>
                {item.total > 0 && (
                  <span className="font-mono-lab text-[10px] opacity-75">
                    {item.completed}/{item.total}
                  </span>
                )}
              </button>
            );
          })}

          {activeTab === "trilha_r1" && (
            <button
              type="button"
              onClick={() => onSelectAreaPill("all")}
              className={clsx(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors cursor-pointer shrink-0",
                !hasSearch && activeAreaPill === "all"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-canvas text-ink-secondary border-line-subtle hover:text-ink-primary hover:bg-elevated"
              )}
            >
              Todas
            </button>
          )}

          {hasSearch && activeTab === "trilha_r1" && (
            <span className="text-[11px] text-accent font-medium whitespace-nowrap ml-1">
              • Buscando em todas as áreas
            </span>
          )}
        </div>
      )}

      {paramSubtema && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded-md bg-accent/10 border border-accent/25 text-xs">
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen className="w-3.5 h-3.5 text-accent shrink-0" />
            <span className="text-ink-secondary">Tema:</span>
            <span className="font-semibold text-ink-primary truncate">{paramSubtema}</span>
          </div>
          <button
            type="button"
            onClick={onClearSubtema}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs bg-surface border border-line-subtle text-ink-secondary hover:text-ink-primary cursor-pointer"
          >
            <X className="w-3 h-3" /> Ver catálogo
          </button>
        </div>
      )}
    </section>
  );
}
