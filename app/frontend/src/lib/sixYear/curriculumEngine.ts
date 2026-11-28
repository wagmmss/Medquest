// Port 1:1 do motor de pontuação de currículo e ROI (USP-SP, USP-RP, UNICAMP — Editais 2027).
// Sem projeção composta / nota de corte / 1ª fase nesta fase.

import {
  CURRICULUM_BANKS_CONFIG,
  UNIFIED_CURRICULUM_CATALOG,
  type BankItemRule,
  type CurriculumBankId,
  type CurriculumEffortLevel,
  type CurriculumEntryState,
  type ProofStatus,
} from "./curriculumCatalog";

export interface CurriculumBlockScore {
  blockId: string;
  label: string;
  rawScore: number;
  cappedScore: number;
  confirmedCappedScore: number;
  maxPoints: number;
  missingToCap: number;
  pct: number;
}

export interface BankScoreSummary {
  bankId: CurriculumBankId;
  nome: string;
  sigla: string;
  escalaMax: number;
  rawSubtotal: number;
  confirmedRawSubtotal: number;
  multiplier: number;
  enamedBonusPoints: number;
  finalScore: number;
  confirmedScore: number;
  unconfirmedGap: number;
  missingToMax: number;
  pct: number;
  confirmedPct: number;
  finalGradeImpactMissing: number;
  equivalentFirstPhaseQuestions: number;
  blocks: CurriculumBlockScore[];
}

export interface UnifiedCurriculumEvaluation {
  banks: Record<CurriculumBankId, BankScoreSummary>;
  itemPointsByBank: Record<string, Record<CurriculumBankId, number>>;
  proofCounts: {
    pdf_pronto: number;
    em_andamento: number;
    falta: number;
    filledItems: number;
    unfilledItems: number;
    totalItems: number;
  };
}

