"""Catálogo pedagógico, ponderação histórica USP e preparação de tópicos do Planner."""
import json
import math
import os
from functools import lru_cache

USP_WEIGHTS = {
    "Clínica Médica": 0.30,
    "Cirurgia": 0.20,
    "Pediatria": 0.15,
    "Ginecologia e Obstetrícia": 0.15,
    "Preventiva": 0.20
}

DEFAULT_PRACTICE_HOURS_PER_SUBTEMA = 2.0
INTERNATO_ESSENTIAL_BONUS = 35.0

# Ciclo contínuo ponderado de 9 posições para o modo Geral (Misturado):
# 2x Clínica, 2x Cirurgia, 2x GO, 2x Pediatria, 1x Preventiva.
# Mantém distância mínima de 4-5 slots entre repetições da mesma área,
# evita Clínica/Cirurgia dominando o topo toda semana e espalha Preventiva
# ao longo do ano em vez de concentrá-la ou sumir por 4+ semanas.
BALANCED_ROTATION_CYCLE = (
    "Clínica Médica",
    "Pediatria",
    "Cirurgia",
    "Ginecologia e Obstetrícia",
    "Preventiva",
    "Clínica Médica",
    "Cirurgia",
    "Ginecologia e Obstetrícia",
    "Pediatria",
)

