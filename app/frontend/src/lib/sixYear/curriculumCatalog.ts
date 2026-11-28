// Port 1:1 do catálogo unificado de currículo (editais 2027: USP-SP, USP-RP, UNICAMP).
// Sem dados pessoais ou inventário baseline.

export type CurriculumBankId = 'usp_sp' | 'usp_rp' | 'unicamp';
export type ProofStatus = 'falta' | 'em_andamento' | 'pdf_pronto';
export type CurriculumEffortLevel = 'baixo' | 'medio' | 'alto';
export type CurriculumCategoryId =
  | 'institucional'
  | 'cientifico'
  | 'ensino_ligas'
  | 'assistencial_cursos'
  | 'representacao';

export interface CurriculumBlockDef {
  id: string;
  label: string;
  maxPoints: number;
}

export interface CurriculumBankConfig {
  id: CurriculumBankId;
  nome: string;
  sigla: string;
  escalaMax: number;
  pesoNotaFinal: string;
  psiquiatriaPesos: string;
  pesoCurriculoPct: number;
  pesoPrimeiraFasePct: number;
  questoesPrimeiraFase: number;
  editalRef: string;
  dicaEnvio: string;
  blocks: CurriculumBlockDef[];
}

export interface BankItemRule {
  blockId: string;
  perUnit: number;
  maxItemPoints: number;
  /** Regra opcional por faixa (ex.: UNICAMP IC/Monitoria/Voluntariado, USP-SP Monitoria/Extensão/Rep.) */
  tiers?: Array<{ minUnits: number; points: number }>;
  note: string;
}

export interface CurriculumCatalogItem {
  id: string;
  categoria: CurriculumCategoryId;
  titulo: string;
  descricao: string;
  inputType: 'boolean' | 'number';
  unitLabel?: string;
  step?: number;
  maxInput: number;
  defaultValue?: number;
  /** Se false, não entra nas recomendações de ROI (ex.: estrutura da faculdade ou 2ª graduação). */
  actionable?: boolean;
  effortHint?: CurriculumEffortLevel;
  /** Incremento realista simulado pelo motor de ROI (padrão = step ou 1). */
  roiStep?: number;
  roiActionLabel?: string;
  rules: Partial<Record<CurriculumBankId, BankItemRule>>;
}

export interface CurriculumEntryState {
  value: number;
  proofStatus: ProofStatus;
  notes?: string;
}


