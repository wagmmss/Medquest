"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  CheckSquare,
  ClipboardPaste,
  Loader2,
  X,
} from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";
import {
  fetchSixYearPreview,
  invalidateSixYearQueries,
  sixYearPreviewKey,
} from "@/lib/queries/sixYear";
import {
  DAY_MODE_DISPLAY,
  SHIFT_KIND_META,
  type DayOverrideMode,
  type ShiftKind,
} from "@/lib/sixYear/staticData";
import { parsePastedDates } from "@/lib/sixYear/datePasteParser";
import type { SixYearActiveRodizio, SixYearDayStatus } from "@/types/api";
import clsx from "clsx";

const MONTH_NAMES_PT = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

const WEEKDAY_HEADERS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function isoFromYmd(year: number, monthIndex0: number, day: number): string {
  return `${year}-${pad2(monthIndex0 + 1)}-${pad2(day)}`;
}

function addDaysIso(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
}

function toneClasses(tone: "muted" | "accent" | "warning" | "normal" | "destructive"): string {
  switch (tone) {
    case "destructive":
      return "bg-destructive/15 text-destructive border-destructive/30";
    case "warning":
      return "bg-warning/15 text-warning border-warning/30";
    case "normal":
      return "bg-normal-bg text-normal border-normal/30";
    case "accent":
      return "bg-primary/10 text-primary border-primary/25";
    default:
      return "bg-elevated text-ink-secondary border-line-subtle";
  }
}

interface ShiftCalendarSectionProps {
  todayIso: string;
  routineEnabled: boolean;
  rodizio: SixYearActiveRodizio | null;
}

