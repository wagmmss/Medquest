"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Award,
  Check,
  ChevronDown,
  ChevronUp,
  Flag,
  Plus,
  Trash2,
  TrendingUp,
} from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";
import {
  SIX_YEAR_SUMMARY_KEY,
  fetchSixYearSummary,
  invalidateSixYearQueries,
} from "@/lib/queries/sixYear";
import {
  CURRICULUM_BANKS_CONFIG,
  CURRICULUM_CATEGORIES_META,
  UNIFIED_CURRICULUM_CATALOG,
  type CurriculumBankId,
  type CurriculumCategoryId,
  type CurriculumEntryState,
  type ProofStatus,
} from "@/lib/sixYear/curriculumCatalog";
import {
  computeCurriculumRoiOpportunities,
  computeUnifiedCurriculumScores,
} from "@/lib/sixYear/curriculumEngine";
import { computeMilestoneCountdown, type MilestoneCategory } from "@/lib/sixYear/milestones";
import clsx from "clsx";

const MILESTONE_CATEGORIES: Array<{ value: MilestoneCategory; label: string }> = [
  { value: "prova", label: "Prova" },
  { value: "curriculo", label: "Currículo" },
  { value: "estudo", label: "Estudo" },
  { value: "graduacao", label: "Graduação" },
  { value: "ingresso", label: "Ingresso" },
];

const PROOF_STATUS_META: Record<ProofStatus, { label: string; cls: string }> = {
  pdf_pronto: { label: "PDF pronto", cls: "bg-normal-bg text-normal border-normal/30" },
  em_andamento: { label: "Em andamento", cls: "bg-warning/15 text-warning border-warning/30" },
  falta: { label: "Falta PDF", cls: "bg-elevated text-ink-secondary border-line-subtle" },
};

const BANK_ORDER: CurriculumBankId[] = ["usp_sp", "usp_rp", "unicamp"];