export const CURRICULUM_BANKS_CONFIG: Record<CurriculumBankId, CurriculumBankConfig> = {
  usp_sp: {
    id: 'usp_sp',
    nome: 'USP-SP (FMUSP / FUVEST)',
    sigla: 'USP-SP',
    escalaMax: 100,
    pesoNotaFinal: '10% (Peso 1 · 0–100)',
    psiquiatriaPesos: '90% 1ª Fase (120q) · 10% Currículo',
    pesoCurriculoPct: 10,
    pesoPrimeiraFasePct: 90,
    questoesPrimeiraFase: 120,
    editalRef: 'Edital COREME/FM nº 02/2026 (Ingresso 2027): 13 blocos = 100 pts × Fator ENAMED (1,0×/1,1×/1,2×, teto 100).',
    dicaEnvio:
      'PDF individual por item na Área do Candidato FUVEST (frente e verso legíveis no mesmo PDF). Extensão exige chancela da CCEx/Diretoria; Ligas foram retiradas do Item 10 em 2027.',
    blocks: [
      { id: 'inst_pos', label: '1. Pós CAPES / Sucupira', maxPoints: 15 },
      { id: 'inst_hu', label: '2. Hospital de Ensino', maxPoints: 12 },
      { id: 'inst_sus', label: '3. Rede SUS 1º/2º/3º', maxPoints: 8 },
      { id: 'monitoria', label: '4. Monitoria Oficial', maxPoints: 3 },
      { id: 'ic', label: '5. Iniciação Científica', maxPoints: 12 },
      { id: 'publicacao', label: '6. Publicação (fora da IC)', maxPoints: 10 },
      { id: 'org_eventos', label: '7. Org. Congressos/Eventos', maxPoints: 6 },
      { id: 'oral', label: '8. Oral (1º Autor)', maxPoints: 8 },
      { id: 'poster', label: '9. Pôster (1º Autor)', maxPoints: 6 },
      { id: 'extensao', label: '10. Extensão Acadêmica', maxPoints: 5 },
      { id: 'aprimoramento', label: '11. Aprimoramento / 2ª Grad.', maxPoints: 8 },
      { id: 'suporte_vida', label: '12. Suporte de Vida', maxPoints: 4 },
      { id: 'rep_estudantil', label: '13. Rep. Estudantil & Esporte', maxPoints: 3 },
    ],
  },
  usp_rp: {
    id: 'usp_rp',
    nome: 'USP-RP (FMRP / HC-FMRP)',
    sigla: 'USP-RP',
    escalaMax: 10,
    pesoNotaFinal: '10% (Peso 1 · 0–10)',
    psiquiatriaPesos: '50% 1ª Fase (100q) · 40% Prática · 10% Currículo',
    pesoCurriculoPct: 10,
    pesoPrimeiraFasePct: 50,
    questoesPrimeiraFase: 100,
    editalRef: 'Edital HC-FMRP Ingresso 2027 (Psiquiatria: 3 fases · 5 eixos = 10,0 pts; ENAMED até 0,5 pt no Histórico).',
    dicaEnvio:
      'Upload no portal HCRP após 1ª fase com timbre, período/carga horária e assinaturas. Sem ACLS/esporte tabelados; Teste de Progresso entra em Ensino.',
    blocks: [
      { id: 'historico', label: '1. Histórico & ENAMED', maxPoints: 1.5 },
      { id: 'assistencial', label: '2. Assistencial Extra', maxPoints: 2.0 },
      { id: 'cientifico', label: '3. Atividades Científicas', maxPoints: 3.0 },
      { id: 'ensino', label: '4. Ensino & Provas', maxPoints: 1.5 },
      { id: 'estudantil', label: '5. Atividades Estudantis', maxPoints: 2.0 },
    ],
  },
  unicamp: {
    id: 'unicamp',
    nome: 'UNICAMP (FCM / COMVEST)',
    sigla: 'UNICAMP',
    escalaMax: 100,
    pesoNotaFinal: '10% (Peso 10 · 0–100)',
    psiquiatriaPesos: '90% Discursiva (100q) · 10% Currículo',
    pesoCurriculoPct: 10,
    pesoPrimeiraFasePct: 90,
    questoesPrimeiraFase: 100,
    editalRef: 'Edital FCM/UNICAMP 2026/2027 (Acesso Direto: 11 blocos = 100 pts).',
    dicaEnvio:
      'PDF único ≤ 5 MB contendo formulário FCM + Lattes + comprovantes rigorosamente na ordem dos 11 itens. Não enviar dentro do prazo elimina do processo.',
    blocks: [
      { id: 'pos_fac', label: '1. Pós CAPES na Faculdade', maxPoints: 15 },
      { id: 'hu', label: '2. Hospital de Ensino', maxPoints: 10 },
      { id: 'ic', label: '3. Iniciação Científica', maxPoints: 20 },
      { id: 'artigos', label: '4. Artigos Completos', maxPoints: 15 },
      { id: 'congresso', label: '5. Trabalhos em Congresso', maxPoints: 10 },
      { id: 'liga', label: '6. Liga Acadêmica', maxPoints: 5 },
      { id: 'aprimoramento', label: '7. Cursos & Suporte Vida', maxPoints: 5 },
      { id: 'monitoria', label: '8. Monitoria / PAD', maxPoints: 5 },
      { id: 'extensao', label: '9. Voluntariado Social', maxPoints: 5 },
      { id: 'rep_colegiado', label: '10. Colegiados Institucionais', maxPoints: 5 },
      { id: 'rep_discente', label: '11. CA / Atlética / Esporte', maxPoints: 5 },
    ],
  },
};

export const CURRICULUM_CATEGORIES_META: Record<CurriculumCategoryId, { label: string }> = {
  institucional: { label: 'Institucional & Formação' },
  cientifico: { label: 'Pesquisa, Artigos & Congressos' },
  ensino_ligas: { label: 'Monitoria, Ligas & Eventos' },
  assistencial_cursos: { label: 'Extensão, Estágios & Cursos' },
  representacao: { label: 'Representação, Esporte & Provas' },
};

/**
 * Catálogo unificado auditado pelos editais oficiais 2027 (USP-SP, USP-RP, UNICAMP).
 * Preencher 1 vez calcula simultaneamente nas 3 bancas respeitando tetos de bloco,
 * multiplicador/bônus ENAMED e regra de não-duplicação IC vs. Artigo na USP-SP.
 */
