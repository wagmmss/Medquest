"use client";

import { useState } from "react";
import { X, Plus, Trash2, CalendarRange, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import type { InternatoBlock, InternatoWeekPatternMode, InternatoWeekdayKey } from "@/types/api";
import { api } from "@/lib/api";
import { AREAS_MEDQUEST, WEEKDAY_CHIPS } from "@/lib/sixYear/staticData";
import toast from "react-hot-toast";
import clsx from "clsx";

const PATTERN_CYCLE: InternatoWeekPatternMode[] = ["integral", "meio_periodo", "folga"];
const PATTERN_LABELS: Record<InternatoWeekPatternMode, string> = {
  integral: "Integral",
  meio_periodo: "Meio per.",
  folga: "Folga",
};

function slugifyId(raw: string, fallbackIndex: number): string {
  const cleaned = raw
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
  return cleaned || `bloco_${fallbackIndex + 1}`;
}

interface InternatoBlocksModalProps {
  initialBlocks: InternatoBlock[];
  defaultWeeklyHours?: number;
  onClose: () => void;
  onSaved: (blocks: InternatoBlock[]) => void;
}

export function InternatoBlocksModal({
  initialBlocks,
  defaultWeeklyHours = 12,
  onClose,
  onSaved,
}: InternatoBlocksModalProps) {
  const [blocks, setBlocks] = useState<InternatoBlock[]>(() =>
    initialBlocks.length > 0
      ? initialBlocks.map((b) => ({ ...b }))
      : [{ id: "cirurgia", start: "2027-01-25", end: "2027-02-21", area: "Cirurgia", label: "Cirurgia Geral" }]
  );
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const handleUpdateBlock = <K extends keyof InternatoBlock>(
    index: number,
    field: K,
    value: InternatoBlock[K]
  ) => {
    setBlocks((prev) =>
      prev.map((block, idx) => (idx === index ? { ...block, [field]: value } : block))
    );
  };

  const handleToggleAncoraArea = (index: number, area: string) => {
    setBlocks((prev) =>
      prev.map((block, idx) => {
        if (idx !== index) return block;
        const current = block.ancora_areas ?? [];
        const next = current.includes(area)
          ? current.filter((a) => a !== area)
          : [...current, area];
        return { ...block, ancora_areas: next };
      })
    );
  };

  const handleCycleDayPattern = (index: number, dayKey: InternatoWeekdayKey) => {
    setBlocks((prev) =>
      prev.map((block, idx) => {
        if (idx !== index) return block;
        const current = { ...(block.week_pattern ?? {}) };
        const defaultMode: InternatoWeekPatternMode =
          dayKey === "sab" || dayKey === "dom" ? "folga" : "integral";
        const cur = current[dayKey] ?? defaultMode;
        const next = PATTERN_CYCLE[(PATTERN_CYCLE.indexOf(cur) + 1) % PATTERN_CYCLE.length];
        return { ...block, week_pattern: { ...current, [dayKey]: next } };
      })
    );
  };

  const handleAddBlock = () => {
    const last = blocks[blocks.length - 1];
    const defaultStart = last?.end || new Date().toISOString().slice(0, 10);
    setBlocks((prev) => [
      ...prev,
      { start: defaultStart, end: defaultStart, area: "Clínica Médica", label: "" },
    ]);
  };

  const handleRemoveBlock = (index: number) => {
    setBlocks((prev) => prev.filter((_, idx) => idx !== index));
    if (expandedIdx === index) setExpandedIdx(null);
  };

  const handleSave = async () => {
    const valid = blocks.every((b) => b.start && b.end && b.area && b.start <= b.end);
    if (!valid) {
      toast.error("Verifique as datas dos blocos: a data inicial deve ser menor ou igual à final.");
      return;
    }

    // Preserva campos originais via spread e aplica saneamento dos campos editados
    const sanitized: InternatoBlock[] = blocks.map((b, idx) => {
      const item: InternatoBlock = {
        ...b,
        id: b.id || slugifyId(b.label || b.area, idx),
        start: b.start,
        end: b.end,
        area: b.area,
      };
      if (b.label && b.label.trim()) {
        item.label = b.label.trim();
      } else {
        delete item.label;
      }
      if (b.hours_per_week != null && Number.isFinite(Number(b.hours_per_week)) && Number(b.hours_per_week) >= 1) {
        item.hours_per_week = Number(b.hours_per_week);
      } else {
        delete item.hours_per_week;
      }
      if (typeof b.ancora70 === "string") {
        const trimmed = b.ancora70.trim();
        if (trimmed) item.ancora70 = trimmed;
        else delete item.ancora70;
      }
      if (typeof b.trilha30 === "string") {
        const trimmed = b.trilha30.trim();
        if (trimmed) item.trilha30 = trimmed;
        else delete item.trilha30;
      }
      if (typeof b.micro_habito === "string") {
        const trimmed = b.micro_habito.trim();
        if (trimmed) item.micro_habito = trimmed;
        else delete item.micro_habito;
      }
      if (Array.isArray(b.procedimentos_alvo)) {
        const cleanProcs = b.procedimentos_alvo.map((p) => p.trim()).filter(Boolean);
        if (cleanProcs.length > 0) item.procedimentos_alvo = cleanProcs;
        else delete item.procedimentos_alvo;
      }
      if (Array.isArray(b.ancora_areas) && b.ancora_areas.length === 0) {
        delete item.ancora_areas;
      }
      if (b.week_pattern && Object.keys(b.week_pattern).length === 0) {
        delete item.week_pattern;
      }
      return item;
    });

    setSaving(true);
    try {
      const res = await api.planner.saveInternatoBlocks(sanitized);
      toast.success("Blocos do internato atualizados!");
      onSaved(res.internato_blocks || sanitized);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar blocos do internato.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="internato-blocks-modal-title"
        className="relative bg-surface border border-line-subtle rounded-2xl shadow-2xl p-6 max-w-4xl w-full max-h-[88dvh] flex flex-col z-10 animate-in fade-in zoom-in-95 duration-200"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <CalendarRange size={20} />
            </div>
            <div>
              <h3 id="internato-blocks-modal-title" className="text-lg font-bold text-ink-primary">
                Blocos do Internato
              </h3>
              <p className="text-xs text-ink-secondary">
                Defina datas, área-âncora (~70% da semana + ~30% trilha paralela), carga opcional ({defaultWeeklyHours}h padrão) e metadados do 6º Ano.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar modal de blocos do internato"
            className="p-1.5 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-full hover:bg-elevated text-ink-muted cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
          {blocks.map((block, index) => {
            const isExpanded = expandedIdx === index;
            const resolvedId = block.id || slugifyId(block.label || block.area, index);
            return (
              <div
                key={index}
                className="p-3 rounded-xl bg-elevated/60 border border-line-subtle space-y-3"
              >
                <div className="grid grid-cols-1 sm:grid-cols-[0.95fr_0.95fr_1.15fr_1fr_0.65fr_auto] gap-2 items-center">
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                      Início
                    </label>
                    <input
                      type="date"
                      value={block.start}
                      onChange={(e) => handleUpdateBlock(index, "start", e.target.value)}
                      className="w-full px-2 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                      Fim
                    </label>
                    <input
                      type="date"
                      value={block.end}
                      onChange={(e) => handleUpdateBlock(index, "end", e.target.value)}
                      className="w-full px-2 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                      Área-Âncora
                    </label>
                    <select
                      value={block.area}
                      onChange={(e) => handleUpdateBlock(index, "area", e.target.value)}
                      className="w-full px-2 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    >
                      {AREAS_MEDQUEST.map((area) => (
                        <option key={area} value={area}>
                          {area === "Geral" ? "Geral (Equilibrado)" : area}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                      Rótulo
                    </label>
                    <input
                      type="text"
                      placeholder={block.area}
                      value={block.label ?? ""}
                      onChange={(e) => handleUpdateBlock(index, "label", e.target.value)}
                      className="w-full px-2 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                      h/sem
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={80}
                      step={1}
                      placeholder={`${defaultWeeklyHours}h`}
                      value={block.hours_per_week ?? ""}
                      onChange={(e) => {
                        const val = e.target.value.trim();
                        handleUpdateBlock(index, "hours_per_week", val === "" ? null : Number(val));
                      }}
                      className="w-full px-2 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                    />
                  </div>
                  <div className="flex items-center gap-1 mt-4 sm:mt-5">
                    <button
                      type="button"
                      onClick={() => setExpandedIdx(isExpanded ? null : index)}
                      title="Detalhes 6º Ano"
                      aria-label={`Detalhes 6º Ano do bloco ${index + 1}`}
                      className="p-2 rounded-lg text-ink-secondary hover:text-ink-primary hover:bg-surface transition-colors cursor-pointer"
                    >
                      {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveBlock(index)}
                      title="Remover bloco"
                      aria-label={`Remover bloco ${index + 1}`}
                      className="p-2 rounded-lg text-ink-muted hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="pt-3 border-t border-line-subtle space-y-3">
                    <div className="text-[11px] font-mono text-ink-muted">
                      ID (somente leitura): <strong className="text-ink-primary">{resolvedId}</strong>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                          Âncora 70%
                        </label>
                        <input
                          type="text"
                          value={block.ancora70 ?? ""}
                          onChange={(e) => handleUpdateBlock(index, "ancora70", e.target.value)}
                          placeholder="Temas prioritários do rodízio"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                          Trilha 30%
                        </label>
                        <input
                          type="text"
                          value={block.trilha30 ?? ""}
                          onChange={(e) => handleUpdateBlock(index, "trilha30", e.target.value)}
                          placeholder="Trilha paralela de revisão"
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                        Micro-hábito
                      </label>
                      <input
                        type="text"
                        value={block.micro_habito ?? ""}
                        onChange={(e) => handleUpdateBlock(index, "micro_habito", e.target.value)}
                        placeholder="Hábito clínico do rodízio"
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                      />
                    </div>

                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                        Procedimentos-alvo (um por linha)
                      </label>
                      <textarea
                        rows={2}
                        value={(block.procedimentos_alvo ?? []).join("\n")}
                        onChange={(e) =>
                          handleUpdateBlock(
                            index,
                            "procedimentos_alvo",
                            e.target.value.split("\n")
                          )
                        }
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                      />
                    </div>

                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1.5">
                        Áreas-âncora (para saldo 70/30)
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {AREAS_MEDQUEST.filter((a) => a !== "Geral").map((area) => {
                          const active = (block.ancora_areas ?? []).includes(area);
                          return (
                            <button
                              key={area}
                              type="button"
                              onClick={() => handleToggleAncoraArea(index, area)}
                              className={clsx(
                                "px-2 py-1 rounded-lg border text-[11px] font-semibold cursor-pointer",
                                active
                                  ? "bg-primary text-primary-foreground border-primary"
                                  : "bg-surface text-ink-secondary border-line-subtle"
                              )}
                            >
                              {area}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1.5">
                        Padrão semanal do rodízio (clique para alternar)
                      </div>
                      <div className="grid grid-cols-7 gap-1">
                        {WEEKDAY_CHIPS.map((wd) => {
                          const def: InternatoWeekPatternMode =
                            wd.key === "sab" || wd.key === "dom" ? "folga" : "integral";
                          const mode = block.week_pattern?.[wd.key] ?? def;
                          return (
                            <button
                              key={wd.key}
                              type="button"
                              onClick={() => handleCycleDayPattern(index, wd.key)}
                              className="p-1.5 rounded-lg border border-line-subtle bg-surface hover:border-line-strong text-center cursor-pointer"
                            >
                              <div className="text-[10px] font-bold text-ink-primary">{wd.short}</div>
                              <div className="text-[9px] text-primary font-semibold">
                                {PATTERN_LABELS[mode]}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-4 mt-4 border-t border-line-subtle">
          <button
            type="button"
            onClick={handleAddBlock}
            className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-line-subtle bg-elevated hover:bg-elevated/80 text-xs font-semibold text-ink-primary cursor-pointer"
          >
            <Plus size={15} />
            Adicionar bloco
          </button>
          <div className="flex items-center gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-line-subtle text-xs font-medium text-ink-primary hover:bg-elevated cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold cursor-pointer disabled:opacity-60"
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              Salvar blocos
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