# Curadoria de temas essenciais do dia a dia do internato (PS, Enfermaria, UBS,
# Sala de Parto e Pediatria prática) usando exatamente os nomes canônicos do catálogo.
INTERNATO_ESSENTIALS = frozenset({
    # Clínica Médica (PS, Enfermaria e UBS)
    "Asma e Doença Pulmonar Obstrutiva Crônica (DPOC)",
    "Cefaleias Primárias (Enxaqueca, Tensional) e Secundárias de Alarme",
    "Celulite, Erisipela, Osteomielite e Infecções de Partes Moles",
    "Cirrose Hepática, Hipertensão Portal e Insuficiência Hepática",
    "Diabetes Mellitus: Metas Glicêmicas, Complicações e Tratamento",
    "Diagnóstico Diferencial das Anemias e Hemoglobinopatias",
    "Distúrbios Eletrolíticos (Sódio, Potássio) e Equilíbrio Ácido-Base",
    "Hipertensão Arterial Sistêmica e Crises Hipertensivas",
    "Hipotireoidismo, Hipertireoidismo e Nódulos Tireoidianos",
    "Infecções Sexualmente Transmissíveis (ISTs) no Adulto",
    "Injúria Renal Aguda (IRA) e Doença Renal Crônica (DRC)",
    "Insuficiência Cardíaca: Diagnóstico, Estadiamento e Terapia Farmacológica",
    "Meningites, Encefalites e Infecções do SNC",
    "Pneumonia Adquirida na Comunidade (PAC) e Síndromes Respiratórias Agudas",
    "Psiquiatria: Transtornos do Humor, Ansiedade e Psicoses",
    "Sepse no Adulto, Choque Séptico e Ressuscitação Hemodinâmica",
    "Síndromes Coronarianas Agudas (Com e Sem Supra de ST)",
    "Síndromes Febris Agudas e Arboviroses (Dengue, Chikungunya, Febre Amarela)",
    "Taquiarritmias, Bradiarritmias, Síncope e Suporte Avançado (ACLS)",
    "Transtornos por Uso de Substâncias (Álcool, Tabaco e Drogas de Abuso)",
    "Tromboembolismo Pulmonar (TEP) e Hipertensão Pulmonar",
    "Ventilação Mecânica, SARA e Insuficiência Respiratória Aguda",
    # Cirurgia (PS Cirúrgico, Trauma e Enfermaria)
    "Abdome Agudo Inflamatório (Apendicite e Diverticulite Aguda)",
    "Abdome Agudo Obstrutivo (Bridas, Neoplasias e Volvo)",
    "Atendimento Inicial ao Politraumatizado (Protocolo xABCDE)",
    "Atendimento ao Paciente Queimado e Reposição Volêmica",
    "Avaliação Pré-Operatória e Estratificação de Risco Cirúrgico",
    "Doença do Refluxo Gastroesofágico (DRGE) e Úlcera Péptica",
    "Hemorragia Digestiva Alta e Baixa na Emergência Cirúrgica",
    "Hiperplasia Prostática Benigna (HPB) e Litíase Urinária",
    "Hérnias da Parede Abdominal (Inguinais, Femorais e Incisionais)",
    "Insuficiência Venosa Crônica e Trombose Venosa Profunda (TVP)",
    "Litíase Biliar, Colecistite, Coledocolitíase e Colangite",
    "Manejo Pós-Operatório e Tratamento de Complicações Cirúrgicas",
    "Pancreatites Aguda e Crônica e Pseudocistos Pancreáticos",
    "Trauma Abdominal Fechado e Penetrante (FAST e Laparotomia)",
    "Trauma Torácico: Pneumotórax, Hemotórax e Tamponamento Cardíaco",
    # Ginecologia e Obstetrícia (Sala de Parto, PS GO e UBS)
    "Amniorrexe Prematura (RPMO) e Corioamnionite",
    "Assistência Clínica ao Trabalho de Parto, Partograma e Distocias",
    "Assistência Pré-Natal de Baixo e Alto Risco",
    "Avaliação da Vitalidade Fetal, Cardiotocografia e Sofrimento Fetal",
    "Diabetes Gestacional e Pré-Gestacional",
    "Doença Inflamatória Pélvica (DIP) e Atendimento à Violência Sexual",
    "Hemorragias da Primeira Metade: Abortamento, Ectópica e Mola",
    "Hemorragias da Segunda Metade: Placenta Prévia e DPP",
    "Infecções Perinatais e Transmissão Vertical (HIV, Sífilis, Hepatites, EGB)",
    "Métodos Contraceptivos: Hormonais, DIU e Cirúrgicos",
    "Puerpério Fisiológico, Patológico e Hemorragia Pós-Parto",
    "Rastreamento Citopatológico e Conduta em Lesões Cervicais (HPV)",
    "Sangramento Uterino Anormal (SUA) e Classificação PALM-COEIN / Miomatose",
    "Síndromes Hipertensivas na Gravidez (Pré-eclâmpsia e Eclâmpsia)",
    "Trabalho de Parto Prematuro e Tocólise",
    "Vulvovaginites e Diagnóstico Diferencial dos Corrimentos Vaginais",
    "Úlceras Genitais e Infecções Sexualmente Transmissíveis na Mulher",
    # Pediatria (PS Pediátrico, Alojamento Conjunto e Puericultura)
    "Afecções de Vias Aéreas Superiores: OMA, Sinusite e Faringoamigdalite",
    "Aleitamento Materno, Alimentação Complementar e Desnutrição Infantil",
    "Alojamento Conjunto e Testes de Triagem Neonatal (Pezinho, Olhinho, Coraçãozinho)",
    "Anemias Carenciais e Distúrbios de Micronutrientes (Ferro, Vitamina D)",
    "Arritmias, Síncope e Parada Cardiorrespiratória Pediátrica (PALS)",
    "Calendário Vacinal do PNI e Imunizações Especiais",
    "Convulsão Febril, Epilepsias e Síndromes Convulsivas na Infância",
    "Diarreia Aguda, Reidratação Oral e Doenças Disabsortivas",
    "Distúrbios Obstrutivos, Asma e Bronquiolite na Infância",
    "Doenças Exantemáticas e Diagnóstico Diferencial dos Exantemas",
    "Infecção do Trato Urinário (ITU) e Refluxo Vesicoureteral na Infância",
    "Neonatologia: Desconforto Respiratório e Doença da Membrana Hialina",
    "Neonatologia: Distúrbios Metabólicos e Hipoglicemia no Recém-Nascido",
    "Neonatologia: Icterícia Neonatal e Doenças Hematológicas",
    "Puericultura: Marcos do Desenvolvimento (DNPM) e Curvas de Crescimento",
    "Reanimação Neonatal e Assistência em Sala de Parto",
    "Sepse Pediátrica, Choque e Ressuscitação Hemodinâmica",
    # Preventiva / MFC (UBS, Vigilância e Ética)
    "Atenção Primária à Saúde e Estratégia Saúde da Família (ESF)",
    "História Natural da Doença e Níveis de Prevenção",
    "Legislação, Diretrizes e Evolução do SUS",
    "Saúde do Trabalhador e Doenças Ocupacionais",
    "Vigilância Epidemiológica: Endemias, Epidemias e Surtos",
    "Vigilância em Saúde e Notificação Compulsória (SINAN)",
    "Ética Médica, Bioética e Prontuários / Documentos",
})


