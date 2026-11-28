// Dados estáticos de exibição para a Central 6º Ano (textos, badges e rótulos).
// NENHUM cálculo de modo do dia ou de meta em TypeScript — toda meta vem do backend.

export type MarchaId = "4_sprint" | "3_normal" | "2_pesada" | "1_sobrevivencia";
export type ShiftKind = "plantao_12h_dia" | "plantao_noturno" | "plantao_24h";
export type DayOverrideMode = "pos_plantao" | "folga" | "meio_periodo" | "integral";
export type WeekPatternMode = "integral" | "meio_periodo" | "folga";
export type WeekdayKey = "seg" | "ter" | "qua" | "qui" | "sex" | "sab" | "dom";

export const NOVO_PEP_BASE_URL = "https://wagmmss.github.io/Novo-PEP";
export const NOVO_PEP_LOGBOOK_URL = `${NOVO_PEP_BASE_URL}/#/6ano/pratica`;
export const NOVO_PEP_ESTEIRA_URL = `${NOVO_PEP_BASE_URL}/#/6ano/teoria`;

export const WEEKDAY_CHIPS: Array<{ key: WeekdayKey; short: string; label: string }> = [
  { key: "seg", short: "Seg", label: "Segunda" },
  { key: "ter", short: "Ter", label: "Terça" },
  { key: "qua", short: "Qua", label: "Quarta" },
  { key: "qui", short: "Qui", label: "Quinta" },
  { key: "sex", short: "Sex", label: "Sexta" },
  { key: "sab", short: "Sáb", label: "Sábado" },
  { key: "dom", short: "Dom", label: "Domingo" },
];

export const SHIFT_KIND_META: Record<ShiftKind, { label: string; short: string; description: string }> = {
  plantao_12h_dia: {
    label: "Plantão 12h diurno",
    short: "12h Dia",
    description: "Reduz a meta do dia; não gera pós-plantão no dia seguinte.",
  },
  plantao_noturno: {
    label: "Plantão noturno",
    short: "Noturno",
    description: "Entrada de plantão hoje + pós-plantão automático (meta 0) amanhã.",
  },
  plantao_24h: {
    label: "Plantão 24h",
    short: "24h",
    description: "Meta 0 hoje e pós-plantão automático (meta 0) amanhã. Peso 2 na Marcha.",
  },
};

export const DAY_MODE_DISPLAY: Record<
  string,
  { label: string; short: string; tone: "muted" | "accent" | "warning" | "normal" | "destructive" }
> = {
  pos_plantao: { label: "Pós-plantão", short: "Pós-pl.", tone: "muted" },
  plantao_24h: { label: "Plantão 24h", short: "24h", tone: "destructive" },
  entrada_noturno: { label: "Entrada de noturno", short: "Noturno", tone: "warning" },
  plantao_12h_dia: { label: "Plantão 12h diurno", short: "12h Dia", tone: "warning" },
  integral: { label: "Integral", short: "Integral", tone: "accent" },
  meio_periodo: { label: "Meio período", short: "Meio per.", tone: "accent" },
  folga: { label: "Folga / FDS", short: "Folga", tone: "normal" },
};

export const DAY_SOURCE_LABELS: Record<string, string> = {
  override: "ajuste manual",
  shift: "plantão",
  pos_plantao: "pós-plantão",
  pattern: "padrão do rodízio",
};

export interface MarchaStaticInfo {
  id: MarchaId;
  nome: string;
  short: string;
  badge: string;
  resumo: string;
}