export function ShiftCalendarSection({
  todayIso,
  routineEnabled,
  rodizio,
}: ShiftCalendarSectionProps) {
  const queryClient = useQueryClient();
  const initialParts = todayIso.split("-").map(Number);
  const [viewYear, setViewYear] = useState<number>(initialParts[0] || 2027);
  const [viewMonth, setViewMonth] = useState<number>((initialParts[1] || 1) - 1);

  // Range do mês ± 7 dias (<= 46 dias, bem abaixo do limite de 62 dias da API)
  const { monthStartIso, monthEndIso, queryFrom, queryTo, gridCells } = useMemo(() => {
    const firstDay = new Date(Date.UTC(viewYear, viewMonth, 1));
    const lastDay = new Date(Date.UTC(viewYear, viewMonth + 1, 0));
    const mStart = isoFromYmd(viewYear, viewMonth, 1);
    const mEnd = isoFromYmd(viewYear, viewMonth, lastDay.getUTCDate());
    const qFrom = addDaysIso(mStart, -7);
    const qTo = addDaysIso(mEnd, 7);

    // Grade começando na segunda-feira (0=Seg .. 6=Dom)
    const firstDow = (firstDay.getUTCDay() + 6) % 7;
    const gridStart = addDaysIso(mStart, -firstDow);
    const totalNeeded = firstDow + lastDay.getUTCDate();
    const totalCells = Math.ceil(totalNeeded / 7) * 7;
    const cells: Array<{ dateIso: string; dayNum: number; inMonth: boolean }> = [];
    for (let i = 0; i < totalCells; i++) {
      const iso = addDaysIso(gridStart, i);
      cells.push({
        dateIso: iso,
        dayNum: Number(iso.slice(8, 10)),
        inMonth: iso >= mStart && iso <= mEnd,
      });
    }
    return {
      monthStartIso: mStart,
      monthEndIso: mEnd,
      queryFrom: qFrom,
      queryTo: qTo,
      gridCells: cells,
    };
  }, [viewYear, viewMonth]);

  const { data: preview, isLoading, isError, refetch } = useQuery({
    queryKey: sixYearPreviewKey(queryFrom, queryTo),
    queryFn: () => fetchSixYearPreview(queryFrom, queryTo),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const daysByIso = useMemo(() => {
    const map = new Map<string, SixYearDayStatus>();
    for (const d of preview?.days ?? []) {
      map.set(d.date_iso, d);
    }
    return map;
  }, [preview]);

  // Popover de dia único
  const [selectedDayIso, setSelectedDayIso] = useState<string | null>(null);
  const [dayNote, setDayNote] = useState<string>("");
  const [busy, setBusy] = useState(false);

  // Seleção múltipla
  const [multiMode, setMultiMode] = useState(false);
  const [multiSelected, setMultiSelected] = useState<string[]>([]);
  const [multiKind, setMultiKind] = useState<ShiftKind>("plantao_noturno");

  // Colar datas
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteKind, setPasteKind] = useState<ShiftKind>("plantao_noturno");

  const parsedPaste = useMemo(
    () =>
      parsePastedDates(pasteText, {
        referenceDateIso: todayIso,
        rodizioStartIso: rodizio?.start,
        rodizioEndIso: rodizio?.end,
      }),
    [pasteText, todayIso, rodizio]
  );

  const selectedDay = selectedDayIso ? daysByIso.get(selectedDayIso) ?? null : null;

  const handlePrevMonth = () => {
    if (viewMonth === 0) {
      setViewYear((y) => y - 1);
      setViewMonth(11);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (viewMonth === 11) {
      setViewYear((y) => y + 1);
      setViewMonth(0);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const handleDayClick = (iso: string) => {
    if (multiMode) {
      setMultiSelected((prev) =>
        prev.includes(iso) ? prev.filter((x) => x !== iso) : [...prev, iso]
      );
      return;
    }
    setSelectedDayIso((prev) => (prev === iso ? null : iso));
    setDayNote("");
  };

  const handleToggleSingleShift = async (dateIso: string, kind: ShiftKind, hasShift: boolean) => {
    setBusy(true);
    try {
      await api.sixYear.postShiftsBatch(
        hasShift
          ? { remove: [{ date_iso: dateIso, kind }] }
          : { add: [{ date_iso: dateIso, kind, note: dayNote.trim() }] }
      );
      await invalidateSixYearQueries(queryClient);
      toast.success(hasShift ? "Plantão removido." : "Plantão salvo.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao atualizar plantão.");
    } finally {
      setBusy(false);
    }
  };

  const handleSingleOverride = async (dateIso: string, mode: DayOverrideMode | null) => {
    setBusy(true);
    try {
      if (mode === null) {
        await api.sixYear.deleteDayOverride(dateIso);
        toast.success("Ajuste do dia removido.");
      } else {
        await api.sixYear.putDayOverride(dateIso, mode);
        toast.success("Ajuste do dia aplicado.");
      }
      await invalidateSixYearQueries(queryClient);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao ajustar dia.");
    } finally {
      setBusy(false);
    }
  };

  const handleApplyMultiBatch = async (action: "add" | "remove") => {
    if (multiSelected.length === 0) return;
    setBusy(true);
    try {
      const items = multiSelected.map((date_iso) => ({ date_iso, kind: multiKind }));
      const res = await api.sixYear.postShiftsBatch(
        action === "add" ? { add: items } : { remove: items }
      );
      await invalidateSixYearQueries(queryClient);
      toast.success(
        action === "add"
          ? `${res.added} plantão(ões) adicionado(s).`
          : `${res.removed} plantão(ões) removido(s).`
      );
      setMultiSelected([]);
      setMultiMode(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao salvar lote de plantões.");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmPaste = async () => {
    if (parsedPaste.valid.length === 0) return;
    setBusy(true);
    try {
      const res = await api.sixYear.postShiftsBatch({
        add: parsedPaste.valid.map((item) => ({
          date_iso: item.dateIso,
          kind: pasteKind,
        })),
      });
      await invalidateSixYearQueries(queryClient);
      toast.success(`${res.added} plantão(ões) cadastrado(s) em lote.`);
      setPasteText("");
      setPasteOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao cadastrar datas coladas.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby="six-year-calendar-heading"
      className="bg-surface border border-line-subtle rounded-2xl p-4 sm:p-5 space-y-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <CalendarDays size={18} />
          </div>
          <div className="min-w-0">
            <h3 id="six-year-calendar-heading" className="text-base font-bold text-ink-primary">
              Calendário de Plantões
            </h3>
            <p className="text-xs text-ink-secondary">
              {routineEnabled
                ? "Clique em um dia para marcar plantão ou ajuste. Noturno e 24h protegem o dia seguinte."
                : "Modo rotina desligado: alterações ficam salvas, mas sem efeito na meta diária."}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setMultiMode((v) => !v);
              setMultiSelected([]);
              setSelectedDayIso(null);
            }}
            className={clsx(
              "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer",
              multiMode
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-elevated text-ink-primary border-line-subtle hover:bg-elevated/80"
            )}
          >
            <CheckSquare size={14} />
            Selecionar vários
          </button>
          <button
            type="button"
            onClick={() => setPasteOpen((v) => !v)}
            className={clsx(
              "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer",
              pasteOpen
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-elevated text-ink-primary border-line-subtle hover:bg-elevated/80"
            )}
          >
            <ClipboardPaste size={14} />
            Colar datas
          </button>
        </div>
      </div>

      {/* Barra de seleção múltipla */}
      {multiMode && (
        <div className="p-3 rounded-xl bg-elevated/70 border border-line-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div className="text-xs text-ink-primary font-medium">
            {multiSelected.length} dia(s) selecionado(s). Clique nos dias do calendário e escolha o tipo:
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Tipo de plantão para seleção múltipla"
              value={multiKind}
              onChange={(e) => setMultiKind(e.target.value as ShiftKind)}
              className="px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
            >
              {(Object.keys(SHIFT_KIND_META) as ShiftKind[]).map((k) => (
                <option key={k} value={k}>
                  {SHIFT_KIND_META[k].label}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy || multiSelected.length === 0}
              onClick={() => void handleApplyMultiBatch("add")}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold disabled:opacity-50 cursor-pointer"
            >
              Adicionar
            </button>
            <button
              type="button"
              disabled={busy || multiSelected.length === 0}
              onClick={() => void handleApplyMultiBatch("remove")}
              className="px-3 py-1.5 rounded-lg border border-destructive/40 text-destructive text-xs font-semibold hover:bg-destructive/10 disabled:opacity-50 cursor-pointer"
            >
              Remover
            </button>
          </div>
        </div>
      )}

      {/* Painel de colar datas em lote */}
      {pasteOpen && (
        <div className="p-3.5 rounded-xl bg-elevated/70 border border-line-subtle space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold text-ink-primary">
              Colar datas em lote (`dd/mm`, `dd/mm/aaaa` ou `aaaa-mm-dd`)
            </span>
            <button
              type="button"
              onClick={() => setPasteOpen(false)}
              aria-label="Fechar colar datas"
              className="p-1 rounded-md text-ink-muted hover:text-ink-primary cursor-pointer"
            >
              <X size={14} />
            </button>
          </div>
          <textarea
            rows={3}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="Ex.: 04/02, 11/02/2027, 2027-02-18"
            aria-label="Datas de plantão para importar"
            className="w-full px-3 py-2 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary font-mono"
          />
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                aria-label="Tipo de plantão para datas coladas"
                value={pasteKind}
                onChange={(e) => setPasteKind(e.target.value as ShiftKind)}
                className="px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
              >
                {(Object.keys(SHIFT_KIND_META) as ShiftKind[]).map((k) => (
                  <option key={k} value={k}>
                    {SHIFT_KIND_META[k].label}
                  </option>
                ))}
              </select>
              <span className="text-ink-secondary">
                <strong>{parsedPaste.valid.length}</strong> data(s) reconhecida(s)
                {parsedPaste.invalid.length > 0 && (
                  <span className="text-destructive ml-1">
                    · {parsedPaste.invalid.length} inválida(s)
                  </span>
                )}
              </span>
            </div>
            <button
              type="button"
              disabled={busy || parsedPaste.valid.length === 0}
              onClick={() => void handleConfirmPaste()}
              className="inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold disabled:opacity-50 cursor-pointer"
            >
              {busy && <Loader2 size={13} className="animate-spin" />}
              Confirmar lote ({parsedPaste.valid.length})
            </button>
          </div>
          {parsedPaste.valid.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {parsedPaste.valid.map((item) => (
                <span
                  key={item.dateIso}
                  className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-surface border border-line-subtle text-ink-primary"
                >
                  {item.dateIso}
                  {item.inferredYear ? " (ano resolvido)" : ""}
                </span>
              ))}
            </div>
          )}
          {parsedPaste.invalid.length > 0 && (
            <p className="text-[11px] text-destructive">
              Não reconhecidas: {parsedPaste.invalid.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* Navegação mensal */}
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={handlePrevMonth}
          aria-label="Mês anterior"
          className="p-1.5 rounded-lg border border-line-subtle bg-elevated hover:bg-elevated/80 text-ink-primary cursor-pointer"
        >
          <ChevronLeft size={16} />
        </button>
        <div className="text-sm font-bold text-ink-primary">
          {MONTH_NAMES_PT[viewMonth]} {viewYear}
          <span className="sr-only">
            ({monthStartIso} a {monthEndIso})
          </span>
        </div>
        <button
          type="button"
          onClick={handleNextMonth}
          aria-label="Próximo mês"
          className="p-1.5 rounded-lg border border-line-subtle bg-elevated hover:bg-elevated/80 text-ink-primary cursor-pointer"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {isError ? (
        <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-xs text-destructive flex items-center justify-between gap-3">
          <span>Não foi possível carregar o calendário deste mês.</span>
          <button
            type="button"
            onClick={() => void refetch()}
            className="px-2.5 py-1 rounded-md bg-surface text-ink-primary border border-line-subtle font-semibold cursor-pointer"
          >
            Tentar novamente
          </button>
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="grid grid-cols-7 gap-1 text-center">
            {WEEKDAY_HEADERS.map((wd) => (
              <div
                key={wd}
                className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted py-1"
              >
                {wd}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {gridCells.map((cell) => {
              const dayData = daysByIso.get(cell.dateIso);
              const meta = dayData
                ? DAY_MODE_DISPLAY[dayData.mode] ?? DAY_MODE_DISPLAY.integral
                : null;
              const isToday = cell.dateIso === todayIso;
              const isSelected = multiMode
                ? multiSelected.includes(cell.dateIso)
                : selectedDayIso === cell.dateIso;

              return (
                <button
                  key={cell.dateIso}
                  type="button"
                  data-date-iso={cell.dateIso}
                  data-day-mode={dayData?.mode ?? ""}
                  onClick={() => handleDayClick(cell.dateIso)}
                  className={clsx(
                    "min-h-[60px] sm:min-h-[68px] p-1 sm:p-1.5 rounded-lg border text-left flex flex-col justify-between transition-all cursor-pointer",
                    cell.inMonth ? "bg-canvas/40" : "opacity-45 bg-elevated/30",
                    isToday
                      ? "border-primary ring-1 ring-primary/40"
                      : isSelected
                        ? "border-accent ring-1 ring-accent/40"
                        : "border-line-subtle hover:border-line-strong"
                  )}
                >
                  <div className="flex items-center justify-between gap-1 w-full">
                    <span
                      className={clsx(
                        "text-[11px] font-bold leading-none",
                        isToday ? "text-primary" : "text-ink-primary"
                      )}
                    >
                      {cell.dayNum}
                    </span>
                    {dayData && (
                      <span className="text-[10px] font-mono text-ink-secondary leading-none">
                        {dayData.goal_questions}q
                      </span>
                    )}
                  </div>

                  {isLoading && !dayData ? (
                    <span className="h-3 w-full rounded bg-elevated animate-pulse" />
                  ) : dayData && meta ? (
                    <div className="space-y-0.5 w-full">
                      <span
                        className={clsx(
                          "block truncate px-1 py-0.5 rounded text-[9px] sm:text-[10px] font-semibold border leading-tight",
                          toneClasses(meta.tone)
                        )}
                      >
                        {meta.short}
                      </span>
                      {dayData.shifts.length > 0 && (
                        <span className="block truncate text-[9px] text-ink-muted leading-none">
                          {dayData.shifts.map((s) => SHIFT_KIND_META[s]?.short ?? s).join("+")}
                        </span>
                      )}
                    </div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Popover / painel inline do dia selecionado */}
      {selectedDayIso && !multiMode && (
        <div
          data-testid="shift-day-popover"
          className="p-3.5 rounded-xl bg-elevated/80 border border-line-strong space-y-3"
        >
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-bold text-ink-primary">
                Dia {selectedDayIso}
                {selectedDay && (
                  <span className="ml-2 font-normal text-ink-secondary">
                    · {DAY_MODE_DISPLAY[selectedDay.mode]?.label ?? selectedDay.mode} ({selectedDay.goal_questions} q)
                  </span>
                )}
              </div>
              {selectedDay && (
                <p className="text-[11px] text-ink-muted">{selectedDay.guidance}</p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setSelectedDayIso(null)}
              aria-label="Fechar detalhes do dia"
              className="p-1 rounded-md text-ink-muted hover:text-ink-primary cursor-pointer"
            >
              <X size={15} />
            </button>
          </div>

          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
              Plantões neste dia
            </div>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(SHIFT_KIND_META) as ShiftKind[]).map((kind) => {
                const active = selectedDay?.shifts.includes(kind) ?? false;
                return (
                  <button
                    key={kind}
                    type="button"
                    disabled={busy}
                    onClick={() => void handleToggleSingleShift(selectedDayIso, kind, active)}
                    className={clsx(
                      "px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50",
                      active
                        ? "bg-warning/20 text-warning border-warning/40"
                        : "bg-surface text-ink-primary border-line-subtle hover:bg-elevated"
                    )}
                  >
                    {active ? "✓ " : "+ "}
                    {SHIFT_KIND_META[kind].label}
                  </button>
                );
              })}
            </div>
            <input
              type="text"
              value={dayNote}
              onChange={(e) => setDayNote(e.target.value)}
              placeholder="Nota opcional ao adicionar plantão (ex.: PS Cirurgia)"
              maxLength={200}
              className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-surface border border-line-subtle text-ink-primary"
            />
          </div>

          <div className="space-y-1.5 pt-2 border-t border-line-subtle">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
              Ajuste manual do dia
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["pos_plantao", "Pós-plantão"],
                  ["folga", "Folga"],
                  ["meio_periodo", "Meio período"],
                  ["integral", "Integral"],
                ] as Array<[DayOverrideMode, string]>
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  disabled={busy}
                  onClick={() => void handleSingleOverride(selectedDayIso, mode)}
                  className={clsx(
                    "px-2.5 py-1 rounded-lg border text-xs font-medium cursor-pointer disabled:opacity-50",
                    selectedDay?.source === "override" && selectedDay.mode === mode
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-surface text-ink-primary border-line-subtle hover:bg-elevated"
                  )}
                >
                  {label}
                </button>
              ))}
              {selectedDay?.source === "override" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleSingleOverride(selectedDayIso, null)}
                  className="px-2.5 py-1 rounded-lg border border-line-subtle text-xs font-medium text-ink-secondary hover:text-ink-primary cursor-pointer"
                >
                  Limpar ajuste
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Legenda compacta */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-line-subtle text-[11px] text-ink-muted">
        <span className="font-semibold text-ink-secondary">Legenda:</span>
        {(["folga", "meio_periodo", "integral", "plantao_12h_dia", "entrada_noturno", "plantao_24h", "pos_plantao"] as const).map(
          (k) => (
            <span
              key={k}
              className={clsx(
                "px-1.5 py-0.5 rounded border text-[10px] font-medium",
                toneClasses(DAY_MODE_DISPLAY[k].tone)
              )}
            >
              {DAY_MODE_DISPLAY[k].short}
            </span>
          )
        )}
      </div>
    </section>
  );
}