def _resolve_data_path(filename):
    """Resolve o caminho de um arquivo JSON procurando em data/ e scripts/."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate_data = os.path.join(base_dir, "data", filename)
    if os.path.exists(candidate_data):
        return candidate_data
    candidate_scripts = os.path.join(base_dir, "scripts", filename)
    if os.path.exists(candidate_scripts):
        return candidate_scripts
    return candidate_data


from .taxonomy import get_normalized_area  # noqa: F401 - re-export canônico


@lru_cache(maxsize=1)
def _load_catalogs():
    # Carrega o mesmo catálogo pedagógico exibido no frontend.
    planner_data_path = _resolve_data_path("plannerData.json")
    try:
        with open(planner_data_path, "r", encoding="utf-8") as f:
            planner_meta = json.load(f)
    except Exception:
        planner_meta = []

    duration_catalog_path = _resolve_data_path("katomartCourseDurations.json")
    try:
        with open(duration_catalog_path, "r", encoding="utf-8") as f:
            duration_catalog = json.load(f)
    except Exception:
        duration_catalog = {}

    katomart_subtemas = duration_catalog.get("subtemas", {})
    practice_hours_per_subtema = duration_catalog.get("source", {}).get(
        "practice_hours_per_subtema",
        DEFAULT_PRACTICE_HOURS_PER_SUBTEMA,
    )
    return planner_meta, katomart_subtemas, practice_hours_per_subtema


def _build_meta_dict(planner_meta, katomart_subtemas):
    # Cria o catálogo canônico de subtemas para fácil acesso. O banco pode
    # conter classificações históricas, incompletas ou ainda não migradas; ele
    # só deve complementar as estatísticas dos temas, nunca definir o edital.
    meta_dict = {}
    for area_group in planner_meta:
        canonical_area = get_normalized_area(area_group.get("area"))
        for macro in area_group.get("macroThemes", []):
            is_high_yield = macro.get("highYield", False)
            # Fallback pedagógico para subtemas sem correspondência segura no
            # catálogo local de aulas do Katomart.
            fallback_theory_hours = max(1.0, len(macro.get("details", [])) * 0.25)

            for db_subtema in macro.get("dbSubtemas", []):
                course_match = katomart_subtemas.get(db_subtema)
                meta_dict[db_subtema] = {
                    "area": canonical_area,
                    "highYield": is_high_yield,
                    "theory_hours": (
                        course_match.get("theory_hours", fallback_theory_hours)
                        if course_match
                        else fallback_theory_hours
                    ),
                    "theory_source": "curriculum" if course_match else "pedagogical_estimate",
                    "course_module": course_match.get("module") if course_match else None,
                }
    return meta_dict


def _consolidate_row_stats(rows, meta_dict):
    # Consolida as estatísticas do banco apenas para os 170 temas do catálogo.
    # Isso também protege contra a mesma classificação aparecer em mais de uma
    # área durante uma migração de dados.
    row_stats = {
        subtema: {"q_count": 0, "target_q_count": 0, "subtopics": []}
        for subtema in meta_dict
    }
    for row in rows:
        subtema = row["subtema"]
        if subtema not in row_stats:
            continue
        stats = row_stats[subtema]
        try:
            stats["q_count"] += int(row["q_count"] or 0)
        except (TypeError, ValueError):
            pass
        raw_target_q = (
            row.get("target_q_count")
            if isinstance(row, dict)
            else (row["target_q_count"] if "target_q_count" in row.keys() else 0)
        )
        try:
            stats["target_q_count"] += int(raw_target_q or 0)
        except (TypeError, ValueError):
            pass
        topics = row.get("topics") if isinstance(row, dict) else (row["topics"] if "topics" in row.keys() else None)
        if topics:
            stats["subtopics"].extend(topic for topic in str(topics).split(",") if topic)
    return row_stats


def _compute_empirical_incidence(meta_dict, row_stats, use_bank_incidence=False):
    """
    Calcula incidência empírica normalizada dentro de cada grande área a partir
    das questões reais das bancas-alvo selecionadas pelo estudante.

    Quando não há bancas-alvo ou não existem questões dessas bancas no catálogo,
    retorna `({}, False)` preservando integralmente o comportamento legado.
    """
    if not use_bank_incidence:
        return {}, False

    total_target_q = sum(stats.get("target_q_count", 0) for stats in row_stats.values())
    if total_target_q <= 0:
        return {}, False

    by_area = {}
    for subtema, meta in meta_dict.items():
        area = meta["area"]
        by_area.setdefault(area, []).append(
            (subtema, row_stats[subtema].get("target_q_count", 0), bool(meta["highYield"]))
        )

    incidence_map = {}
    for area, items in by_area.items():
        max_area_q = max((item[1] for item in items), default=0)
        if max_area_q <= 0:
            for subtema, tq, is_hy in items:
                incidence_map[subtema] = {
                    "target_q_count": tq,
                    "effective_high_yield": is_hy,
                    "incidence_bonus": 0.0,
                    "incidence_source": "national_catalog",
                }
            continue

        static_hy_count = sum(1 for item in items if item[2])
        cutoff = max(1, static_hy_count) if static_hy_count > 0 else max(1, round(len(items) * 0.5))
        ranked = sorted(items, key=lambda x: (x[1], 1 if x[2] else 0), reverse=True)
        top_subtemas = {item[0] for item in ranked[:cutoff]}
        denom = math.log1p(max_area_q)

        for subtema, tq, _is_hy in items:
            ratio = (math.log1p(tq) / denom) if denom > 0 and tq > 0 else 0.0
            incidence_map[subtema] = {
                "target_q_count": tq,
                "effective_high_yield": subtema in top_subtemas,
                "incidence_bonus": round(ratio * 25.0, 2),
                "incidence_source": "target_banks",
            }

    return incidence_map, True


def _build_topic_item(
    subtema,
    meta,
    stats,
    prog,
    practice_hours_per_subtema,
    adaptive_signals=None,
    completed_subtemas=None,
    incidence_info=None,
):
    norm_area = meta["area"]
    q_count = stats["q_count"] if stats else 0

    prog_dict = dict(prog) if prog else {}
    ans_count = prog_dict.get("ans_count") or 0
    attempts = prog_dict.get("attempts") or 0
    correct_count = prog_dict.get("correct_count") or 0
    acc = (correct_count / attempts) if attempts > 0 else 0

    remaining_q = max(0, q_count - ans_count)

    theory_hours = meta["theory_hours"]
    practice_hours = practice_hours_per_subtema
    total_topic_hours = theory_hours + practice_hours

    use_empirical = bool(incidence_info and incidence_info.get("incidence_source") == "target_banks")
    effective_high_yield = (
        bool(incidence_info["effective_high_yield"])
        if incidence_info is not None
        else bool(meta["highYield"])
    )
    incidence_bonus = float(incidence_info.get("incidence_bonus", 0.0)) if use_empirical else 0.0
    target_q_count = int(incidence_info.get("target_q_count", 0)) if use_empirical else None

    is_internato_essential = subtema in INTERNATO_ESSENTIALS

    # Priority score: High Yield = 100, plus Internato Essential = 55, plus empirical bank incidence, plus area weight
    weight = USP_WEIGHTS.get(norm_area, 0.1)
    priority = 100 if effective_high_yield else 0
    if is_internato_essential:
        priority += INTERNATO_ESSENTIAL_BONUS
    priority += incidence_bonus
    priority += weight * 10

    priority_reasons = []
    if adaptive_signals is not None:
        sig = adaptive_signals.get(subtema)
        if sig:
            reasons = sig.get("reasons", [])
            if reasons:
                # Sinais adaptativos com evidências reais de dificuldade ou revisão pendente
                score = float(sig.get("priority_score", 0.0) or 0.0)
                priority += round(score * 50.0, 2)
                priority_reasons = list(reasons)
    else:
        # Fallback retrocompatível para chamadas sem sinais adaptativos
        if attempts >= 3 and acc < 0.6:
            priority += 50
            priority_reasons.append("low_accuracy")

    # Tier and explanation
    if priority >= 130:
        priority_tier = "Diamante"
    elif priority >= 100:
        priority_tier = "Alta"
    elif priority >= 50:
        priority_tier = "Média"
    else:
        priority_tier = "Normal"

    explanation_parts = []
    if effective_high_yield:
        if use_empirical and target_q_count and target_q_count > 0:
            q_label = "1 questão" if target_q_count == 1 else f"{target_q_count} questões"
            explanation_parts.append(f"tem alta incidência nas suas bancas ({q_label})")
        else:
            explanation_parts.append("é de alto rendimento nas provas")
    if is_internato_essential:
        explanation_parts.append("é tema essencial do dia a dia do internato")
    if "low_accuracy" in priority_reasons:
        explanation_parts.append("houve baixo desempenho recente")
    if "reviews_due" in priority_reasons:
        explanation_parts.append("há revisões vencidas")
    if "memory_at_risk" in priority_reasons:
        explanation_parts.append("há risco de esquecimento")
    if "low_coverage" in priority_reasons:
        explanation_parts.append("você ainda não cobriu este assunto")

    if explanation_parts:
        if len(explanation_parts) > 1:
            exp = ", ".join(explanation_parts[:-1]) + " e " + explanation_parts[-1]
        else:
            exp = explanation_parts[0]
        priority_explanation = f"Recomendado porque {exp}."
    else:
        priority_explanation = "Recomendado para cobrir o edital equilibradamente."

    topic_obj = {
        "area": norm_area,
        "subtema": subtema,
        "subtopics": stats["subtopics"] if stats else [],
        "questions_available": remaining_q,
        "estimated_theory_hours": round(theory_hours, 2),
        "estimated_practice_hours": round(practice_hours, 2),
        "estimated_hours": round(total_topic_hours, 2),
        "theory_source": meta["theory_source"],
        "course_module": meta["course_module"],
        "priority": round(priority, 2),
        "priority_reasons": priority_reasons,
        "priority_tier": priority_tier,
        "priority_explanation": priority_explanation,
        "is_internato_essential": is_internato_essential,
        "completed": bool(completed_subtemas and subtema in completed_subtemas),
        "incidence_source": "target_banks" if use_empirical else "national_catalog",
    }
    if use_empirical:
        topic_obj["target_questions_count"] = target_q_count
    return topic_obj, total_topic_hours


def _prepare_topics(
    meta_dict,
    row_stats,
    user_progress,
    intensive,
    practice_hours_per_subtema,
    adaptive_signals=None,
    completed_subtemas=None,
    incidence_map=None,
):
    # Prepara exatamente os tópicos canônicos, calculando as horas de cada um.
    all_topics = []
    total_required_hours = 0.0
    pending_required_hours = 0.0

    if user_progress is None:
        user_progress = {}

    for subtema, meta in meta_dict.items():
        inc_info = incidence_map.get(subtema) if incidence_map else None
        effective_hy = inc_info["effective_high_yield"] if inc_info is not None else meta["highYield"]
        if intensive and not effective_hy:
            continue

        stats = row_stats[subtema]
        prog = user_progress.get(subtema)
        topic_obj, topic_hours = _build_topic_item(
            subtema,
            meta,
            stats,
            prog,
            practice_hours_per_subtema,
            adaptive_signals,
            completed_subtemas=completed_subtemas,
            incidence_info=inc_info,
        )
        total_required_hours += topic_hours
        if not topic_obj["completed"]:
            pending_required_hours += topic_hours
        all_topics.append(topic_obj)

    # Sort topics by priority (descending)
    all_topics.sort(key=lambda x: x["priority"], reverse=True)
    return all_topics, total_required_hours, pending_required_hours