export const UNIFIED_CURRICULUM_CATALOG: CurriculumCatalogItem[] = [
  // 1. INSTITUCIONAL & FORMAÇÃO
  {
    id: 'inst_pos_capes',
    categoria: 'institucional',
    titulo: 'Faculdade com Pós-Graduação Stricto Sensu (Doutorado CAPES)',
    descricao: 'Declaração oficial da CPG listando programas Medicina I/II/III credenciados (≥ 5 programas / Sucupira).',
    inputType: 'boolean',
    maxInput: 1,
    actionable: false,
    rules: {
      usp_sp: { blockId: 'inst_pos', perUnit: 15, maxItemPoints: 15, note: 'Item 1 (2027): Pós CAPES/Sucupira até 15 pts' },
      usp_rp: { blockId: 'historico', perUnit: 0.5, maxItemPoints: 0.5, note: 'Item 1: ≥ 5 programas CAPES = 0,5 pt (+ ENAMED até 0,5)' },
      unicamp: { blockId: 'pos_fac', perUnit: 15, maxItemPoints: 15, note: 'Item 1a: Doutorado stricto sensu = 15 pts' },
    },
  },
  {
    id: 'inst_hu_proprio',
    categoria: 'institucional',
    titulo: 'Hospital de Ensino Próprio (HU / HCRP)',
    descricao: 'Termo emitido pelo Serviço Acadêmico / Comissão de Graduação comprovando hospital universitário próprio.',
    inputType: 'boolean',
    maxInput: 1,
    actionable: false,
    rules: {
      usp_sp: { blockId: 'inst_hu', perUnit: 12, maxItemPoints: 12, note: 'Item 2a: Hospital de ensino próprio = 12 pts' },
      usp_rp: { blockId: 'historico', perUnit: 0.5, maxItemPoints: 0.5, note: 'Item 1: HU próprio = 0,5 pt (soma c/ CAPES + ENAMED = 1,5)' },
      unicamp: { blockId: 'hu', perUnit: 10, maxItemPoints: 10, note: 'Item 2a: HU próprio = 10 pts' },
    },
  },
  {
    id: 'inst_sus_rede',
    categoria: 'institucional',
    titulo: 'Centro Assistencial Próprio SUS (Primário, Secundário e Terciário)',
    descricao: 'Declaração do Serviço Acadêmico com nome, endereço e telefone dos locais da rede SUS 1º/2º/3º (Portaria 4.279).',
    inputType: 'boolean',
    maxInput: 1,
    actionable: false,
    rules: {
      usp_sp: { blockId: 'inst_sus', perUnit: 8, maxItemPoints: 8, note: 'Item 3a: Rede SUS 1º, 2º e 3º níveis = 8 pts' },
    },
  },
  {
    id: 'outra_graduacao_pos',
    categoria: 'institucional',
    titulo: 'Outro Curso Universitário Concluído (ex.: Psicologia)',
    descricao: 'Diploma de graduação prévia reconhecida pelo MEC (Item 11d USP-SP). Mestrado (4) / Doutorado (8) entram no mesmo bloco.',
    inputType: 'boolean',
    maxInput: 1,
    actionable: false,
    rules: {
      usp_sp: { blockId: 'aprimoramento', perUnit: 1, maxItemPoints: 1, note: 'Item 11d: Outro curso universitário concluído = 1 pt (bloco teto 8)' },
    },
  },

  // 2. CIENTÍFICO (IC, ARTIGOS, CONGRESSOS)
  {
    id: 'ic_com_bolsa',
    categoria: 'cientifico',
    titulo: 'Iniciação Científica COM Bolsa (FAPESP / CNPq / PIBIC)',
    descricao: 'Informe em anos concluídos (1 ano = 2 semestres). Exige declaração institucional + agência de fomento e carga horária.',
    inputType: 'number',
    unitLabel: 'anos',
    step: 0.5,
    maxInput: 4,
    actionable: true,
    effortHint: 'alto',
    roiStep: 1,
    roiActionLabel: 'Concluir +1 ano de IC com bolsa',
    rules: {
      usp_sp: {
        blockId: 'ic',
        perUnit: 2,
        maxItemPoints: 4,
        note: 'Item 5b: 2 pts/projeto (2 sem) s/ artigo; sobe p/ 6 pts/projeto (teto 12) com artigo vinculado à IC',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 0.7,
        maxItemPoints: 1.4,
        note: 'Item 3: 0,7 pt/ano (mín. 1 ano; teto 1,4)',
      },
      unicamp: {
        blockId: 'ic',
        perUnit: 15,
        maxItemPoints: 20,
        tiers: [
          { minUnits: 1.5, points: 20 },
          { minUnits: 0.5, points: 15 },
        ],
        note: 'Item 3a: > 2 sem = 20 pts; até 2 sem = 15 pts',
      },
    },
  },
  {
    id: 'ic_sem_bolsa',
    categoria: 'cientifico',
    titulo: 'Iniciação Científica SEM Bolsa (Institucional Oficial)',
    descricao: 'Vigência institucional oficial sem fomento (em anos) com carga horária e assinatura do orientador/instituição.',
    inputType: 'number',
    unitLabel: 'anos',
    step: 0.5,
    maxInput: 4,
    actionable: true,
    effortHint: 'alto',
    roiStep: 1,
    roiActionLabel: 'Concluir +1 ano de IC sem bolsa',
    rules: {
      usp_sp: {
        blockId: 'ic',
        perUnit: 1,
        maxItemPoints: 2,
        note: 'Item 5: 1 pt/projeto s/ artigo; sobe p/ 4 pts/projeto (teto 8) se tiver artigo vinculado',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 0.5,
        maxItemPoints: 1.0,
        note: 'Item 3: 0,5 pt/ano sem bolsa (teto 1,0)',
      },
      unicamp: {
        blockId: 'ic',
        perUnit: 5,
        maxItemPoints: 10,
        tiers: [
          { minUnits: 1.5, points: 10 },
          { minUnits: 0.5, points: 5 },
        ],
        note: 'Item 3b: > 2 sem = 10 pts; até 2 sem = 5 pts',
      },
    },
  },
  {
    id: 'ic_artigo_vinculado',
    categoria: 'cientifico',
    titulo: 'Projetos de IC com Artigo Aceito / Publicado (Bônus USP-SP)',
    descricao: 'Quantos dos seus artigos abaixo derivam diretamente de projetos de IC. Na USP-SP eleva o projeto de 2→6 pts (e desconta do Item 6).',
    inputType: 'number',
    unitLabel: 'projetos',
    step: 1,
    maxInput: 2,
    actionable: true,
    effortHint: 'medio',
    roiStep: 1,
    roiActionLabel: 'Publicar artigo derivado do 2º projeto de IC',
    rules: {
      usp_sp: {
        blockId: 'ic',
        perUnit: 4,
        maxItemPoints: 8,
        note: 'Item 5a: +4 pts/proj c/ bolsa (total 6/proj) ou +3 pts s/ bolsa; artigo usado aqui não repete no Item 6',
      },
    },
  },
  {
    id: 'artigo_pubmed',
    categoria: 'cientifico',
    titulo: 'Artigo Científico Completo Publicado / Aceito (PubMed / JCR)',
    descricao: 'Informe o TOTAL de artigos PubMed (incluindo o da IC). Anexar cópia completa + DOI. Resumos em anais não contam.',
    inputType: 'number',
    unitLabel: 'artigos',
    step: 1,
    maxInput: 6,
    actionable: true,
    effortHint: 'alto',
    roiStep: 1,
    roiActionLabel: 'Publicar +1 artigo completo indexado no PubMed',
    rules: {
      usp_sp: {
        blockId: 'publicacao',
        perUnit: 10,
        maxItemPoints: 10,
        note: 'Item 6a: 10 pts (máx 1 artigo DIFERENTE do usado na IC)',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 1.0,
        maxItemPoints: 3.0,
        note: 'Item 3: 1,0 pt/artigo c/ DOI (bloco teto 3,0)',
      },
      unicamp: {
        blockId: 'artigos',
        perUnit: 10,
        maxItemPoints: 15,
        note: 'Item 4a: 10 pts/artigo PubMed c/ DOI (teto 15)',
      },
    },
  },
  {
    id: 'artigo_scielo',
    categoria: 'cientifico',
    titulo: 'Artigo Científico Completo Publicado / Aceito (SciELO / LILACS)',
    descricao: 'Artigo completo indexado em SciELO/LILACS/Scopus com DOI. Na USP-RP vale 1,0 pt igual PubMed.',
    inputType: 'number',
    unitLabel: 'artigos',
    step: 1,
    maxInput: 6,
    actionable: true,
    effortHint: 'alto',
    roiStep: 1,
    roiActionLabel: 'Publicar +1 artigo completo SciELO/LILACS',
    rules: {
      usp_sp: {
        blockId: 'publicacao',
        perUnit: 8,
        maxItemPoints: 8,
        note: 'Item 6b: 8 pts (máx 1 artigo DIFERENTE do usado na IC)',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 1.0,
        maxItemPoints: 3.0,
        note: 'Item 3: 1,0 pt/artigo SciELO/LILACS/Scopus c/ DOI (teto 3,0)',
      },
      unicamp: {
        blockId: 'artigos',
        perUnit: 5,
        maxItemPoints: 15,
        note: 'Item 4b: 5 pts/artigo SciELO (teto 15)',
      },
    },
  },
  {
    id: 'congresso_oral',
    categoria: 'cientifico',
    titulo: 'Apresentação ORAL em Congresso de Sociedade (Nacional / Int.)',
    descricao: 'Certificado especificando apresentação oral e 1º autor (exigido na USP-SP). Na UNICAMP vale autor ou coautor.',
    inputType: 'number',
    unitLabel: 'trabalhos',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'medio',
    roiStep: 1,
    roiActionLabel: 'Apresentar 1 trabalho ORAL (1º autor) em congresso de sociedade',
    rules: {
      usp_sp: {
        blockId: 'oral',
        perUnit: 7,
        maxItemPoints: 8,
        note: 'Item 8: 1º autor oral Nacional = 7 pts (Int. = 8 pts; teto bloco 8)',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 0.5,
        maxItemPoints: 1.0,
        note: 'Item 3: 0,5 pt/apresentação oral (teto 1,0)',
      },
      unicamp: {
        blockId: 'congresso',
        perUnit: 10,
        maxItemPoints: 10,
        note: 'Item 5a.1: Oral em Congresso de Sociedade = 10 pts (teto 10)',
      },
    },
  },
  {
    id: 'congresso_poster',
    categoria: 'cientifico',
    titulo: 'Pôster em Congresso de Sociedade Médica (1º Autor)',
    descricao: 'Certificado de congresso de sociedade nacional/internacional indicando 1º autor (USP-SP exige 1º autor; USP-RP 1º/2º).',
    inputType: 'number',
    unitLabel: 'pôsteres',
    step: 1,
    maxInput: 6,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Apresentar 1 pôster (1º autor) em congresso nacional de sociedade',
    rules: {
      usp_sp: {
        blockId: 'poster',
        perUnit: 4,
        maxItemPoints: 6,
        note: 'Item 9b: 1º autor Nacional = 4 pts (Int. = 6 pts; teto bloco 6)',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 0.15,
        maxItemPoints: 0.6,
        note: 'Item 3: Pôster 1º/2º autor (Reg 0,1 / Nac 0,15 / Int 0,3 · teto 0,6)',
      },
      unicamp: {
        blockId: 'congresso',
        perUnit: 6,
        maxItemPoints: 10,
        note: 'Item 5a.2: Pôster em Sociedade = 6 pts (bloco teto 10)',
      },
    },
  },
  {
    id: 'congresso_academico',
    categoria: 'cientifico',
    titulo: 'Trabalho em Evento Acadêmico Local / Regional (ex.: SIICUSP)',
    descricao: 'Jornadas, simpósios acadêmicos ou SIICUSP como 1º autor. Atenção: certificado deve especificar oral vs. pôster.',
    inputType: 'number',
    unitLabel: 'trabalhos',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Apresentar trabalho em simpósio/jornada acadêmica (1º autor)',
    rules: {
      usp_sp: {
        blockId: 'poster',
        perUnit: 1,
        maxItemPoints: 1,
        note: 'Item 9c: 1º autor pôster evento acadêmico = 1 pt (se oral comprovado: Item 8i = 2 pts)',
      },
      usp_rp: {
        blockId: 'cientifico',
        perUnit: 0.1,
        maxItemPoints: 0.6,
        note: 'Item 3: Pôster regional 1º/2º autor = 0,1 pt (oral = 0,5 pt)',
      },
      unicamp: {
        blockId: 'congresso',
        perUnit: 2,
        maxItemPoints: 10,
        note: 'Item 5b: Congresso acadêmico local/regional (oral ou pôster) = 2 pts',
      },
    },
  },

  // 3. ENSINO, LIGAS & EVENTOS
  {
    id: 'monitoria_oficial',
    categoria: 'ensino_ligas',
    titulo: 'Monitoria Acadêmica Oficial / PAD (em semestres)',
    descricao: 'Certificado institucional com período e carga horária (USP-SP: 64h/128h/192h; USP-RP exige bolsa por ≥ 1 ano).',
    inputType: 'number',
    unitLabel: 'semestres',
    step: 1,
    maxInput: 6,
    actionable: true,
    effortHint: 'medio',
    roiStep: 2,
    roiActionLabel: 'Fazer 2 semestres de monitoria oficial (c/ bolsa se possível)',
    rules: {
      usp_sp: {
        blockId: 'monitoria',
        perUnit: 1,
        maxItemPoints: 3,
        tiers: [
          { minUnits: 3, points: 3 },
          { minUnits: 2, points: 2 },
          { minUnits: 1, points: 1 },
        ],
        note: 'Item 4: >2 sem (≥192h)=3; 2 sem (≥128h)=2; 1 sem (≥64h)=1',
      },
      usp_rp: {
        blockId: 'ensino',
        perUnit: 0.5,
        maxItemPoints: 1.0,
        tiers: [
          { minUnits: 4, points: 1.0 },
          { minUnits: 2, points: 0.5 },
        ],
        note: 'Item 4: Monitoria COM bolsa ≥1 ano (2 sem) = 0,5 pt/ano (teto 1,0)',
      },
      unicamp: {
        blockId: 'monitoria',
        perUnit: 2,
        maxItemPoints: 5,
        tiers: [
          { minUnits: 3, points: 5 },
          { minUnits: 1, points: 2 },
        ],
        note: 'Item 8: > 2 sem = 5 pts; até 2 sem = 2 pts',
      },
    },
  },
  {
    id: 'liga_diretoria',
    categoria: 'ensino_ligas',
    titulo: 'Liga Acadêmica — Diretoria (≥ 1 ano / 2 semestres)',
    descricao: 'Certificado timbrado pelo coordenador da liga. Nota: USP-SP 2027 retirou ligas do Item 10 (agora é extensão).',
    inputType: 'boolean',
    maxInput: 1,
    actionable: true,
    effortHint: 'medio',
    roiActionLabel: 'Completar 1 ano de diretoria em liga acadêmica',
    rules: {
      usp_rp: { blockId: 'assistencial', perUnit: 0.5, maxItemPoints: 0.5, note: 'Item 2: 0,5 pt por ano de liga (sem bônus por diretoria; máx 1,0)' },
      unicamp: { blockId: 'liga', perUnit: 5, maxItemPoints: 5, note: 'Item 6a: Diretoria de liga = 5 pts (teto 5)' },
    },
  },
  {
    id: 'liga_membro',
    categoria: 'ensino_ligas',
    titulo: 'Liga Acadêmica — Anos adicionais como Membro / Ligante',
    descricao: 'Anos como ligante (ou 2º ano de liga para fechar o teto 1,0 pt na USP-RP). Relatório de atividades se houver assistência.',
    inputType: 'number',
    unitLabel: 'anos',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Completar +1 ano em liga acadêmica (fecha teto USP-RP)',
    rules: {
      usp_rp: { blockId: 'assistencial', perUnit: 0.5, maxItemPoints: 1.0, note: 'Item 2: 0,5 pt/ano de liga (teto conjunto liga = 1,0)' },
      unicamp: { blockId: 'liga', perUnit: 2, maxItemPoints: 4, note: 'Item 6b: Membro = 2 pts (bloco teto 5)' },
    },
  },
  {
    id: 'org_evento',
    categoria: 'ensino_ligas',
    titulo: 'Organização de Eventos Científicos (Ligas / DA / Extensão)',
    descricao: 'Comissão organizadora de jornadas, aulas abertas ou simpósios acadêmicos (ex.: LAPQ, Simpósio Pontes).',
    inputType: 'number',
    unitLabel: 'eventos',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Organizar +1 evento científico acadêmico',
    rules: {
      usp_sp: { blockId: 'org_eventos', perUnit: 2, maxItemPoints: 4, note: 'Item 7b: 2 pts/evento acadêmico (máx 2 atividades = 4 pts)' },
      usp_rp: { blockId: 'ensino', perUnit: 0.3, maxItemPoints: 0.6, note: 'Item 4: 0,3 pt/evento científico (teto 0,6)' },
    },
  },
  {
    id: 'org_evento_sociedade',
    categoria: 'ensino_ligas',
    titulo: 'Organização de Congresso de Sociedade Médica (Estadual / Nac.)',
    descricao: 'Comissão organizadora de congresso promovido por entidade profissional de classe (USP-SP Item 7a).',
    inputType: 'number',
    unitLabel: 'eventos',
    step: 1,
    maxInput: 2,
    actionable: true,
    effortHint: 'alto',
    roiStep: 1,
    roiActionLabel: 'Participar da comissão organizadora de congresso de sociedade',
    rules: {
      usp_sp: { blockId: 'org_eventos', perUnit: 4, maxItemPoints: 4, note: 'Item 7a: 4 pts (máx 1 atividade; bloco teto 6)' },
      usp_rp: { blockId: 'ensino', perUnit: 0.3, maxItemPoints: 0.6, note: 'Item 4: 0,3 pt/evento (teto 0,6)' },
    },
  },

  // 4. EXTENSÃO, ESTÁGIOS & CURSOS
  {
    id: 'extensao_voluntariado',
    categoria: 'assistencial_cursos',
    titulo: 'Extensão Universitária Acadêmica / Voluntariado Social (horas)',
    descricao: 'Projetos de extensão não curriculares e voluntariado social (exceto ligas). USP-SP exige chancela da CCEx/Diretoria.',
    inputType: 'number',
    unitLabel: 'horas',
    step: 24,
    maxInput: 240,
    actionable: true,
    effortHint: 'medio',
    roiStep: 48,
    roiActionLabel: 'Acumular +48h em extensão/voluntariado oficial',
    rules: {
      usp_sp: {
        blockId: 'extensao',
        perUnit: 0.05,
        maxItemPoints: 5,
        tiers: [
          { minUnits: 96, points: 5 },
          { minUnits: 48, points: 2.5 },
        ],
        note: 'Item 10 (2027): Extensão acadêmica (sem ligas) c/ aval CCEx/Diretoria — até 5 pts',
      },
      usp_rp: {
        blockId: 'assistencial',
        perUnit: 0.004,
        maxItemPoints: 1.0,
        tiers: [
          { minUnits: 240, points: 1.0 },
          { minUnits: 120, points: 0.5 },
        ],
        note: 'Item 2: Voluntariado social 0,5 pt por bloco de 120h (teto 1,0)',
      },
      unicamp: {
        blockId: 'extensao',
        perUnit: 0.05,
        maxItemPoints: 5,
        tiers: [
          { minUnits: 97, points: 5 },
          { minUnits: 48, points: 2 },
        ],
        note: 'Item 9: Voluntariado social > 96h = 5 pts; 48–96h = 2 pts',
      },
    },
  },
  {
    id: 'cursos_suporte_vida',
    categoria: 'assistencial_cursos',
    titulo: 'Cursos de Suporte de Vida Atualizados (ACLS / ATLS / PALS / BLS)',
    descricao: 'Certificação dentro da validade na inscrição. Pontua na USP-SP e UNICAMP (não tabelado na USP-RP).',
    inputType: 'number',
    unitLabel: 'cursos',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Fazer 1 curso de suporte de vida (ACLS/BLS/PALS)',
    rules: {
      usp_sp: { blockId: 'suporte_vida', perUnit: 2, maxItemPoints: 4, note: 'Item 12: 2 pts/curso atualizado (máx 2 = 4 pts)' },
      unicamp: { blockId: 'aprimoramento', perUnit: 2, maxItemPoints: 5, note: 'Item 7b: 2 pts/curso suporte de vida (bloco teto 5)' },
    },
  },
  {
    id: 'cursos_aprimoramento_12h',
    categoria: 'assistencial_cursos',
    titulo: 'Cursos de ECG / Ventilação Mecânica / USG Beira-Leito (> 12h)',
    descricao: 'Cursos concluídos na área da saúde com > 12h (não vale cursinho preparatório para residência).',
    inputType: 'number',
    unitLabel: 'cursos',
    step: 1,
    maxInput: 5,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Concluir 1 curso certificado > 12h (ECG/VM/USG)',
    rules: {
      unicamp: { blockId: 'aprimoramento', perUnit: 1, maxItemPoints: 5, note: 'Item 7a: 1 pt/curso > 12h (bloco teto 5)' },
    },
  },
  {
    id: 'estagio_extracurricular',
    categoria: 'assistencial_cursos',
    titulo: 'Plantão / Estágio Voluntário Extracurricular (blocos de 120h)',
    descricao: 'Fora da grade obrigatória do internato com declaração de carga horária. Pontua apenas na USP-RP.',
    inputType: 'number',
    unitLabel: 'blocos (120h)',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'medio',
    roiStep: 1,
    roiActionLabel: 'Cumprir 1 bloco de 120h de plantão voluntário extracurricular',
    rules: {
      usp_rp: { blockId: 'assistencial', perUnit: 0.5, maxItemPoints: 1.0, note: 'Item 2: 0,5 pt por 120h de plantão voluntário (teto 1,0)' },
    },
  },

  // 5. REPRESENTAÇÃO, ESPORTE & PROVAS
  {
    id: 'rep_colegiado',
    categoria: 'representacao',
    titulo: 'Representação Discente em Colegiados Institucionais (anos)',
    descricao: 'Congregação, Conselhos Departamentais, CCG ou Comissões de Avaliação/Reforma Curricular (assinado pela faculdade).',
    inputType: 'number',
    unitLabel: 'anos',
    step: 1,
    maxInput: 2,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Assumir 1 gestão (1 ano) como representante discente em colegiado',
    rules: {
      usp_sp: {
        blockId: 'rep_estudantil',
        perUnit: 1,
        maxItemPoints: 3,
        tiers: [
          { minUnits: 2, points: 3 },
          { minUnits: 1, points: 1 },
        ],
        note: 'Item 13: ≥ 2 anos = 3 pts; ≥ 1 ano = 1 pt (teto bloco 3)',
      },
      usp_rp: { blockId: 'estudantil', perUnit: 0.5, maxItemPoints: 1.0, note: 'Item 5: 0,5 pt/ano em colegiado oficial (teto 1,0)' },
      unicamp: {
        blockId: 'rep_colegiado',
        perUnit: 5,
        maxItemPoints: 5,
        tiers: [{ minUnits: 1, points: 5 }],
        note: 'Item 10: Colegiado institucional (mín. 1 sem) = 5 pts',
      },
    },
  },
  {
    id: 'rep_ca_atletica',
    categoria: 'representacao',
    titulo: 'Diretoria de Centro Acadêmico (CARL/DA) ou Atlética (gestões/anos)',
    descricao: 'Gestão mínima de 1 ano (2 semestres) comprovada por certificado institucional contendo período e cargo.',
    inputType: 'number',
    unitLabel: 'anos',
    step: 1,
    maxInput: 3,
    actionable: true,
    effortHint: 'medio',
    roiStep: 1,
    roiActionLabel: 'Cumprir 1 gestão de CA ou Atlética',
    rules: {
      usp_sp: {
        blockId: 'rep_estudantil',
        perUnit: 1,
        maxItemPoints: 3,
        tiers: [
          { minUnits: 2, points: 3 },
          { minUnits: 1, points: 1 },
        ],
        note: 'Item 13: ≥ 2 anos = 3 pts; ≥ 1 ano = 1 pt (compartilha teto 3)',
      },
      usp_rp: { blockId: 'estudantil', perUnit: 0.5, maxItemPoints: 1.0, note: 'Item 5: 0,5 pt/ano em CA/Atlética (teto 1,0)' },
      unicamp: { blockId: 'rep_discente', perUnit: 2, maxItemPoints: 4, note: 'Item 11: CA = 2 pts / Atlética = 2 pts (bloco teto 5)' },
    },
  },
  {
    id: 'esporte_universitario',
    categoria: 'representacao',
    titulo: 'Equipe Esportiva Universitária Oficial (ex.: Natação, em anos)',
    descricao: 'Participação regular comprovada pela instituição/atlética com período e carga horária. Na USP-SP entra no Item 13!',
    inputType: 'number',
    unitLabel: 'anos',
    step: 0.5,
    maxInput: 4,
    actionable: true,
    effortHint: 'medio',
    roiStep: 0.5,
    roiActionLabel: 'Completar 2 anos de equipe esportiva universitária',
    rules: {
      usp_sp: {
        blockId: 'rep_estudantil',
        perUnit: 1,
        maxItemPoints: 3,
        tiers: [
          { minUnits: 2, points: 3 },
          { minUnits: 1, points: 1 },
        ],
        note: 'Item 13: Equipe esportiva ≥ 2 anos = 3 pts; ≥ 1 ano = 1 pt',
      },
      unicamp: {
        blockId: 'rep_discente',
        perUnit: 1,
        maxItemPoints: 1,
        tiers: [{ minUnits: 1, points: 1 }],
        note: 'Item 11c: Equipe esportiva (≥ 2 sem) = 1 pt',
      },
    },
  },
  {
    id: 'teste_progresso',
    categoria: 'representacao',
    titulo: 'Provas Suprainstitucionais (Teste de Progresso / Habilidades / CRM)',
    descricao: 'Participação comprovada nas edições anuais do Teste de Progresso (ABEM/Núcleo). Pontua em Ensino na USP-RP.',
    inputType: 'number',
    unitLabel: 'provas',
    step: 1,
    maxInput: 4,
    actionable: true,
    effortHint: 'baixo',
    roiStep: 1,
    roiActionLabel: 'Fazer +1 edição do Teste de Progresso (ABEM/Núcleo)',
    rules: {
      usp_rp: { blockId: 'ensino', perUnit: 0.5, maxItemPoints: 1.0, note: 'Item 4 (Ensino): 0,5 pt/prova não obrigatória (teto 1,0)' },
    },
  },
];