export interface CurriculumRoiOpportunity {
  itemId: string;
  titulo: string;
  actionLabel: string;
  effort: CurriculumEffortLevel;
  currentValue: number;
  simulatedValue: number;
  unitLabel?: string;
  deltaByBank: Record<CurriculumBankId, number>;
  combinedFinalPtsDelta: number;
  roiScore: number;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function evaluateRulePoints(rule: BankItemRule | undefined, unitsRaw: number): number {
  if (!rule) return 0;
  const units = Number.isFinite(unitsRaw) ? Math.max(0, unitsRaw) : 0;
  if (units <= 0) return 0;

  if (Array.isArray(rule.tiers) && rule.tiers.length > 0) {
    const sorted = [...rule.tiers].sort((a, b) => b.minUnits - a.minUnits);
    for (const tier of sorted) {
      if (units >= tier.minUnits) {
        return Math.min(rule.maxItemPoints, round2(tier.points));
      }
    }
    return 0;
  }

  return Math.min(rule.maxItemPoints, round2(units * rule.perUnit));
}

interface PassEvaluation {
  blockAccumulator: Record<CurriculumBankId, Record<string, number>>;
  itemPointsByBank: Record<string, Record<CurriculumBankId, number>>;
  uspRpEnamedBonus: number;
}

function evaluateEntriesPass(
  entries: Record<string, CurriculumEntryState>,
  enamedConcept: 3 | 4 | 5,
  onlyConfirmed: boolean
): PassEvaluation {
  const bankIds: CurriculumBankId[] = ["usp_sp", "usp_rp", "unicamp"];
  const blockAccumulator: Record<CurriculumBankId, Record<string, number>> = {
    usp_sp: {},
    usp_rp: {},
    unicamp: {},
  };

  for (const bId of bankIds) {
    for (const blk of CURRICULUM_BANKS_CONFIG[bId].blocks) {
      blockAccumulator[bId][blk.id] = 0;
    }
  }

  const effectiveUnits: Record<string, number> = {};
  for (const item of UNIFIED_CURRICULUM_CATALOG) {
    const entry = entries[item.id];
    const rawVal = Math.min(item.maxInput, Math.max(0, Number(entry?.value) || 0));
    const status: ProofStatus = entry?.proofStatus || "falta";
    effectiveUnits[item.id] = onlyConfirmed && status !== "pdf_pronto" ? 0 : rawVal;
  }

  // Regras cruzadas USP-SP: Item 5 (IC com/sem artigo vinculado) e Item 6 (Publicação DIFERENTE da IC)
  const icBolsaAnos = effectiveUnits.ic_com_bolsa || 0;
  const icSemBolsaAnos = effectiveUnits.ic_sem_bolsa || 0;
  const pubmedCount = Math.floor(effectiveUnits.artigo_pubmed || 0);
  const scieloCount = Math.floor(effectiveUnits.artigo_scielo || 0);
  const totalArticles = pubmedCount + scieloCount;
  const icBolsaProjects = Math.min(2, Math.floor(icBolsaAnos + 1e-9));
  const icSemBolsaProjects = Math.min(2, Math.floor(icSemBolsaAnos + 1e-9));
  const requestedIcLinked = Math.min(2, Math.floor(effectiveUnits.ic_artigo_vinculado || 0));
  const effectiveIcLinked = Math.min(
    requestedIcLinked,
    totalArticles,
    icBolsaProjects + icSemBolsaProjects
  );
  const linkedBolsa = Math.min(effectiveIcLinked, icBolsaProjects);
  const linkedSemBolsa = Math.min(effectiveIcLinked - linkedBolsa, icSemBolsaProjects);
  const uspSpIcArtigoBonus = round2(linkedBolsa * 4 + linkedSemBolsa * 3);

  // Alocar artigos vinculados à IC preferencialmente de SciELO primeiro para preservar PubMed no Item 6
  const usedScieloInIc = Math.min(scieloCount, effectiveIcLinked);
  const usedPubmedInIc = Math.min(pubmedCount, effectiveIcLinked - usedScieloInIc);
  const freePubmedForItem6 = Math.max(0, pubmedCount - usedPubmedInIc);
  const freeScieloForItem6 = Math.max(0, scieloCount - usedScieloInIc);

  const itemPointsByBank: Record<string, Record<CurriculumBankId, number>> = {};

  // Rastrear teto específico de Liga na USP-RP (máx 1,0 pt somando diretoria + membro)
  let uspRpLigaPts = 0;

  for (const item of UNIFIED_CURRICULUM_CATALOG) {
    const units = effectiveUnits[item.id] || 0;
    itemPointsByBank[item.id] = { usp_sp: 0, usp_rp: 0, unicamp: 0 };

    for (const bId of bankIds) {
      const rule = item.rules[bId];
      if (!rule) continue;

      let pts = 0;
      if (bId === "usp_sp" && item.id === "ic_artigo_vinculado") {
        pts = uspSpIcArtigoBonus;
      } else if (bId === "usp_sp" && item.id === "artigo_pubmed") {
        pts = freePubmedForItem6 > 0 ? 10 : 0;
      } else if (bId === "usp_sp" && item.id === "artigo_scielo") {
        pts = freePubmedForItem6 > 0 ? 0 : freeScieloForItem6 > 0 ? 8 : 0;
      } else {
        pts = evaluateRulePoints(rule, units);
      }

      if (bId === "usp_rp" && (item.id === "liga_diretoria" || item.id === "liga_membro")) {
        const room = Math.max(0, round2(1.0 - uspRpLigaPts));
        pts = Math.min(pts, room);
        uspRpLigaPts = round2(uspRpLigaPts + pts);
      }

      itemPointsByBank[item.id][bId] = pts;
      if (pts > 0) {
        blockAccumulator[bId][rule.blockId] = round2(
          (blockAccumulator[bId][rule.blockId] || 0) + pts
        );
      }
    }
  }

  // USP-RP Edital 2027: ENAMED soma 0,1 × conceito (0,3 a 0,5 pt) no bloco Histórico
  // quando houver vínculo institucional informado/comprovado (HU ou Pós CAPES).
  const hasInstForUspRp =
    (effectiveUnits.inst_pos_capes || 0) > 0 || (effectiveUnits.inst_hu_proprio || 0) > 0;
  const uspRpEnamedBonus = hasInstForUspRp ? round2(enamedConcept * 0.1) : 0;
  if (uspRpEnamedBonus > 0) {
    blockAccumulator.usp_rp.historico = round2(
      (blockAccumulator.usp_rp.historico || 0) + uspRpEnamedBonus
    );
  }

  return { blockAccumulator, itemPointsByBank, uspRpEnamedBonus };
}

export function computeUnifiedCurriculumScores(
  entries: Record<string, CurriculumEntryState> | undefined,
  options: { enamedConcept?: 3 | 4 | 5 } = {}
): UnifiedCurriculumEvaluation {
  const safeEntries = entries || {};
  const enamedConcept: 3 | 4 | 5 =
    options.enamedConcept === 3 || options.enamedConcept === 4 || options.enamedConcept === 5
      ? options.enamedConcept
      : 5;
  const uspSpMultiplier = enamedConcept === 5 ? 1.2 : enamedConcept === 4 ? 1.1 : 1.0;

  let pdfPronto = 0;
  let emAndamento = 0;
  let falta = 0;
  let filledItems = 0;
  let unfilledItems = 0;

  for (const item of UNIFIED_CURRICULUM_CATALOG) {
    const entry = safeEntries[item.id];
    const clampedUnits = Math.min(item.maxInput, Math.max(0, Number(entry?.value) || 0));
    const status: ProofStatus = entry?.proofStatus || "falta";

    if (clampedUnits > 0) {
      filledItems += 1;
      if (status === "pdf_pronto") pdfPronto += 1;
      else if (status === "em_andamento") emAndamento += 1;
      else falta += 1;
    } else {
      unfilledItems += 1;
    }
  }

  const projectedPass = evaluateEntriesPass(safeEntries, enamedConcept, false);
  const confirmedPass = evaluateEntriesPass(safeEntries, enamedConcept, true);

  const bankIds: CurriculumBankId[] = ["usp_sp", "usp_rp", "unicamp"];
  const banks = {} as Record<CurriculumBankId, BankScoreSummary>;

  for (const bId of bankIds) {
    const cfg = CURRICULUM_BANKS_CONFIG[bId];
    const blocks: CurriculumBlockScore[] = cfg.blocks.map((blk) => {
      const rawScore = round2(projectedPass.blockAccumulator[bId][blk.id] || 0);
      const cappedScore = Math.min(blk.maxPoints, rawScore);
      const confRaw = round2(confirmedPass.blockAccumulator[bId][blk.id] || 0);
      const confirmedCappedScore = Math.min(blk.maxPoints, confRaw);
      const missingToCap = Math.max(0, round2(blk.maxPoints - cappedScore));
      const pct =
        blk.maxPoints > 0 ? Math.min(100, Math.round((cappedScore / blk.maxPoints) * 100)) : 0;
      return {
        blockId: blk.id,
        label: blk.label,
        rawScore,
        cappedScore,
        confirmedCappedScore,
        maxPoints: blk.maxPoints,
        missingToCap,
        pct,
      };
    });

    const rawSubtotal = round2(blocks.reduce((acc, b) => acc + b.cappedScore, 0));
    const confirmedRawSubtotal = round2(blocks.reduce((acc, b) => acc + b.confirmedCappedScore, 0));
    const multiplier = bId === "usp_sp" ? uspSpMultiplier : 1.0;
    const finalScore = Math.min(cfg.escalaMax, round2(rawSubtotal * multiplier));
    const confirmedScore = Math.min(cfg.escalaMax, round2(confirmedRawSubtotal * multiplier));
    const unconfirmedGap = Math.max(0, round2(finalScore - confirmedScore));
    const missingToMax = Math.max(0, round2(cfg.escalaMax - finalScore));
    const pct = cfg.escalaMax > 0 ? Math.min(100, Math.round((finalScore / cfg.escalaMax) * 100)) : 0;
    const confirmedPct =
      cfg.escalaMax > 0 ? Math.min(100, Math.round((confirmedScore / cfg.escalaMax) * 100)) : 0;

    const finalGradeImpactMissing =
      cfg.escalaMax > 0 ? round2((missingToMax / cfg.escalaMax) * cfg.pesoCurriculoPct) : 0;
    const ptsPerQuestion =
      cfg.questoesPrimeiraFase > 0 ? cfg.pesoPrimeiraFasePct / cfg.questoesPrimeiraFase : 1;
    const equivalentFirstPhaseQuestions =
      ptsPerQuestion > 0 ? round2(finalGradeImpactMissing / ptsPerQuestion) : 0;

    banks[bId] = {
      bankId: bId,
      nome: cfg.nome,
      sigla: cfg.sigla,
      escalaMax: cfg.escalaMax,
      rawSubtotal,
      confirmedRawSubtotal,
      multiplier,
      enamedBonusPoints: bId === "usp_rp" ? projectedPass.uspRpEnamedBonus : 0,
      finalScore,
      confirmedScore,
      unconfirmedGap,
      missingToMax,
      pct,
      confirmedPct,
      finalGradeImpactMissing,
      equivalentFirstPhaseQuestions,
      blocks,
    };
  }

  return {
    banks,
    itemPointsByBank: projectedPass.itemPointsByBank,
    proofCounts: {
      pdf_pronto: pdfPronto,
      em_andamento: emAndamento,
      falta,
      filledItems,
      unfilledItems,
      totalItems: UNIFIED_CURRICULUM_CATALOG.length,
    },
  };
}

export function computeCurriculumRoiOpportunities(
  entries: Record<string, CurriculumEntryState> | undefined,
  options: { enamedConcept?: 3 | 4 | 5; limit?: number } = {}
): CurriculumRoiOpportunity[] {
  const safeEntries = entries || {};
  const enamedConcept = options.enamedConcept ?? 5;
  const limit = options.limit ?? 5;
  const baseline = computeUnifiedCurriculumScores(safeEntries, { enamedConcept });

  const effortPenalty: Record<CurriculumEffortLevel, number> = {
    baixo: 1.0,
    medio: 1.45,
    alto: 2.25,
  };

  const opportunities: CurriculumRoiOpportunity[] = [];

  for (const item of UNIFIED_CURRICULUM_CATALOG) {
    if (item.actionable === false) continue;
    const curEntry = safeEntries[item.id];
    const currentValue = Math.min(item.maxInput, Math.max(0, Number(curEntry?.value) || 0));
    if (currentValue >= item.maxInput) continue;

    const deltaStep = item.inputType === "boolean" ? 1 : item.roiStep || item.step || 1;
    const simulatedValue = Math.min(item.maxInput, round2(currentValue + deltaStep));
    if (simulatedValue <= currentValue) continue;

    const simEntries: Record<string, CurriculumEntryState> = {
      ...safeEntries,
      [item.id]: {
        value: simulatedValue,
        proofStatus: curEntry?.proofStatus || "em_andamento",
        notes: curEntry?.notes,
      },
    };

    const simulated = computeUnifiedCurriculumScores(simEntries, { enamedConcept });
    const dSp = round2(simulated.banks.usp_sp.finalScore - baseline.banks.usp_sp.finalScore);
    const dRp = round2(simulated.banks.usp_rp.finalScore - baseline.banks.usp_rp.finalScore);
    const dUni = round2(simulated.banks.unicamp.finalScore - baseline.banks.unicamp.finalScore);

    const combinedFinalPtsDelta = round2(
      (dSp / CURRICULUM_BANKS_CONFIG.usp_sp.escalaMax) * CURRICULUM_BANKS_CONFIG.usp_sp.pesoCurriculoPct +
        (dRp / CURRICULUM_BANKS_CONFIG.usp_rp.escalaMax) * CURRICULUM_BANKS_CONFIG.usp_rp.pesoCurriculoPct +
        (dUni / CURRICULUM_BANKS_CONFIG.unicamp.escalaMax) * CURRICULUM_BANKS_CONFIG.unicamp.pesoCurriculoPct
    );

    if (combinedFinalPtsDelta <= 0.01) continue;

    const effort: CurriculumEffortLevel = item.effortHint || "medio";
    const roiScore = round2(combinedFinalPtsDelta / effortPenalty[effort]);

    opportunities.push({
      itemId: item.id,
      titulo: item.titulo,
      actionLabel: item.roiActionLabel || item.titulo,
      effort,
      currentValue,
      simulatedValue,
      unitLabel: item.unitLabel,
      deltaByBank: {
        usp_sp: dSp,
        usp_rp: dRp,
        unicamp: dUni,
      },
      combinedFinalPtsDelta,
      roiScore,
    });
  }

  opportunities.sort((a, b) => {
    if (b.roiScore !== a.roiScore) return b.roiScore - a.roiScore;
    return b.combinedFinalPtsDelta - a.combinedFinalPtsDelta;
  });

  return opportunities.slice(0, limit);
}
