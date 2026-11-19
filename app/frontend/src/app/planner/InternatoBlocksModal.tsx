"use client";

import { useState } from "react";
import { X, Plus, Trash2, CalendarRange, Loader2 } from "lucide-react";
import type { InternatoBlock } from "@/types/api";
import { api } from "@/lib/api";
import toast from "react-hot-toast";

const INTERNATO_AREA_OPTIONS = [
  "Clínica Médica",
  "Cirurgia",
  "Ginecologia e Obstetrícia",
  "Pediatria",
  "Preventiva",
  "Medicina Intensiva",
  "Especialidades",
];

interface InternatoBlocksModalProps {
  initialBlocks: InternatoBlock[];
  onClose: () => void;
  onSaved: (blocks: InternatoBlock[]) => void;
}

export function InternatoBlocksModal({
  initialBlocks,
  onClose,
  onSaved,
}: InternatoBlocksModalProps) {
  const [blocks, setBlocks] = useState<InternatoBlock[]>(() =>
    initialBlocks.length > 0
      ? initialBlocks.map((b) => ({ ...b }))
      : [{ start: "2027-01-26", end: "2027-02-22", area: "Cirurgia" }]
  );
  const [saving, setSaving] = useState(false);

  const handleUpdateBlock = (index: number, field: keyof InternatoBlock, value: string) => {
    setBlocks((prev) =>
      prev.map((block, idx) => (idx === index ? { ...block, [field]: value } : block))
    );
  };

  const handleAddBlock = () => {
    const last = blocks[blocks.length - 1];
    const defaultStart = last?.end || new Date().toISOString().slice(0, 10);
    setBlocks((prev) => [
      ...prev,
      { start: defaultStart, end: defaultStart, area: "Clínica Médica" },
    ]);
  };

  const handleRemoveBlock = (index: number) => {
    setBlocks((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleSave = async () => {
    const valid = blocks.every((b) => b.start && b.end && b.area && b.start <= b.end);
    if (!valid) {
      toast.error("Verifique as datas dos blocos: a data inicial deve ser menor ou igual à final.");
      return;
    }

    setSaving(true);
    try {
      const res = await api.planner.saveInternatoBlocks(blocks);
      toast.success("Blocos do internato atualizados! Cronograma recalculado mantendo aulas feitas.");
      onSaved(res.internato_blocks || blocks);
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
        className="relative bg-surface border border-line-subtle rounded-2xl shadow-2xl p-6 max-w-2xl w-full max-h-[88dvh] flex flex-col z-10 animate-in fade-in zoom-in-95 duration-200"
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
                Defina as datas e grandes áreas de cada rodízio. As aulas já marcadas como feitas serão preservadas.
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
          {blocks.map((block, index) => (
            <div
              key={index}
              className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_1.4fr_auto] gap-2 items-center p-3 rounded-xl bg-elevated/60 border border-line-subtle"
            >
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                  Início
                </label>
                <input
                  type="date"
                  value={block.start}
                  onChange={(e) => handleUpdateBlock(index, "start", e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
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
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                />
              </div>
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-1">
                  Grande Área
                </label>
                <select
                  value={block.area}
                  onChange={(e) => handleUpdateBlock(index, "area", e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
                >
                  {INTERNATO_AREA_OPTIONS.map((area) => (
                    <option key={area} value={area}>
                      {area}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => handleRemoveBlock(index)}
                title="Remover bloco"
                aria-label={`Remover bloco ${index + 1}`}
                className="mt-4 sm:mt-5 p-2 rounded-lg text-ink-muted hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
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
