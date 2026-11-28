"""Configuração canônica dos rodízios, modos de dia, Marchas e férias do 6º Ano."""
from __future__ import annotations

from datetime import datetime

from .timezones import DEFAULT_TZ

# Áreas reconhecidas pelo banco de dados do MedQuest
AREAS_MEDQUEST = [
    "Geral",
    "Preventiva",
    "Ginecologia e Obstetrícia",
    "Cirurgia",
    "Medicina Intensiva",
    "Clínica Médica",
    "Pediatria",
    "Especialidades",
]

DAY_MODES = (
    "folga",
    "meio_periodo",
    "integral",
    "plantao_12h_dia",
    "entrada_noturno",
    "plantao_24h",
    "pos_plantao",
)

DAY_MODE_BASE_GOALS: dict[str, int] = {
    "folga": 55,
    "meio_periodo": 40,
    "integral": 25,
    "plantao_12h_dia": 10,
    "entrada_noturno": 10,
    "plantao_24h": 0,
    "pos_plantao": 0,
}

# Ordem de desempate quando duas metas empatam (rótulo exibido): primeiro da lista vence.
DAY_MODE_LABEL_PRIORITY = (
    "plantao_24h",
    "pos_plantao",
    "entrada_noturno",
    "plantao_12h_dia",
    "integral",
    "meio_periodo",
    "folga",
)

DAY_MODE_META: dict[str, dict[str, str]] = {
    "folga": {
        "label": "Folga",
        "guidance": "Melhor janela para blocos 70/30 e revisão profunda.",
    },
    "meio_periodo": {
        "label": "Meio período",
        "guidance": "1–2 blocos focados de questões.",
    },
    "integral": {
        "label": "Integral",
        "guidance": "Tiro curto de questões à noite.",
    },
    "plantao_12h_dia": {
        "label": "Plantão 12h",
        "guidance": "Só manutenção leve.",
    },
    "entrada_noturno": {
        "label": "Entra no noturno",
        "guidance": "Cochilo profilático antes; manutenção leve.",
    },
    "plantao_24h": {
        "label": "Plantão 24h",
        "guidance": "Sem meta. Revisões opcionais.",
    },
    "pos_plantao": {
        "label": "Pós-plantão",
        "guidance": "Descanso. Meta zero; revisões opcionais.",
    },
}

SHIFT_LABELS: dict[str, str] = {
    "plantao_12h_dia": "Plantão 12h diurno",
    "plantao_noturno": "Plantão noturno",
    "plantao_24h": "Plantão 24h",
}

MARCHA_FACTORS: dict[str, float] = {
    "4_sprint": 1.5,
    "3_normal": 1.0,
    "2_pesada": 0.72,
    "1_sobrevivencia": 0.4,
}

MARCHA_LABELS: dict[str, str] = {
    "4_sprint": "Sprint",
    "3_normal": "Normal",
    "2_pesada": "Pesada",
    "1_sobrevivencia": "Sobrevivência",
}

SHIFT_WEIGHT_FOR_MARCHA: dict[str, int] = {
    "plantao_12h_dia": 1,
    "plantao_noturno": 1,
    "plantao_24h": 2,
}

DEFAULT_WEEK_PATTERN: dict[str, str] = {
    "seg": "integral",
    "ter": "integral",
    "qua": "integral",
    "qui": "integral",
    "sex": "integral",
    "sab": "folga",
    "dom": "folga",
}

FERIAS_WEEKS: list[dict[str, str]] = [
    {"id": "sem1", "start": "2026-11-30", "end": "2026-12-06"},
    {"id": "sem2", "start": "2026-12-07", "end": "2026-12-13"},
    {"id": "sem3", "start": "2026-12-14", "end": "2026-12-20"},
    {"id": "sem4", "start": "2026-12-21", "end": "2026-12-27"},
    {"id": "sem5", "start": "2026-12-28", "end": "2027-01-03"},
    {"id": "sem6", "start": "2027-01-04", "end": "2027-01-10"},
    {"id": "sem7", "start": "2027-01-11", "end": "2027-01-17"},
    {"id": "sem8", "start": "2027-01-18", "end": "2027-01-24"},
]

