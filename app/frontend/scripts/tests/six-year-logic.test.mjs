import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { registerHooks } from "node:module";

// Permite que módulos TS com imports relativos sem extensão (ex.: "./curriculumCatalog")
// sejam carregados diretamente pelo `node --test` no Node 22+.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (
      (specifier.startsWith("./") || specifier.startsWith("../")) &&
      !path.extname(specifier) &&
      context.parentURL?.startsWith("file:")
    ) {
      const parentDir = path.dirname(fileURLToPath(context.parentURL));
      const tsCandidate = path.resolve(parentDir, `${specifier}.ts`);
      if (fs.existsSync(tsCandidate)) {
        return { url: pathToFileURL(tsCandidate).href, shortCircuit: true };
      }
    }
    return nextResolve(specifier, context);
  },
});

const {
  computeUnifiedCurriculumScores,
  computeCurriculumRoiOpportunities,
  evaluateRulePoints,
} = await import("../../src/lib/sixYear/curriculumEngine.ts");
const { computeMilestoneCountdown } = await import("../../src/lib/sixYear/milestones.ts");
const { parsePastedDates } = await import("../../src/lib/sixYear/datePasteParser.ts");

test("curriculumEngine: empty entries produce zero scores and positive ROI opportunities", () => {
  const res = computeUnifiedCurriculumScores({}, { enamedConcept: 5 });
  assert.equal(res.banks.usp_sp.finalScore, 0);
  assert.equal(res.banks.usp_rp.finalScore, 0);
  assert.equal(res.banks.unicamp.finalScore, 0);
  assert.equal(res.proofCounts.filledItems, 0);

  const roi = computeCurriculumRoiOpportunities({}, { enamedConcept: 5, limit: 5 });
  assert.ok(roi.length > 0);
  assert.ok(roi[0].roiScore >= roi[roi.length - 1].roiScore);
});

test("curriculumEngine: ENAMED multiplier on USP-SP and bonus on USP-RP respect caps", () => {
  const synthEntries = {
    inst_pos_capes: { value: 1, proofStatus: "pdf_pronto" },
    inst_hu_proprio: { value: 1, proofStatus: "pdf_pronto" },
    inst_sus_rede: { value: 1, proofStatus: "em_andamento" },
    ic_com_bolsa: { value: 2, proofStatus: "pdf_pronto" },
  };

  const c5 = computeUnifiedCurriculumScores(synthEntries, { enamedConcept: 5 });
  const c4 = computeUnifiedCurriculumScores(synthEntries, { enamedConcept: 4 });
  const c3 = computeUnifiedCurriculumScores(synthEntries, { enamedConcept: 3 });

  // USP-SP aplica multiplicador 1.2 / 1.1 / 1.0
  assert.equal(c5.banks.usp_sp.multiplier, 1.2);
  assert.equal(c4.banks.usp_sp.multiplier, 1.1);
  assert.equal(c3.banks.usp_sp.multiplier, 1.0);
  assert.ok(c5.banks.usp_sp.finalScore > c4.banks.usp_sp.finalScore);
  assert.ok(c4.banks.usp_sp.finalScore > c3.banks.usp_sp.finalScore);

  // Comprovado exclui item em_andamento (inst_sus_rede)
  assert.ok(c5.banks.usp_sp.confirmedScore < c5.banks.usp_sp.finalScore);
  assert.equal(c5.proofCounts.pdf_pronto, 3);
  assert.equal(c5.proofCounts.em_andamento, 1);

  // USP-RP soma 0.5 / 0.4 / 0.3 no bloco histórico (cap 1.5)
  assert.equal(c5.banks.usp_rp.enamedBonusPoints, 0.5);
  assert.equal(c4.banks.usp_rp.enamedBonusPoints, 0.4);
  assert.equal(c3.banks.usp_rp.enamedBonusPoints, 0.3);
  const hist5 = c5.banks.usp_rp.blocks.find((b) => b.blockId === "historico");
  assert.equal(hist5?.cappedScore, 1.5);
});