export function R1CurriculumTab() {
  const queryClient = useQueryClient();
  const { data: summary, isLoading, isError, refetch } = useQuery({
    queryKey: SIX_YEAR_SUMMARY_KEY,
    queryFn: fetchSixYearSummary,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Draft local de currículo para edição responsiva com debounce 600ms
  const [localEntries, setLocalEntries] = useState<Record<string, CurriculumEntryState>>({});
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Filtros da matriz
  const [categoryFilter, setCategoryFilter] = useState<CurriculumCategoryId | "all">("all");
  const [proofFilter, setProofFilter] = useState<ProofStatus | "all">("all");
  const [expandedRules, setExpandedRules] = useState<Record<CurriculumBankId, boolean>>({
    usp_sp: false,
    usp_rp: false,
    unicamp: false,
  });

  // Novo marco inline
  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newCat, setNewCat] = useState<MilestoneCategory>("prova");
  const [newNote, setNewNote] = useState("");
  const [busy, setBusy] = useState(false);

  // Sincronizar entries do servidor quando chegam (sem sobrescrever itens com debounce pendente)
  useEffect(() => {
    if (!summary) return;
    setLocalEntries((prev) => {
      const next: Record<string, CurriculumEntryState> = {};
      for (const [itemId, dto] of Object.entries(summary.curriculum_entries)) {
        next[itemId] = {
          value: dto.value,
          proofStatus: dto.proof_status,
          notes: dto.note,
        };
      }
      for (const pendingId of Object.keys(debounceTimers.current)) {
        if (prev[pendingId]) {
          next[pendingId] = prev[pendingId];
        }
      }
      return next;
    });
  }, [summary]);

  useEffect(() => {
    const timers = debounceTimers.current;
    return () => {
      for (const t of Object.values(timers)) {
        clearTimeout(t);
      }
    };
  }, []);

  const enamedConcept: 3 | 4 | 5 = summary?.plan.enamed_concept ?? 5;

  const evaluation = useMemo(
    () => computeUnifiedCurriculumScores(localEntries, { enamedConcept }),
    [localEntries, enamedConcept]
  );

  const roiList = useMemo(
    () => computeCurriculumRoiOpportunities(localEntries, { enamedConcept, limit: 5 }),
    [localEntries, enamedConcept]
  );

  const filteredCatalog = useMemo(() => {
    return UNIFIED_CURRICULUM_CATALOG.filter((item) => {
      if (categoryFilter !== "all" && item.categoria !== categoryFilter) return false;
      if (proofFilter !== "all") {
        const entry = localEntries[item.id];
        const status: ProofStatus = entry?.proofStatus ?? "falta";
        if (status !== proofFilter) return false;
      }
      return true;
    });
  }, [categoryFilter, proofFilter, localEntries]);

  if (isLoading && !summary) {
    return (
      <div className="space-y-4 animate-pulse" aria-busy="true" aria-label="Carregando R1 e Currículo">
        <div className="h-32 rounded-2xl bg-surface border border-line-subtle" />
        <div className="h-48 rounded-2xl bg-surface border border-line-subtle" />
        <div className="h-64 rounded-2xl bg-surface border border-line-subtle" />
      </div>
    );
  }

  if (isError || !summary) {
    return (
      <div className="bg-surface border border-line-subtle rounded-2xl p-6 text-center space-y-3">
        <p className="text-sm font-semibold text-ink-primary">
          Não foi possível carregar os dados de R1 & Currículo.
        </p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  const [ty, tm, td] = summary.today.date_iso.split("-").map(Number);
  const nowRef = ty && tm && td ? new Date(ty, tm - 1, td) : new Date();

  const scheduleCurriculumSave = (itemId: string, nextState: CurriculumEntryState) => {
    setLocalEntries((prev) => ({ ...prev, [itemId]: nextState }));
    if (debounceTimers.current[itemId]) {
      clearTimeout(debounceTimers.current[itemId]);
    }
    debounceTimers.current[itemId] = setTimeout(async () => {
      delete debounceTimers.current[itemId];
      try {
        await api.sixYear.putCurriculumEntry(itemId, {
          value: nextState.value,
          proof_status: nextState.proofStatus,
          note: nextState.notes ?? "",
        });
        await queryClient.invalidateQueries({ queryKey: ["six-year-summary"] });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Erro ao salvar item de currículo.");
      }
    }, 600);
  };

  const handleChangeEnamed = async (concept: 3 | 4 | 5) => {
    setBusy(true);
    try {
      await api.sixYear.patchPlan({ enamed_concept: concept });
      await invalidateSixYearQueries(queryClient);
      toast.success(`Conceito ENAMED atualizado para ${concept}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao atualizar conceito ENAMED.");
    } finally {
      setBusy(false);
    }
  };

  const handleAddMilestone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDate) {
      toast.error("Informe título e data do marco.");
      return;
    }
    setBusy(true);
    try {
      await api.sixYear.createMilestone({
        titulo: newTitle.trim(),
        data_iso: newDate,
        categoria: newCat,
        note: newNote.trim(),
      });
      await invalidateSixYearQueries(queryClient);
      setNewTitle("");
      setNewDate("");
      setNewNote("");
      toast.success("Marco R1 adicionado.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao criar marco.");
    } finally {
      setBusy(false);
    }
  };

  const handleToggleMilestoneDone = async (id: string, currentDone: boolean) => {
    setBusy(true);
    try {
      await api.sixYear.patchMilestone(id, { done: !currentDone });
      await invalidateSixYearQueries(queryClient);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao atualizar marco.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteMilestone = async (id: string) => {
    setBusy(true);
    try {
      await api.sixYear.deleteMilestone(id);
      await invalidateSixYearQueries(queryClient);
      toast.success("Marco removido.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao remover marco.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 pb-10">
      {/* 1. LINHA DO TEMPO DE MARCOS */}
      <section
        aria-labelledby="r1-milestones-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <Flag size={18} />
          </div>
          <div>
            <h2 id="r1-milestones-heading" className="text-base font-bold text-ink-primary">
              Linha do Tempo de Marcos R1
            </h2>
            <p className="text-xs text-ink-secondary">
              Datas-chave de editais, dossiê de currículo, provas e ingresso.
            </p>
          </div>
        </div>

        {/* Formulário inline */}
        <form
          onSubmit={(e) => void handleAddMilestone(e)}
          className="grid grid-cols-1 sm:grid-cols-[1.5fr_0.9fr_0.9fr_auto] gap-2 p-3 rounded-xl bg-elevated/50 border border-line-subtle"
        >
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Título do marco (ex.: Envio currículo USP-SP)"
            aria-label="Título do novo marco"
            maxLength={200}
            className="px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
          />
          <input
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.target.value)}
            aria-label="Data do novo marco"
            className="px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
          />
          <select
            value={newCat}
            onChange={(e) => setNewCat(e.target.value as MilestoneCategory)}
            aria-label="Categoria do novo marco"
            className="px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
          >
            {MILESTONE_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
          >
            <Plus size={14} /> Adicionar
          </button>
          <input
            type="text"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Nota opcional"
            aria-label="Nota opcional do novo marco"
            maxLength={2000}
            className="sm:col-span-4 px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
          />
        </form>

        {summary.milestones.length === 0 ? (
          <p className="text-xs text-ink-secondary">
            Nenhum marco cadastrado ainda. Adicione o primeiro acima.
          </p>
        ) : (
          <ul className="space-y-2">
            {summary.milestones.map((ms) => {
              const cd = computeMilestoneCountdown(ms, nowRef);
              const isNext = summary.next_milestone?.id === ms.id;
              return (
                <li
                  key={ms.id}
                  className={clsx(
                    "p-3 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-2.5",
                    isNext && !ms.done
                      ? "bg-primary/10 border-primary"
                      : ms.done
                        ? "bg-elevated/30 border-line-subtle opacity-70"
                        : "bg-elevated/50 border-line-subtle"
                  )}
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleToggleMilestoneDone(ms.id, ms.done)}
                      aria-label={ms.done ? `Reabrir ${ms.titulo}` : `Concluir ${ms.titulo}`}
                      className={clsx(
                        "mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 cursor-pointer",
                        ms.done
                          ? "bg-normal border-normal text-white"
                          : "bg-surface border-line-strong"
                      )}
                    >
                      {ms.done && <Check size={12} />}
                    </button>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={clsx(
                            "text-xs font-bold text-ink-primary",
                            ms.done && "line-through"
                          )}
                        >
                          {ms.titulo}
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface border border-line-subtle text-ink-secondary">
                          {ms.categoria}
                        </span>
                        {isNext && !ms.done && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary text-primary-foreground">
                            Próximo
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-ink-secondary mt-0.5">
                        {ms.data_iso} ·{" "}
                        <span
                          className={clsx(
                            "font-semibold",
                            cd.status === "overdue"
                              ? "text-destructive"
                              : cd.status === "soon"
                                ? "text-warning"
                                : "text-ink-primary"
                          )}
                        >
                          {cd.label}
                        </span>
                      </div>
                      {ms.note && <p className="text-[11px] text-ink-muted mt-0.5">{ms.note}</p>}
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDeleteMilestone(ms.id)}
                    aria-label={`Remover marco ${ms.titulo}`}
                    className="self-end sm:self-center p-1.5 rounded-lg text-ink-muted hover:text-destructive hover:bg-destructive/10 cursor-pointer shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 2. PLACAR POR BANCA + FATOR ENAMED */}
      <section className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
              <Award size={18} />
            </div>
            <div>
              <h3 className="text-base font-bold text-ink-primary">
                Placar de Currículo por Banca (Editais 2027)
              </h3>
              <p className="text-xs text-ink-secondary">
                Comprovado (PDF pronto) × Projetado · {evaluation.proofCounts.pdf_pronto} pronto(s),{" "}
                {evaluation.proofCounts.em_andamento} em andamento, {evaluation.proofCounts.falta} faltando PDF.
              </p>
            </div>
          </div>

          {/* Fator ENAMED */}
          <div className="flex items-center gap-1.5 bg-elevated/70 border border-line-subtle rounded-xl p-1.5 shrink-0">
            <span className="text-[11px] font-semibold text-ink-secondary px-1.5">ENAMED:</span>
            {([3, 4, 5] as const).map((c) => (
              <button
                key={c}
                type="button"
                disabled={busy}
                onClick={() => void handleChangeEnamed(c)}
                className={clsx(
                  "px-2.5 py-1 rounded-lg text-xs font-bold transition-colors cursor-pointer",
                  enamedConcept === c
                    ? "bg-primary text-primary-foreground"
                    : "text-ink-primary hover:bg-surface"
                )}
              >
                Conceito {c}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {BANK_ORDER.map((bId) => {
            const b = evaluation.banks[bId];
            const cfg = CURRICULUM_BANKS_CONFIG[bId];
            const isOpen = expandedRules[bId];
            return (
              <div
                key={bId}
                className="p-3.5 rounded-xl bg-elevated/50 border border-line-subtle space-y-2.5 flex flex-col justify-between"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold text-ink-primary">{b.sigla}</span>
                    <span className="text-[11px] font-mono text-ink-secondary">
                      {b.finalScore}/{b.escalaMax} ({b.pct}%)
                    </span>
                  </div>
                  <div className="text-xs text-ink-secondary flex flex-wrap justify-between gap-1">
                    <span>
                      Comprovado: <strong className="text-normal">{b.confirmedScore}</strong>
                    </span>
                    <span>
                      Projetado: <strong className="text-ink-primary">{b.finalScore}</strong>
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-surface border border-line-subtle overflow-hidden relative">
                    <div
                      className="h-full bg-primary/35 absolute left-0 top-0"
                      style={{ width: `${b.pct}%` }}
                    />
                    <div
                      className="h-full bg-normal absolute left-0 top-0"
                      style={{ width: `${b.confirmedPct}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-ink-muted">
                    Bruto: {b.rawSubtotal}
                    {b.multiplier > 1 ? ` × ${b.multiplier}` : ""}
                    {b.enamedBonusPoints > 0 ? ` (+${b.enamedBonusPoints} ENAMED)` : ""}
                  </div>
                </div>

                <div className="pt-2 border-t border-line-subtle">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedRules((prev) => ({ ...prev, [bId]: !prev[bId] }))
                    }
                    className="w-full flex items-center justify-between text-[11px] font-semibold text-primary cursor-pointer"
                  >
                    <span>Regras de envio & edital</span>
                    {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {isOpen && (
                    <div className="mt-2 space-y-1.5 text-[11px] text-ink-secondary">
                      <p>{cfg.editalRef}</p>
                      <p className="text-ink-primary">{cfg.dicaEnvio}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 3. TOP ROI DE CURRÍCULO */}
      <section className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-normal-bg text-normal shrink-0">
            <TrendingUp size={18} />
          </div>
          <div>
            <h3 className="text-base font-bold text-ink-primary">Top ROI de Currículo</h3>
            <p className="text-xs text-ink-secondary">
              Maiores ganhos marginais reais nas 3 bancas (já descontando tetos e esforço).
            </p>
          </div>
        </div>

        {roiList.length === 0 ? (
          <p className="text-xs text-ink-secondary">
            Nenhuma alavanca marginal adicional disponível para os itens acionáveis atuais.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {roiList.map((op) => (
              <div
                key={op.itemId}
                className="p-3 rounded-xl bg-elevated/50 border border-line-subtle space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-ink-primary">{op.actionLabel}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface border border-line-subtle text-ink-secondary shrink-0">
                    esforço {op.effort}
                  </span>
                </div>
                <div className="text-[11px] text-ink-secondary flex flex-wrap gap-2">
                  <span>USP-SP: +{op.deltaByBank.usp_sp}</span>
                  <span>USP-RP: +{op.deltaByBank.usp_rp}</span>
                  <span>UNICAMP: +{op.deltaByBank.unicamp}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 4. MATRIZ UNIFICADA DE CURRÍCULO */}
      <section
        aria-labelledby="r1-matrix-heading"
        className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 id="r1-matrix-heading" className="text-base font-bold text-ink-primary">
              Matriz Unificada de Currículo
            </h3>
            <p className="text-xs text-ink-secondary">
              Alterações são salvas automaticamente (debounce 600 ms) e recalculam as 3 bancas.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Filtrar por categoria"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as CurriculumCategoryId | "all")}
              className="px-2.5 py-1.5 text-xs rounded-lg bg-elevated border border-line-subtle text-ink-primary"
            >
              <option value="all">Todas as categorias</option>
              {(Object.keys(CURRICULUM_CATEGORIES_META) as CurriculumCategoryId[]).map((cat) => (
                <option key={cat} value={cat}>
                  {CURRICULUM_CATEGORIES_META[cat].label}
                </option>
              ))}
            </select>
            <select
              aria-label="Filtrar por status do comprovante"
              value={proofFilter}
              onChange={(e) => setProofFilter(e.target.value as ProofStatus | "all")}
              className="px-2.5 py-1.5 text-xs rounded-lg bg-elevated border border-line-subtle text-ink-primary"
            >
              <option value="all">Todos os comprovantes</option>
              <option value="pdf_pronto">PDF pronto</option>
              <option value="em_andamento">Em andamento</option>
              <option value="falta">Falta PDF</option>
            </select>
          </div>
        </div>

        <div className="space-y-2.5">
          {filteredCatalog.map((item) => {
            const entry = localEntries[item.id] ?? { value: 0, proofStatus: "falta" as ProofStatus, notes: "" };
            const pts = evaluation.itemPointsByBank[item.id] ?? { usp_sp: 0, usp_rp: 0, unicamp: 0 };

            return (
              <div
                key={item.id}
                className="p-3.5 rounded-xl bg-elevated/40 border border-line-subtle space-y-2.5"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2.5">
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="text-xs font-bold text-ink-primary">{item.titulo}</div>
                    <p className="text-[11px] text-ink-secondary">{item.descricao}</p>
                    <div className="flex flex-wrap gap-2 pt-1 text-[10px] font-mono text-ink-muted">
                      {item.rules.usp_sp && <span>USP-SP: {pts.usp_sp} pts</span>}
                      {item.rules.usp_rp && <span>USP-RP: {pts.usp_rp} pts</span>}
                      {item.rules.unicamp && <span>UNICAMP: {pts.unicamp} pts</span>}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {item.inputType === "boolean" ? (
                      <button
                        type="button"
                        onClick={() =>
                          scheduleCurriculumSave(item.id, {
                            ...entry,
                            value: entry.value > 0 ? 0 : 1,
                          })
                        }
                        className={clsx(
                          "px-3 py-1.5 rounded-lg border text-xs font-bold cursor-pointer",
                          entry.value > 0
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-surface text-ink-primary border-line-subtle"
                        )}
                      >
                        {entry.value > 0 ? "Sim" : "Não"}
                      </button>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number"
                          min={0}
                          max={item.maxInput}
                          step={item.step ?? 1}
                          value={entry.value}
                          aria-label={`Valor para ${item.titulo}`}
                          onChange={(e) => {
                            const num = Number(e.target.value);
                            const clamped = Number.isFinite(num)
                              ? Math.max(0, Math.min(item.maxInput, num))
                              : 0;
                            scheduleCurriculumSave(item.id, { ...entry, value: clamped });
                          }}
                          className="w-20 px-2 py-1 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary font-mono"
                        />
                        {item.unitLabel && (
                          <span className="text-[11px] text-ink-muted">{item.unitLabel}</span>
                        )}
                      </div>
                    )}

                    <select
                      aria-label={`Comprovante para ${item.titulo}`}
                      value={entry.proofStatus}
                      onChange={(e) =>
                        scheduleCurriculumSave(item.id, {
                          ...entry,
                          proofStatus: e.target.value as ProofStatus,
                        })
                      }
                      className={clsx(
                        "px-2 py-1.5 rounded-lg border text-[11px] font-semibold",
                        PROOF_STATUS_META[entry.proofStatus].cls
                      )}
                    >
                      <option value="falta">Falta PDF</option>
                      <option value="em_andamento">Em andamento</option>
                      <option value="pdf_pronto">PDF pronto</option>
                    </select>
                  </div>
                </div>

                <input
                  type="text"
                  value={entry.notes ?? ""}
                  onChange={(e) =>
                    scheduleCurriculumSave(item.id, { ...entry, notes: e.target.value })
                  }
                  placeholder="Nota de dossiê / certificado..."
                  maxLength={2000}
                  className="w-full px-2.5 py-1.5 text-[11px] rounded-lg bg-surface border border-line-subtle text-ink-primary"
                />
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