# Configuração padrão — Plano Mestre 6º Ano FMRP-USP (2026/2027)
# IDs canônicos sincronizados com o Novo-PEP para feed, Logbook e deep links.
RODIZIOS_TURMA_J = [
    {
        "id": "ferias",
        "start": "2026-11-30",
        "end": "2027-01-24",
        "area": "Geral",
        "label": "Férias (Pré-Temporada)",
        "ancora70": "Cirurgia + Anestesio/CTI + Lacunas Obstetrícia + Clínica Crítica (Medway + MedQuest, ~2h/dia)",
        "trilha30": "Esteira Contínua v3.1 (~55–70 min/dia Seg–Sex; ~3h/dia total, folgas 24–25/12, 31/12–01/01 e 11–17/01)",
        "ancora_areas": ["Cirurgia", "Medicina Intensiva", "Ginecologia e Obstetrícia", "Clínica Médica"],
        "procedimentos_alvo": [
            "1ª passada E1 (19/20 + baseline), E3-Porta (6/7) e E4 (6/7) até 24/01",
            "≥ 6 queixas E1 dominadas na Esteira v3.1 + ≥ 25/31 dias úteis no Bloco 1",
            "Blocos visuais obrigatórios (ECG + RX nas queixas #1, #4, #5 e #17)",
            "Revisão de 15 min do LOG + Baseline Caso B em 24/01/2027 + IC/editais R1",
        ],
        "micro_habito": "Anamnese guiada por 3 hipóteses (3H ≤ 60s) + apresentação oral ≤ 90s",
    },
    {
        "id": "cirurgia",
        "start": "2027-01-25",
        "end": "2027-02-21",
        "area": "Cirurgia",
        "label": "Cirurgia Geral",
        "ancora70": "Abdome agudo, Trauma/ATLS, Pré/Pós-operatório, Hérnias, Vias biliares e Onco-cirurgia",
        "trilha30": "Preventiva Bloco 1 (SUS, Atenção Primária, Vigilância e Indicadores)",
        "ancora_areas": ["Cirurgia"],
        "procedimentos_alvo": [
            "Anestesia local + Sutura (Regra 3x)",
            "Drenagem abscesso / CE superficial",
            "Curativo complexo / retirada de dreno",
            "SVD (M/F) e SNG/SNE",
        ],
        "micro_habito": "Exame de Abdome Agudo guiado por hipóteses (LR+) + Passagem SBAR pós-op",
    },
    {
        "id": "anestesio_cti",
        "start": "2027-02-22",
        "end": "2027-03-21",
        "area": "Medicina Intensiva",
        "label": "Anestesio / CTI",
        "ancora70": "Avaliação pré-anestésica, Via Aérea/IOT, Choque/Sepse/DVA, VM + Clínica Crítica (Cardio/Pneumo/Nefro/Gaso)",
        "trilha30": "Preventiva Bloco 2 (Estudos Epidemiológicos, Bioestatística e Testes Diagnósticos)",
        "ancora_areas": ["Medicina Intensiva", "Clínica Médica"],
        "procedimentos_alvo": [
            "Ventilação BVM (C-E)",
            "Laringoscopia / IOT",
            "Punção para Gasometria Arterial",
        ],
        "micro_habito": "ABCDE nos primeiros 5 min + Checklist das 7 Travas A-R-G-I-V-P-O no CTI",
    },
    {
        "id": "go",
        "start": "2027-03-22",
        "end": "2027-05-02",
        "area": "Ginecologia e Obstetrícia",
        "label": "GO (6 sem)",
        "ancora70": "Obstetrícia de Alto Risco (DHEG/HELLP, Hemorragias, Partograma/CTG) + Gineco Endócrina, IST/DIP e Onco",
        "trilha30": "Clínica Médica Bloco 1 (Endocrinologia: DM/Tireoide + Reumatologia)",
        "ancora_areas": ["Ginecologia e Obstetrícia"],
        "procedimentos_alvo": [
            "Exame especular + coleta CCO",
            "Toque obstétrico (dilatação/apagamento/plano)",
            "Parto normal assistido / sutura perineal",
        ],
        "micro_habito": "Anamnese acolhedora Calgary-Cambridge (ICE) + 4 Manobras de Leopold + SNAPPS",
    },
    {
        "id": "oftalmo_orl_ccp",
        "start": "2027-05-03",
        "end": "2027-05-16",
        "area": "Especialidades",
        "label": "Oftalmo / ORL / CCP",
        "ancora70": "Olho vermelho, Glaucoma, Otites, Vertigem (HINTS), Epistaxe/IVAS + Neurologia (AVC, Cefaleias, Epilepsia)",
        "trilha30": "Pediatria Bloco 1 (Neonatologia: Reanimação, Icterícia, Sepse e Triagem Neonatal)",
        "ancora_areas": ["Especialidades", "Clínica Médica"],
        "procedimentos_alvo": [
            "Otoscopia limpa + remoção de cerume/CE",
            "Avaliação de olho vermelho com Fluoresceína",
            "Tamponamento nasal anterior",
        ],
        "micro_habito": "Triagem neurológica rápida (HINTS/Pares Cranianos) + Otoscopia técnica",
    },
    {
        "id": "mfc",
        "start": "2027-05-17",
        "end": "2027-06-13",
        "area": "Preventiva",
        "label": "MFC / Preventiva",
        "ancora70": "Preventiva Completa + APS + Clínica Médica Ambulatorial (HAS, Dislipidemia, Asma/DPOC, Rastreamentos)",
        "trilha30": "Pediatria Bloco 2 (Puericultura, Aleitamento, DNPM, Vacinação e Crescimento)",
        "ancora_areas": ["Preventiva", "Clínica Médica"],
        "procedimentos_alvo": [
            "Consultas centradas na pessoa (ICE + Teach-Back)",
            "Conciliação medicamentosa e rastreamentos",
            "Fechamento do Dossiê Curricular R1 até 30/06/2027",
        ],
        "micro_habito": "Explicação compartilhada (Ask-Tell-Ask + Teach-Back) e conciliação medicamentosa",
    },
    {
        "id": "cm",
        "start": "2027-06-14",
        "end": "2027-07-11",
        "area": "Clínica Médica",
        "label": "Clínica Médica",
        "ancora70": "Clínica Médica Pesada: Infectologia, Gastroenterologia/Hepatologia e Hematologia",
        "trilha30": "Pediatria Bloco 3 (Emergências Pediátricas, BVA, PAC, GECA/Desidratação e ITU)",
        "ancora_areas": ["Clínica Médica"],
        "procedimentos_alvo": [
            "Paracentese diagnóstica / alívio (supervisionada)",
            "Toracocentese (supervisionada)",
            "Punção Lombar (supervisionada)",
        ],
        "micro_habito": "Apresentação de visita pelo Pyramid Principle (≤ 90s) + 7 Travas na prescrição",
    },
    {
        "id": "ped",
        "start": "2027-07-12",
        "end": "2027-08-08",
        "area": "Pediatria",
        "label": "Pediatria",
        "ancora70": "Consolidação Total de Pediatria (Neonatologia, Puericultura, Infecto-Ped e Urgências)",
        "trilha30": "Auditoria e Fechamento de Lacunas (<80% de acerto nas 5 grandes áreas)",
        "ancora_areas": ["Pediatria"],
        "procedimentos_alvo": [
            "Otoscopia pediátrica com contenção adequada",
            "Passos iniciais + VPP neonatal em sala de parto",
        ],
        "micro_habito": "Coreografia de Exame Físico Pediátrico (Ordem Anti-Choro + Triângulo de Avaliação)",
    },
    {
        "id": "emergencia_trauma",
        "start": "2027-08-09",
        "end": "2027-10-03",
        "area": "Cirurgia",
        "label": "Emergência & Trauma",
        "ancora70": "Até 31/08: Fechar 100% do 1º ciclo | A partir de 01/09: Provas antigas (USP-SP, USP-RP, UNICAMP) + revisão de lacunas",
        "trilha30": "Esteira v3.1 (E4 Sala Vermelha + Regulação CROSS) + consolidação do Logbook 3x",
        "ancora_areas": ["Cirurgia", "Clínica Médica"],
        "procedimentos_alvo": [
            "Cardioversão elétrica / Desfibrilação (manuseio prático)",
            "Priorização de sala vermelha + SBAR sob pressão",
        ],
        "micro_habito": "Liderança em Sala Vermelha (ABCDE + Comunicação em Alça Fechada + SBAR)",
    },
    {
        "id": "sprint_r1",
        "start": "2027-10-04",
        "end": "2027-11-30",
        "area": "Geral",
        "label": "Reta Final 6º Ano & Consolidação",
        "ancora70": "Provas antigas cronometradas (USP-SP, USP-RP, UNICAMP) como diagnóstico de base pré-2028 + fechamento de lacunas (<80%)",
        "trilha30": "Transição para plantões 2028: Checklist 'Posso Assumir Essa Escala?' (§8 CRM 2028) + revisão de prescrição e emergências",
        "ancora_areas": [a for a in AREAS_MEDQUEST if a != "Geral"],
        "procedimentos_alvo": [
            "Revisão final das 7 Travas de prescrição e altas defensáveis (E3)",
            "Domínio prático dos cenários críticos de porta e sala vermelha (E4)",
            "Fechamento de pendências do internato e formatura FMRP-USP (nov/2027)",
        ],
        "micro_habito": "Conduta completa e prescrição segura com autonomia para assumir plantões em 2028",
    },
]


def get_area_prioritaria_atual(today_iso: str | None = None):
    hoje = today_iso or datetime.now(DEFAULT_TZ).date().isoformat()
    for bloco in RODIZIOS_TURMA_J:
        if bloco["start"] <= hoje <= bloco["end"]:
            return bloco["area"]
    return None