/**
 * Migração automática de chaves antigas da v2 para as chaves auditadas 2027.
 */
export const CURRICULUM_ID_MIGRATION_MAP: Record<string, string> = {
  inst_docentes_cr: 'inst_sus_rede',
};


/**
 * Mapeamento de migração automática dos IDs legados (`curriculoDoneIds` da v1)
 * para o catálogo canônico unificado (preserva progresso salvo no localStorage).
 */
export const LEGACY_CURRICULO_TO_UNIFIED_MAP: Record<string, Array<{ canonicalId: string; value: number }>> = {
  'curr-inst-fmrp': [
    { canonicalId: 'inst_pos_capes', value: 1 },
    { canonicalId: 'inst_hu_proprio', value: 1 },
    { canonicalId: 'inst_sus_rede', value: 1 },
  ],
  'curr-ic-2anos': [{ canonicalId: 'ic_com_bolsa', value: 2 }],
  'curr-2-artigos': [{ canonicalId: 'artigo_pubmed', value: 2 }],
  'curr-liga': [{ canonicalId: 'liga_diretoria', value: 1 }],
  'curr-natacao': [{ canonicalId: 'esporte_universitario', value: 1.5 }],
  'curr-monitoria': [{ canonicalId: 'monitoria_oficial', value: 2 }],
  'curr-congresso': [{ canonicalId: 'congresso_oral', value: 1 }],
  'curr-org-evento': [{ canonicalId: 'org_evento', value: 1 }],
  'curr-cursos-suporte': [{ canonicalId: 'cursos_suporte_vida', value: 1 }],
  'curr-voluntariado-plantao': [{ canonicalId: 'extensao_voluntariado', value: 100 }],
  'curr-rep-estudantil': [
    { canonicalId: 'rep_colegiado', value: 1 },
    { canonicalId: 'teste_progresso', value: 2 },
  ],
};