test("curriculumEngine: USP-SP IC-linked article does not double-count in Item 6", () => {
  // 1 projeto IC com bolsa + 1 artigo PubMed vinculado à IC -> 0 artigos livres para Item 6
  const oneLinked = computeUnifiedCurriculumScores(
    {
      ic_com_bolsa: { value: 1, proofStatus: "pdf_pronto" },
      artigo_pubmed: { value: 1, proofStatus: "pdf_pronto" },
      ic_artigo_vinculado: { value: 1, proofStatus: "pdf_pronto" },
    },
    { enamedConcept: 3 }
  );
  assert.equal(oneLinked.itemPointsByBank.ic_artigo_vinculado.usp_sp, 4);
  assert.equal(oneLinked.itemPointsByBank.artigo_pubmed.usp_sp, 0);

  // 2 artigos PubMed (1 vinculado + 1 livre) -> libera 10 pts no Item 6
  const twoArticles = computeUnifiedCurriculumScores(
    {
      ic_com_bolsa: { value: 1, proofStatus: "pdf_pronto" },
      artigo_pubmed: { value: 2, proofStatus: "pdf_pronto" },
      ic_artigo_vinculado: { value: 1, proofStatus: "pdf_pronto" },
    },
    { enamedConcept: 3 }
  );
  assert.equal(twoArticles.itemPointsByBank.ic_artigo_vinculado.usp_sp, 4);
  assert.equal(twoArticles.itemPointsByBank.artigo_pubmed.usp_sp, 10);
});

test("evaluateRulePoints respects tiered rules and maxItemPoints", () => {
  const rule = {
    blockId: "test",
    perUnit: 1,
    maxItemPoints: 5,
    tiers: [
      { minUnits: 1, points: 2 },
      { minUnits: 2, points: 5 },
    ],
    note: "",
  };
  assert.equal(evaluateRulePoints(rule, 0), 0);
  assert.equal(evaluateRulePoints(rule, 1), 2);
  assert.equal(evaluateRulePoints(rule, 3), 5);
});

test("computeMilestoneCountdown classifies overdue, today, soon, and upcoming", () => {
  const ref = new Date(2027, 1, 4); // 2027-02-04

  const past = computeMilestoneCountdown(
    { id: "m1", titulo: "Passado", data_iso: "2027-02-01", categoria: "prova" },
    ref
  );
  assert.equal(past.status, "overdue");
  assert.equal(past.daysLeft, -3);

  const today = computeMilestoneCountdown(
    { id: "m2", titulo: "Hoje", data_iso: "2027-02-04", categoria: "prova" },
    ref
  );
  assert.equal(today.status, "soon");
  assert.equal(today.daysLeft, 0);
  assert.equal(today.label, "Hoje");

  const soon = computeMilestoneCountdown(
    { id: "m3", titulo: "Em breve", data_iso: "2027-03-06", categoria: "curriculo" },
    ref
  );
  assert.equal(soon.status, "soon");
  assert.equal(soon.daysLeft, 30);

  const future = computeMilestoneCountdown(
    { id: "m4", titulo: "Futuro", data_iso: "2027-10-15", categoria: "prova" },
    ref
  );
  assert.equal(future.status, "upcoming");
  assert.ok(future.daysLeft > 200);
});

test("parsePastedDates handles dd/mm, dd/mm/aaaa, ISO, invalid dates, deduplication, and year rollover", () => {
  const parsed = parsePastedDates(
    "04/02, 11/02/2027\n2027-02-18; 04/02 31/02/2027 foo 05/01",
    {
      referenceDateIso: "2026-12-20",
      rodizioStartIso: "2026-11-30",
      rodizioEndIso: "2027-01-24",
    }
  );

  // 05/01 cai dentro do rodízio (2027-01-05); 04/02 é próxima ocorrência (2027-02-04)
  assert.deepEqual(
    parsed.valid.map((v) => v.dateIso),
    ["2027-01-05", "2027-02-04", "2027-02-11", "2027-02-18"]
  );
  assert.equal(parsed.duplicatesRemoved, 1);
  assert.deepEqual(parsed.invalid, ["31/02/2027", "foo"]);
  assert.equal(parsed.valid[0].inferredYear, true);
  assert.equal(parsed.valid[2].inferredYear, false);
});