export const MARCHAS_6ANO: Record<MarchaId, MarchaStaticInfo> = {
  "4_sprint": {
    id: "4_sprint",
    nome: "Marcha 4 — Consolidação Intensiva",
    short: "Sprint",
    badge: "1,5×",
    resumo: "Provas antigas cronometradas (USP-SP/USP-RP/UNICAMP) + revisão cirúrgica de erros.",
  },
  "3_normal": {
    id: "3_normal",
    nome: "Marcha Normal",
    short: "Normal",
    badge: "1,0×",
    resumo: "Carga padrão do internato. Esteira v3.1 em ritmo normal e blocos 70/30.",
  },
  "2_pesada": {
    id: "2_pesada",
    nome: "Semana Pesada",
    short: "Pesada",
    badge: "0,72×",
    resumo: "2+ plantões na semana. Ativa modo Semana Pesada na Esteira v3.1; estudo enxuto e sono protegido.",
  },
  "1_sobrevivencia": {
    id: "1_sobrevivencia",
    nome: "Sobrevivência",
    short: "Sobrevivência",
    badge: "0,4×",
    resumo: "Semana caótica (3+ pesos de plantão). Zero teoria nova nos dias úteis; foco em proteger o sono.",
  },
};

export const MARCHA_ORDER: MarchaId[] = ["4_sprint", "3_normal", "2_pesada", "1_sobrevivencia"];

export const RITUAL_DOMINGO_DATA: Array<{ id: string; text: string }> = [
  {
    id: "rit-escala",
    text: "Definir a Marcha da semana conforme plantões e carga real do internato (sincroniza a Esteira v3.1).",
  },
  {
    id: "rit-7030",
    text: "Confirmar ou ajustar os subtemas da semana: 70% Rodízio-Âncora + 30% Trilha Paralela.",
  },
  {
    id: "rit-habito",
    text: "Revisar pendências clínicas: itens [CHECAR] na Esteira, Pontos Cegos abertos e Logbook 3x.",
  },
  {
    id: "rit-curriculo",
    text: "Avançar 1 pendência de comprovante na matriz R1 & Currículo (corte 30/06/2027).",
  },
];

export interface FeriasSemanaStatic {
  id: string;
  de: string;
  ate: string;
  label: string;
  focoConteudo: string;
  focoExames: string;
  focoHabilidade: string;
  isFreeWeek?: boolean;
}

export const FERIAS_SEMANAS: FeriasSemanaStatic[] = [
  {
    id: "sem1",
    de: "2026-11-30",
    ate: "2026-12-06",
    label: "Semana 1 (30/11 a 04/12 · 5d) — Cirurgia I: Abdome Agudo Inflamatório/Obstrutivo",
    focoConteudo:
      "Apendicite, colecistite/colangite, diverticulite, pancreatite aguda, obstrução intestinal e hérnias",
    focoExames: "Semana cheia v3.1 (~290m Seg–Sex): BASELINE-A em 30/11; 3 (D1+A) + 1 C + 1 B + visual aplicável",
    focoHabilidade: "Seg–Sex (~3h/dia total; Sáb/Dom 0 min de habilidades; foco em 3H ≤ 60s e 1ª passada E1)",
  },
  {
    id: "sem2",
    de: "2026-12-07",
    ate: "2026-12-13",
    label: "Semana 2 (07/12 a 11/12 · 5d) — Cirurgia II: Vascular/Perfurativo, Pós-Op & Trauma",
    focoConteudo:
      "Úlcera perfurada, isquemia mesentérica, complicações pós-op (5 Ws, deiscência, TEP) e ATLS inicial / choque hemorrágico",
    focoExames: "Semana cheia v3.1 (~290m Seg–Sex): 3 (D1+A) + 1 C + 1 B + 10 min EF + gravação 5m",
    focoHabilidade: "Avançar 1ª passada E1 + checagem [CHECAR] em diretriz/protocolo/bula",
  },
  {
    id: "sem3",
    de: "2026-12-14",
    ate: "2026-12-20",
    label: "Semana 3 (14/12 a 18/12 · 5d) — Anestesio & CTI I: Via Aérea, Choque, Sepse e DVA",
    focoConteudo:
      "Pré-anestésico (ASA, Mallampati, jejum), via aérea/SRI, choque (4 tipos), sepse/ILAS, noradrenalina/vasopressina e sedação",
    focoExames: "Semana cheia v3.1 (~290m Seg–Sex): 3 (D1+A) + 1 C + 1 B + revisão de Não Pode Passar",
    focoHabilidade: "Priorizar D(1) para retestar queixas com falha recente e confirmar sequências em dias distintos",
  },
  {
    id: "sem4",
    de: "2026-12-21",
    ate: "2026-12-27",
    label: "Semana 4 (21/12 a 23/12 · 3d · Folga Natal 24–25/12) — Anestesio & CTI II (Enxuta)",
    focoConteudo:
      "Distúrbios Na+/K+/Ca2+, Injúria Renal Aguda (IRA) e Ventilação Mecânica básica (VCV/PCV, PEEP, driving pressure)",
    focoExames: "Semana reduzida de Natal (Seg–Qua): 2 (D1+A) + 1 C (Qua 23/12) · Folga oficial 24–25/12",
    focoHabilidade: "Cadência curta de 3 dias sem dívida no Natal",
  },
  {
    id: "sem5",
    de: "2026-12-28",
    ate: "2027-01-03",
    label: "Semana 5 (28/12 a 30/12 · 3d · Folga Ano-Novo 31/12–01/01) — Obstetrícia (Lacunas Pós-Prova)",
    focoConteudo:
      "Vitalidade fetal/CTG, pré-natal de alto risco/DMG, infecções congênitas (sífilis/toxo/GBS) + doses MgSO4/HPP",
    focoExames: "Semana reduzida de Ano-Novo (Seg–Qua): 2 (D1+A) + 1 B + EF/Gravação (Qua 30/12) · Folga 31/12–01/01",
    focoHabilidade: "Prescrição segura (Prompt B) + limpeza de itens [CHECAR] pendentes antes de janeiro",
  },
  {
    id: "sem6",
    de: "2027-01-04",
    ate: "2027-01-10",
    label: "Semana 6 (04/01 a 08/01 · 5d · Contingência 10/01) — Clínica Crítica (CTI/PS) + Reforço Cirurgia",
    focoConteudo:
      "ACLS/arritmias e SCA, insuf. respiratória/TEP, CAD/EHH + reforço Cirurgia (vias biliares, trauma, onco básica)",
    focoExames: "Semana cheia v3.1 (~290m Seg–Sex): 3 (D1+A) + 1 C + 1 B · Marco 3H ≥ 80% em 10/01",
    focoHabilidade: "Consolidar queixas E1 em caminho de domínio (meta ≥ 6 dominadas até 24/01)",
  },
  {
    id: "sem7",
    de: "2027-01-11",
    ate: "2027-01-17",
    label: "Semana Livre (11/01 a 17/01/2027 · 0d) — Viagem & Pausa Total",
    focoConteudo: "ZERO estudo teórico novo e ZERO questões.",
    focoExames: "Pausa total na Esteira v3.1 (0 sessões).",
    focoHabilidade: "Descanso integral antes da última semana pré-Cirurgia.",
    isFreeWeek: true,
  },
  {
    id: "sem8",
    de: "2027-01-18",
    ate: "2027-01-24",
    label: "Semana 7 Útil (18/01 a 22/01 · 5d · Baseline B 24/01) — Ponte Pré-Cirurgia & Fechamento",
    focoConteudo: "2–3 blocos refazendo erros de Cirurgia (S1–S2: abdome agudo, pós-op, trauma) + lacunas CTI/PS",
    focoExames: "Semana cheia v3.1 (18–22/01): 3 (D1+A) + 1 C + 1 B · Dom 24/01: Baseline Caso B + 15 min revisão LOG",
    focoHabilidade: "Fechar 1ª passada e destravar Cirurgia Geral em 25/01",
  },
];

export const AREAS_MEDQUEST = [
  "Clínica Médica",
  "Cirurgia",
  "Ginecologia e Obstetrícia",
  "Pediatria",
  "Preventiva",
  "Medicina Intensiva",
  "Especialidades",
  "Geral",
] as const;
