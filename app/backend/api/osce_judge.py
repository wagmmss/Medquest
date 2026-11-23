"""Juiz Clínico com IA para avaliação semântica do barema OSCE com trava anti-alucinação."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import gemini_pool
from .osce_evaluation import (
    _NEGATION_PREFIXES,
    _clause_has_negation,
    _extract_clause_prefix,
    _find_term_matches,
    _has_affirmative_mention,
    _normalize_text,
    evaluate_osce_red_flags,
)

logger = logging.getLogger(__name__)

_POSITIVE_VERBS = (
    "indico ", "prescrevo ", "inicio ", "administro ", "solicito ", "faco ", "realizo ",
    "mantenho ", "associo ", "ativo ", "oriento ", "encaminho ", "garanto ", "explico ",
)

# Equivalências semânticas médicas usadas pelo simulador hermético offline (testes)
_CLINICAL_CONCEPT_CLUSTERS: list[set[str]] = [
    {"kussmaul", "padrao respiratorio profundo", "respiracao profunda", "taquipneia", "acidotica"},
    {"halito cetonico", "halito frutado"},
    {"torpor", "rebaixamento", "sensorio", "consciencia"},
    {"cetoacidose", "descompensacao hiperglicemica", "cetose", "acidemia metabolica", "acidose metabolica"},
    {"soro fisiologico", "solucao salina isotonica", "sf 0,9%", "cristaloide isotonico", "solucao fisiologica"},
    {"potassio", "calemia", "ionograma", "eletrolito", "cloreto de potassio", "repor potassio"},
    {"insulina regular", "hormonio insulinico", "terapia hormonal"},
    {"soro glicosado", "solucao glicosada", "sg 5%"},
    {"fechar anion gap", "normalizar o bicarbonato", "normalizar bicarbonato"},
    {"privacidade", "consultorio reservado", "ambiente reservado"},
    {"acompanhante", "familiar", "esposa"},
    {"percepcao", "o que o senhor sabe", "o que ja compreende", "o que tem passado"},
    {"gostaria de saber", "ate que ponto prefere", "explicacoes minuciosas", "detalhes"},
    {"aviso previo", "preparar", "noticia dificil", "infelizmente"},
    {"cancer", "tumor", "neoplasia maligna", "linguagem simples", "sem termos tecnicos"},
    {"acolher", "silencio", "valido sua angustia", "respeitando sua emocao", "compreendo"},
    {"oncologia", "equipe especializada em cancer", "estadiamento", "acompanhamento continuo", "encaminhamento"},
    {"atls", "abcde", "avaliacao primaria sistematizada", "protecao cervical", "via aerea", "colar cervical"},
    {"choque hemorragico", "instabilidade hemodinamica", "sangramento agudo", "choque hipovolemico"},
    {"e-fast", "fast", "ultrassonografico focado", "ultrassonografia beira-leito", "rastreamento cavitario"},
    {"hemoperitonio", "esplenorrenal", "liquido livre", "colecao liquida", "ruptura do baco", "trauma esplenico"},
    {"transfusao macica", "hemotransfusao macica", "hemacias", "plasma", "plaquetas", "1:1:1"},
    {"acido tranexamico", "antifibrinolitico", "transamin"},
    {"laparotomia", "cirurgia abdominal exploradora", "centro operatorio", "centro cirurgico"},
    {"sigilo", "confidencialidade", "nao exige registro policial", "sem boletim", "sem pericia"},
    {"levonorgestrel", "pilula hormonal de emergencia", "progestageno", "anticoncepcao de emergencia"},
    {"profilaxia pos-exposicao", "antirretroviral", "tenofovir", "lamivudina", "dolutegravir", "quatro semanas", "28 dias"},
    {"ceftriaxona", "azitromicina", "metronidazol", "gonorreia", "clamidiose", "tricomoniase", "infeccoes sexualmente transmissiveis"},
    {"hepatite", "imunoglobulina", "imunizacao", "psicologa", "psicologia", "servico social", "assistencia social"},
    {"samsst", "sem supra", "sem elevacao do segmento st", "angina de repouso", "angina instavel"},
    {"infradesnivelamento", "depressao do segmento st", "onda t", "ondas t", "sofrimento miocardico"},
    {"grace", "timi", "escore prognostico", "alto risco isquemico", "biomarcador cardiaco"},
    {"dupla antiagregacao", "antiplaquetaria dupla", "acido acetilsalicilico", "bloqueador do receptor p2y12", "ticagrelor", "clopidogrel", "aspirina"},
    {"enoxaparina", "heparina de baixo peso molecular", "heparina fracionada", "anticoagulacao"},
    {"nitrato", "betabloqueador", "atorvastatina", "estatina de alta potencia", "terapia antianginosa"},
    {"cateterismo", "coronariografia precoce", "estrategia invasiva precoce", "angioplastia", "reperfusao", "hemodinamica", "cardiologia intervencionista"},
    {"primeiro episodio", "chiado no peito", "prematuridade", "prematuro", "contatos domiciliares"},
    {"tiragem", "retracao subcostal", "trabalho respiratorio", "taquipneia", "dessaturacao", "hipoxemia"},
    {"bronquiolite", "infeccao viral aguda das pequenas vias aereas", "virus sincicial", "virus respiratorio"},
    {"oxigenio", "canula nasal", "cateter nasal", "saturacao acima de noventa"},
    {"lavagem nasal", "higiene nasal", "solucao salina isotonica"},
    {"aleitamento", "leite materno", "fracionar mamadas", "pequenas porcoes"},
    {"codigo vermelho", "equipe multidisciplinar", "chamar ajuda", "acessos venosos calibrosos", "dois acessos"},
    {"4 ts", "quatro principais causas", "atonia uterina", "falha de contracao uterina"},
    {"hamilton", "compressao uterina bimanual", "massagem bimanual", "punho vaginal"},
    {"ocitocina", "uterotonico de primeira escolha", "primeira linha"},
    {"misoprostol", "prostaglandina retal", "metilergometrina", "sondagem vesical", "cateterismo de alivio"},
    {"balao de bakri", "tamponamento intrauterino", "b-lynch", "sutura hemostatica", "histerectomia"},
    {"escuta ativa", "perguntas abertas", "sem julgamentos", "atencao plena"},
    {"mccp", "experiencia subjetiva", "sentimentos", "receios", "ideias", "funcao", "expectativas"},
    {"genograma", "rede familiar", "marido", "conjuge acamado", "cuidadora", "sobrecarga", "etilismo", "dependente quimico"},
    {"somatizacao", "sofrimento fisico e legitimo", "exaustao emocional", "sintomas corporais", "sua dor e real"},
    {"prevencao quaternaria", "evitar exames", "evitando solicitar", "desnecessarios"},
    {"atencao domiciliar", "atendimento domiciliar", "grupo de apoio", "retorno", "cuidadores"},
    {"bom dia", "boa tarde", "cumprimento", "cumprimento cordialmente", "cumprimento a paciente", "me chamo", "sou o medico", "ajuda-lo"},
    {"quando comecou", "irradia", "irradiacao", "mandibula", "suor frio", "sudorese", "enjoo", "nausea"},
    {"tabagismo", "habito tabagico", "comorbidades", "pressao alta", "diabetes", "sildenafila", "vasodilatadores"},
    {"monitorizacao", "oximetria", "oximetro", "acessos perifericos", "acesso venoso"},
    {"eletrocardiograma", "tracado eletrocardiografico", "12 derivacoes", "doze derivacoes"},
    {"supradesnivelamento", "elevacao do segmento st", "infarto agudo", "parede anterior"},
    {"desobstruir", "entupimento de uma arteria", "arteria do coracao"},
    {"anti-inflamatorio", "medicacoes anti-inflamatorias", "ibuprofeno", "diclofenaco", "dispepticos", "ulcera"},
    {"abdome em tabua", "rigidez difusa", "blumberg", "descompressao", "jobert", "macicez"},
    {"radiografia", "exame radiografico", "cupulas diafragmaticas", "ortostatico", "torax em pe"},
    {"pneumoperitonio", "gas livre subdiafragmatico", "ar livre", "perfuracao de viscera oca"},
    {"jejum", "sonda nasogastrica", "sonda gastrica", "cristaloide", "solucao balanceada", "hidratacao"},
    {"antibiotico", "antibioticoterapia", "ceftriaxona", "metronidazol", "analgesia", "analgesico"},
    {"cirurgia", "laparotomia", "laparoscopia", "abordagem operatoria", "centro cirurgico"},
    {"consentimento", "explicar", "comunico", "termo", "leito pos-operatorio"},
    {"anafilaxia", "reacao alergica sistemica", "choque anafilatico", "estridor"},
    {"adrenalina", "epinefrina", "intramuscular", "vasto lateral", "coxa"},
    {"mascara", "reservatorio", "pernas elevadas", "elevar pernas"},
    {"20 ml/kg", "vinte mililitros por quilo", "intraosseo", "tibial"},
    {"corticoide", "corticosteroide", "hidrocortisona", "bloqueador histaminico", "anti-histaminico", "adjuvantes"},
    {"reacao bifasica", "retorno tardio", "observacao", "autoinjetor", "caneta"},
    {"decubito lateral", "repouso lateral", "niveis tensionais", "pressao arterial"},
    {"cefaleia", "dor de cabeca intensa", "escotomas", "alteracoes visuais", "epigastralgia", "dor epigastrica", "hiperreflexia", "reflexos exaltados"},
    {"batimentos fetais", "batimentos cardiacos fetais", "altura uterina", "tonus"},
    {"sulfato de magnesio", "sulfatacao", "zuspan", "prevencao de convulsoes"},
    {"hidralazina", "nifedipino", "anti-hipertensivo", "controle pressorico"},
    {"gluconato de calcio", "antidoto de calcio", "reflexo patelar", "diurese", "frequencia respiratoria"},
    {"betametasona", "corticoterapia antenatal", "maturacao pulmonar", "amadurecimento pulmonar"},
    {"terapia intensiva", "cuidados intensivos", "internacao", "riscos materno-fetais"},
    {"hipotensao", "queda pressorica", "instabilidade", "congestao pulmonar", "rebaixamento"},
    {"desfibrilador", "cardioversor", "carrinho de parada", "carro de emergencia", "pas"},
    {"sincronizar", "sincronizacao", "sincronizado", "complexo qrs", "onda r"},
    {"sedacao", "etomidato", "midazolam", "fentanil", "analgesia"},
    {"100 joules", "cem joules", "cardioversao eletrica", "terapia eletrica sincronizada", "afasta"},
    {"sepse", "choque septico", "disfuncao organica grave infecciosa", "hipoperfusao", "marcador de hipoperfusao"},
    {"hemocultura", "amostras microbiologicas", "lactato", "marcador metabolico"},
    {"amplo espectro", "primeira hora", "sessenta minutos"},
    {"30 ml/kg", "trinta mililitros por quilo", "solucao cristaloide balanceada", "ringer lactato"},
    {"noradrenalina", "vasopressor", "droga vasoativa", "pam 65", "pressao arterial media"},
    {"pneumotorax hipertensivo", "quadro compressivo pleural", "choque obstrutivo", "estase jugular", "desvio traqueal"},
    {"toracocentese", "puncao agulhada", "descompressao imediata da cavidade pleural", "puncao", "agulha"},
    {"drenagem de torax", "drenagem subaquatica", "selo d'agua", "tubo pleural", "dreno"},
    {"letargia", "prostracao acentuada", "olhos fundos", "globos oculares encovados", "lagrimas", "boca seca", "mucosas ressecadas", "sinal da prega", "prega cutanea"},
    {"desidratacao grave", "plano c", "perda hidroeletrolitica", "comprometimento hemodinamico"},
    {"100 ml/kg", "cem mililitros por quilo", "fase rapida", "fase inicial rapida"},
    {"aleitamento materno", "leite materno", "amamentacao materna", "alimentacao"},
    {"zinco", "micronutriente zinco", "sulfato de zinco"},
    {"acidente ocupacional", "instrumento oco", "agulha oca", "sangue visivel", "sessenta minutos", "tempo decorrido"},
    {"agua e sabao", "solucao neutra", "nao espremer", "proibindo comprimir", "proibido espremer", "cortar a pele"},
    {"paciente-fonte", "pessoa-fonte", "testes rapidos da pessoa-fonte", "teste rapido da fonte"},
    {"sorologias iniciais", "exames basais", "anticorpos protetores", "anti-hbs"},
    {"pep imediata", "profilaxia antirretroviral de urgencia", "primeiras horas", "sem esperar exame laboratorial"},
    {"imunoglobulina", "ighahb", "soro especifico hiperimune", "reforco vacinal", "reforco imunizante"},
    {"hepatite c", "hepatite viral c", "quimioprofilaxia", "sem profilaxia", "acompanhamento molecular"},
    {"preservativo", "barreiras sexuais", "nao doar sangue", "doacao sanguinea", "reacoes gastricas"},
    {"cat", "comunicacao de acidente de trabalho", "documentacao trabalhista ocupacional"},
    {"notificacao compulsoria", "notificacao epidemiologica", "registro epidemiologico compulsorio", "sinan", "trinta e noventa dias"},
    {"cao de rua", "cao errante", "nao observavel", "condicao do animal", "mordedura profunda"},
    {"vacina de tetano", "antitetanica", "dupla adulto", "imunizacoes previas", "virus rabico"},
    {"exame da mao", "movimento tendineo", "circulacao distal", "tendinea", "sensibilidade"},
    {"acidente grave", "categoria de alto risco", "extremidade palmar profunda", "polpas digitais"},
    {"nao suturar", "sem sutura", "evitando pontos primarios", "ferida aberta"},
    {"vacina antirrabica", "imunizacao antirrabica", "quatro aplicacoes", "deltoide", "dias 0, 3, 7 e 14"},
    {"soro antirrabico", "soro hiperimune", "imunoglobulina antirrabica", "imunoglobulina especifica", "infiltrada diretamente"},
    {"amoxicilina-clavulanato", "amoxicilina associada a clavulanato", "cobertura antimicrobiana"},
    {"sinais de infeccao", "alerta infeccioso", "adesao rigorosa"},
    {"tosse cronica", "4 semanas", "febre de fim de tarde", "febre vespertina", "suores noturnos", "sudorese noturna", "moradores infantis"},
    {"62 kg", "sessenta e dois quilos", "peso corporal", "ausculta respiratoria apical"},
    {"trm-tb", "genexpert", "teste molecular rapido", "cultura microbacteriana", "baciloscopia"},
    {"radiografia de torax", "estudo radiografico toracico", "sorologia anti-hiv", "teste rapido de hiv", "funcao hepatica"},
    {"tuberculose pulmonar", "tuberculose pulmonar ativa transmissivel", "bacilifera"},
    {"esquema ripe", "esquema quadruplo basico", "quatro comprimidos diarios em jejum", "manutencao dupla"},
    {"tdo", "tratamento diretamente observado", "acompanhamento supervisionado diario"},
    {"urina alaranjada", "coloracao alaranjada", "alerta hepatico", "hepatotoxicidade", "ictericia"},
    {"contatos intradomiciliares", "rastreamento clinico", "teste cutaneo", "prova tuberculinica", "iltb"},
    {"afastamento", "repouso laboral", "duas semanas", "ambiente arejado", "ventilado"},
]


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def build_candidate_timeline_log(
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Constrói o registro cronológico exclusivo do candidato (falas, prescrições e ações)."""
    log: list[dict[str, Any]] = []
    seq = 0

    for item in transcript:
        if item.get("sender") != "candidato":
            continue
        raw_msg = str(item.get("message") or "").strip()
        if not raw_msg:
            continue
        elapsed = item.get("elapsed_seconds")
        elapsed_int = int(elapsed) if elapsed is not None else 0
        log.append({
            "seq": seq,
            "elapsed_seconds": elapsed_int,
            "source": "speech",
            "text": raw_msg,
        })
        seq += 1

    allowed_action_types = {
        "vitals",
        "physical_exam",
        "lab_imaging",
        "exam",
        "procedure",
        "cardioversion",
    }
    for act in actions:
        act_type = str(act.get("action_type") or "").strip()
        elapsed = act.get("elapsed_seconds")
        elapsed_int = int(elapsed) if elapsed is not None else 0

        if act_type == "prescription":
            for p in act.get("prescription_items", []):
                p_text = _collapse_spaces(
                    f"{p.get('drug_name', '')} {p.get('dose', '')} "
                    f"{p.get('unit', '')} {p.get('route', '')} {p.get('notes', '')}"
                )
                if p_text:
                    log.append({
                        "seq": seq,
                        "elapsed_seconds": elapsed_int,
                        "source": "prescription",
                        "text": p_text,
                    })
                    seq += 1
        elif act_type in allowed_action_types:
            target_raw = str(act.get("action_target", "") or "").strip()
            target_norm = _normalize_text(target_raw)
            alias = ""
            if act_type in ("lab_imaging", "exam"):
                if "ecg" in target_norm or "eletro" in target_norm:
                    alias = "eletrocardiograma ecg 12 derivacoes"
                elif target_norm in ("rx", "raio_x", "rx_torax", "radiografia"):
                    alias = "radiografia raio-x rx de torax"
                elif "gaso" in target_norm or "eletrolito" in target_norm:
                    alias = "gasometria eletrolitos potassio"
            a_text = _collapse_spaces(
                f"{act_type} {target_raw} {act.get('procedure_type', '')} {act.get('anatomical_site', '')} {alias}"
            )
            if a_text:
                log.append({
                    "seq": seq,
                    "elapsed_seconds": elapsed_int,
                    "source": "action",
                    "text": a_text,
                })
                seq += 1

    log.sort(key=lambda entry: (entry["elapsed_seconds"], entry["seq"]))
    return log


def verify_evidence_quote(
    quote: str,
    candidate_log: list[dict[str, Any]],
) -> tuple[bool, str, int | None, str]:
    """
    Valida se `quote` existe literalmente no log do candidato (após colapso de espaços).
    Retorna (valido, citacao_literal_preservada, elapsed_seconds, source).
    """
    clean_quote = _collapse_spaces(quote)
    if len(clean_quote) < 3:
        return False, "", None, ""

    q_lower = clean_quote.lower()
    for entry in candidate_log:
        entry_clean = _collapse_spaces(entry.get("text", ""))
        idx = entry_clean.lower().find(q_lower)
        if idx != -1:
            literal_slice = entry_clean[idx:idx + len(clean_quote)]
            return True, literal_slice, entry.get("elapsed_seconds"), str(entry.get("source", "speech"))

    joined = _collapse_spaces(" ".join(entry.get("text", "") for entry in candidate_log))
    idx_joined = joined.lower().find(q_lower)
    if idx_joined != -1:
        literal_slice = joined[idx_joined:idx_joined + len(clean_quote)]
        first_sec = candidate_log[0].get("elapsed_seconds") if candidate_log else None
        return True, literal_slice, first_sec, "speech"

    return False, "", None, ""


def _split_sentences_and_clauses(text: str) -> list[str]:
    """Divide um texto em sentenças e sub-cláusulas preservando escopo de negação em listas."""
    sentences = [s.strip() for s in re.split(r"[.!?\n;]+", text) if s.strip()]
    return sentences


def _sentence_is_negated_at_match(norm_sentence: str, match_pos: int) -> bool:
    """Determina se a ocorrência em `match_pos` está sob negação (incluindo listas tipo 'Não peço A, B ou C')."""
    prefix_clause = _extract_clause_prefix(norm_sentence, match_pos, window=140)
    if _clause_has_negation(prefix_clause):
        return True
    if any(marker in prefix_clause for marker in ("antes de ", "antes do ", "antes da ", "sem fazer ", "pos-")):
        return True
    before = norm_sentence[:match_pos]
    last_comma = before.rfind(",")
    if last_comma != -1:
        after_comma = before[last_comma + 1:]
        if any(verb in after_comma for verb in _POSITIVE_VERBS):
            return False
        head_sentence = before[:last_comma].strip()
        if head_sentence.startswith(("nao ", "nunca ", "jamais ", "sem ", "dispenso ", "recuso ")):
            return True
    return False


def _quote_is_purely_negated(
    matched_quote: str,
    candidate_log: list[dict[str, Any]],
    source: str,
) -> bool:
    """Impede que citações sob negação explícita pontuem itens afirmativos."""
    if source != "speech":
        return False
    norm_quote = _normalize_text(matched_quote)
    if not norm_quote:
        return True
    if any(norm_quote.startswith(neg.strip()) for neg in _NEGATION_PREFIXES):
        return True

    for entry in candidate_log:
        if entry.get("source") != "speech":
            continue
        for sent in _split_sentences_and_clauses(entry.get("text", "")):
            norm_sent = _normalize_text(sent)
            idx = norm_sent.find(norm_quote)
            if idx != -1:
                return _sentence_is_negated_at_match(norm_sent, idx)
    return False


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    """Extrai objeto JSON válido mesmo quando envolvido em cercas markdown."""
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _item_concept_terms(item: dict[str, Any]) -> list[str]:
    """Expande as keywords do item com clusters de sinônimos clínicos equivalentes."""
    base_terms: list[str] = []
    for kw in item.get("keywords", []):
        nk = _normalize_text(kw)
        if nk:
            base_terms.append(nk)
    title_norm = _normalize_text(item.get("title", ""))

    expanded: list[str] = list(base_terms)
    for cluster in _CLINICAL_CONCEPT_CLUSTERS:
        norm_cluster = [_normalize_text(c) for c in cluster]
        if any(
            any(_find_term_matches(src, term) for term in norm_cluster)
            for src in base_terms + ([title_norm] if title_norm else [])
        ):
            for term in norm_cluster:
                if term not in expanded:
                    expanded.append(term)
    return expanded


def simulate_llm_judge_json(
    station_meta: dict[str, Any],
    candidate_log: list[dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    critical_errors: list[str],
) -> str:
    """
    Simulador hermético offline do Juiz LLM:
    Avalia sentença a sentença respeitando paráfrases clínicas, negação em listas e citação literal.
    """
    judged_items: list[dict[str, Any]] = []
    station_code = str(station_meta.get("code", "")).upper()

    # Prepara sentenças literais e ações do candidato
    units: list[dict[str, Any]] = []
    for entry in candidate_log:
        txt = _collapse_spaces(entry.get("text", ""))
        src = entry.get("source", "speech")
        if src == "speech":
            # Remove prefixo automático de conduct_notes para evitar contaminação de citação
            clean_speech = re.sub(r"^Conduta e Prescrição Verbalizada:\s*", "", txt, flags=re.IGNORECASE)
            for sent in _split_sentences_and_clauses(clean_speech):
                units.append({"text": sent, "norm": _normalize_text(sent), "source": "speech"})
        else:
            units.append({"text": txt, "norm": _normalize_text(txt), "source": src})

    for item in checklist_items:
        item_id = str(item.get("id", ""))
        is_inverse = bool(item.get("inverse", False))
        forbidden_terms = [_normalize_text(ft) for ft in item.get("forbidden_terms", []) if _normalize_text(ft)]

        if is_inverse and forbidden_terms:
            violated = False
            negated_quote = ""
            for u in units:
                for ft in forbidden_terms:
                    for m in _find_term_matches(u["norm"], ft):
                        if u["source"] != "speech" or not _sentence_is_negated_at_match(u["norm"], m.start()):
                            violated = True
                            break
                        if not negated_quote:
                            negated_quote = u["text"]
                    if violated:
                        break
                if violated:
                    break

            if not violated and not negated_quote:
                # Verifica também afirmações de não realizar exame/conduta proibida
                for u in units:
                    for kw in item.get("keywords", []):
                        nk = _normalize_text(kw)
                        if nk and _find_term_matches(u["norm"], nk):
                            negated_quote = u["text"]
                            break
                    if not negated_quote and (
                        "proibo" in u["norm"]
                        or "proibida" in u["norm"]
                        or "evitando solicitar" in u["norm"]
                        or "nao ha indicacao" in u["norm"]
                        or "contraindic" in u["norm"]
                    ):
                        negated_quote = u["text"]
                        break

            if violated or not negated_quote:
                judged_items.append({
                    "id": item_id,
                    "status": "NONE",
                    "evidence_quote": "",
                    "rationale": "Conduta contraindicada executada ou não verbalizada." if violated else "Critério não contemplado.",
                })
            else:
                judged_items.append({
                    "id": item_id,
                    "status": "FULL",
                    "evidence_quote": negated_quote,
                    "rationale": "Candidato afastou explicitamente a conduta iatrogênica.",
                })
            continue

        # Caso especial: REVALIDA-2023-GO-PEP item_1 (acolhimento/sigilo sem exigir BO)
        if station_code == "REVALIDA-2023-GO-PEP" and item_id == "item_1":
            demands_bo = any(
                _has_affirmative_mention(
                    u["norm"], "", ["exigir boletim", "exijo boletim", "exijo o boletim", "condicao para realizar"]
                )
                for u in units
            )
            if demands_bo:
                judged_items.append({
                    "id": item_id,
                    "status": "NONE",
                    "evidence_quote": "",
                    "rationale": "Exigiu boletim de ocorrência indevidamente.",
                })
                continue

        concepts = _item_concept_terms(item)
        matched_units: list[tuple[str, int]] = []

        for u in units:
            unit_hits = 0
            for term in concepts:
                for m in _find_term_matches(u["norm"], term):
                    if u["source"] != "speech" or not _sentence_is_negated_at_match(u["norm"], m.start()):
                        unit_hits += 1
                        break
            if unit_hits > 0:
                matched_units.append((u["text"], unit_hits))

        if not matched_units:
            judged_items.append({
                "id": item_id,
                "status": "NONE",
                "evidence_quote": "",
                "rationale": "Critério ausente ou explicitamente negado pelo candidato.",
            })
        else:
            best_quote, best_hits = max(matched_units, key=lambda x: x[1])
            total_hits = sum(h for _, h in matched_units)
            status = "FULL" if (total_hits >= 1 and (best_hits >= 1 or len(matched_units) >= 1)) else "PARTIAL"
            judged_items.append({
                "id": item_id,
                "status": status,
                "evidence_quote": best_quote,
                "rationale": "Conduta ou conceito clínico contemplado com citação literal.",
            })

    # Erros críticos também extraídos com citação literal quando presentes
    spoken_joined = " ".join(u["text"] for u in units if u["source"] == "speech")
    prescribed_joined = " ".join(u["text"] for u in units if u["source"] != "speech")
    crit_triggered: list[dict[str, str]] = []
    if critical_errors:
        from .osce_evaluation import evaluate_critical_safety_violations

        violated = evaluate_critical_safety_violations(
            critical_errors=critical_errors,
            evidence_text=spoken_joined,
            actions=[],
            station_meta=station_meta,
        )
        if not violated and prescribed_joined:
            violated = evaluate_critical_safety_violations(
                critical_errors=critical_errors,
                evidence_text=f"{spoken_joined} {prescribed_joined}",
                actions=[],
                station_meta=station_meta,
            )
        for err in violated:
            crit_triggered.append({
                "error": err,
                "evidence_quote": units[0]["text"] if units else "",
                "rationale": "Violação de segurança identificada na conduta do candidato.",
            })

    return json.dumps(
        {"items": judged_items, "critical_errors_triggered": crit_triggered},
        ensure_ascii=False,
    )


def _run_block0_fallback(
    station_meta: dict[str, Any],
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    critical_errors: list[str],
    reason: str = "",
) -> dict[str, Any]:
    """Executa o motor determinístico do Bloco 0 quando o Juiz LLM falha."""
    from .osce import collect_candidate_evidence, score_checklist_items

    if reason:
        logger.warning("[OSCE Judge] Fallback determinístico ativado: %s", reason)

    evidence_data = collect_candidate_evidence(transcript, actions)
    scored_items = score_checklist_items(checklist_items, evidence_data)
    evaluated_items = [
        {
            "id": it["id"],
            "criterion_id": it["criterion_id"],
            "code": it["code"],
            "title": it["title"],
            "description": it["description"],
            "category": it["category"],
            "weight": it["weight"],
            "max_score": it["max_score"],
            "optional": bool(it.get("optional", False)),
            "clinical_note": str(it.get("clinical_note", "")).strip(),
            "score_earned": it["score_earned"],
            "awarded_score": it["awarded_score"],
            "status": it["status"],
            "timestamp_achieved_sec": it["timestamp_achieved_sec"],
            "evidence": it["evidence"],
            "evidence_citation": it["evidence_citation"],
            "evidence_quote": "",
            "rationale": "",
        }
        for it in scored_items
    ]
    red_flags = evaluate_osce_red_flags(
        actions=actions,
        transcript=transcript,
        station_meta=station_meta,
        checklist_items=checklist_items,
        critical_errors=critical_errors,
        evidence_text=evidence_data["all_text"],
    )
    return {
        "evaluated_items": evaluated_items,
        "red_flags": red_flags,
        "graded_with_ai": False,
        "grading_mode": "deterministic_fallback",
        "grading_notice": "Corrigido sem IA",
    }


def _build_judge_prompts(
    station_meta: dict[str, Any],
    candidate_log: list[dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    critical_errors: list[str],
) -> tuple[str, str]:
    system_instruction = (
        "Você é o Juiz Examinador rigoroso de uma prova prática médica (OSCE). "
        "Avalie exclusivamente o que o candidato falou, prescreveu ou executou no registro cronológico fornecido. "
        "REGRAS INVIOLÁVEIS:\n"
        "1. Aceite sinônimos clínicos e paráfrases corretas mesmo sem usar palavras exatas do barema.\n"
        "2. Se o candidato NEGOU ou RECUSOU uma conduta, marque status 'NONE' (exceto em itens marcados inverse=true, onde pontua se ele rejeitou a conduta proibida e não a executou).\n"
        "3. Para TODO item marcado como 'FULL' ou 'PARTIAL', você DEVE copiar em `evidence_quote` uma substring LITERAL e EXATA do texto do candidato que comprove o item. Nunca invente citações.\n"
        "4. Responda APENAS em JSON válido seguindo exatamente o schema pedido."
    )

    simplified_items = [
        {
            "id": it.get("id"),
            "title": it.get("title"),
            "description": it.get("description"),
            "weight": it.get("weight"),
            "optional": bool(it.get("optional", False)),
            "clinical_note": str(it.get("clinical_note", "")).strip(),
            "keywords": it.get("keywords", []),
            "inverse": bool(it.get("inverse", False)),
            "forbidden_terms": it.get("forbidden_terms", []),
        }
        for it in checklist_items
    ]

    user_payload = {
        "station": {
            "code": station_meta.get("code"),
            "title": station_meta.get("title"),
            "area": station_meta.get("area"),
        },
        "candidate_timeline": candidate_log,
        "checklist_items": simplified_items,
        "critical_errors": critical_errors,
        "expected_output_schema": {
            "items": [
                {
                    "id": "item_1",
                    "status": "FULL | PARTIAL | NONE",
                    "evidence_quote": "trecho literal exato do candidate_timeline ou vazio se NONE",
                    "rationale": "justificativa objetiva em até 1 frase",
                }
            ],
            "critical_errors_triggered": [
                {
                    "error": "string exata de critical_errors",
                    "evidence_quote": "trecho literal exato do candidate_timeline",
                    "rationale": "motivo objetivo",
                }
            ],
        },
    }
    return system_instruction, json.dumps(user_payload, ensure_ascii=False, indent=2)


def evaluate_session_with_judge(
    station_meta: dict[str, Any],
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    critical_errors: list[str] | None = None,
) -> dict[str, Any]:
    """
    Executa a correção semântica com o Juiz LLM (temperatura 0, JSON estrito e trava anti-alucinação).
    Se não houver atividade do candidato ou o LLM falhar, utiliza o motor determinístico do Bloco 0.
    """
    crit_list = list(critical_errors or [])
    candidate_log = build_candidate_timeline_log(transcript, actions)

    # Sessão sem nenhuma interação do candidato: retorna zerado imediatamente sem desperdiçar LLM
    if not candidate_log:
        return _run_block0_fallback(
            station_meta=station_meta,
            transcript=transcript,
            actions=actions,
            checklist_items=checklist_items,
            critical_errors=crit_list,
        ) | {"graded_with_ai": True, "grading_mode": "ai_judge", "grading_notice": "Corrigido com IA"}

    system_prompt, user_prompt = _build_judge_prompts(
        station_meta=station_meta,
        candidate_log=candidate_log,
        checklist_items=checklist_items,
        critical_errors=crit_list,
    )

    try:
        resp = gemini_pool.generate_content_with_fallback(
            prompt=user_prompt,
            system_instruction=system_prompt,
            json_mode=True,
            temperature=0.0,
            timeout=18,
        )
        raw_text = resp.get("text", "") if isinstance(resp, dict) else str(resp or "")
    except Exception as exc:  # noqa: BLE001
        return _run_block0_fallback(
            station_meta=station_meta,
            transcript=transcript,
            actions=actions,
            checklist_items=checklist_items,
            critical_errors=crit_list,
            reason=f"Exceção na chamada ao LLM: {exc}",
        )

    parsed = _extract_json_object(raw_text)
    if not parsed or not isinstance(parsed.get("items"), list) or len(parsed["items"]) == 0:
        return _run_block0_fallback(
            station_meta=station_meta,
            transcript=transcript,
            actions=actions,
            checklist_items=checklist_items,
            critical_errors=crit_list,
            reason="JSON inválido ou lista de itens vazia retornada pelo juiz.",
        )

    judged_map: dict[str, dict[str, Any]] = {}
    for j_item in parsed["items"]:
        if isinstance(j_item, dict) and j_item.get("id"):
            judged_map[str(j_item["id"])] = j_item

    spoken_all = _normalize_text(" ".join(e["text"] for e in candidate_log if e["source"] == "speech"))
    prescribed_actions_all = _normalize_text(" ".join(e["text"] for e in candidate_log if e["source"] != "speech"))

    evaluated_items: list[dict[str, Any]] = []
    for item in checklist_items:
        item_id = str(item.get("id", ""))
        is_optional = bool(item.get("optional", False)) or float(item.get("weight", 1.0)) <= 0.0
        weight = 0.0 if is_optional else float(item.get("weight", 1.0))
        clinical_note = str(item.get("clinical_note", "")).strip()
        is_inverse = bool(item.get("inverse", False))
        forbidden_terms = [str(ft) for ft in item.get("forbidden_terms", [])]

        j_entry = judged_map.get(item_id, {})
        raw_status = str(j_entry.get("status", "NONE")).upper().strip()
        if raw_status not in ("FULL", "PARTIAL", "NONE"):
            raw_status = "NONE"

        raw_quote = str(j_entry.get("evidence_quote") or "").strip()
        rationale = str(j_entry.get("rationale") or "").strip()

        verified_quote = ""
        achieved_sec: int | None = None

        if raw_status in ("FULL", "PARTIAL"):
            ok, literal_quote, sec, src = verify_evidence_quote(raw_quote, candidate_log)
            if not ok:
                # Trava anti-alucinação: descarta evidência inventada e zera item
                raw_status = "NONE"
                rationale = "Evidência descartada pela auditoria literal (citação ausente no registro do candidato)."
            else:
                if is_inverse and forbidden_terms:
                    violated_ft = any(
                        _has_affirmative_mention(spoken_all, prescribed_actions_all, [ft])
                        for ft in forbidden_terms
                    )
                    if violated_ft:
                        raw_status = "NONE"
                        rationale = "Critério violado: conduta contraindicada executada ou mencionada afirmativamente."
                    else:
                        verified_quote = literal_quote
                        achieved_sec = sec
                else:
                    if _quote_is_purely_negated(literal_quote, candidate_log, src):
                        raw_status = "NONE"
                        rationale = "Critério negado ou recusado pelo candidato."
                    else:
                        verified_quote = literal_quote
                        achieved_sec = sec

        if raw_status == "FULL":
            awarded = weight
        elif raw_status == "PARTIAL":
            awarded = round(weight * 0.5, 2)
        else:
            awarded = 0.0

        default_unmatched = (
            clinical_note
            or ("Item opcional/neutro (sem penalidade na nota)." if is_optional else "Critério não contemplado nas falas ou ações do candidato.")
        )
        citation_text = (
            f'"{verified_quote}"'
            + (f" — {rationale}" if rationale else "")
            + (f" ({clinical_note})" if clinical_note else "")
            if verified_quote
            else (rationale or default_unmatched)
        )
        if not verified_quote and is_optional and not rationale:
            rationale = default_unmatched

        evaluated_items.append({
            "id": item.get("id"),
            "criterion_id": item_id,
            "code": str(item.get("code", item_id or "ITEM")),
            "title": item.get("title"),
            "description": item.get("description", item.get("title", "")),
            "category": item.get("category", "Geral"),
            "weight": weight,
            "max_score": weight,
            "optional": is_optional,
            "clinical_note": clinical_note,
            "score_earned": awarded,
            "awarded_score": awarded,
            "status": raw_status,
            "timestamp_achieved_sec": achieved_sec,
            "evidence": citation_text,
            "evidence_citation": citation_text,
            "evidence_quote": verified_quote,
            "rationale": rationale,
        })

    # Combina detecção determinística de red flags / segurança clínica com críticas validadas pelo juiz
    all_candidate_text = " ".join(e["text"] for e in candidate_log)
    red_flags = evaluate_osce_red_flags(
        actions=actions,
        transcript=transcript,
        station_meta=station_meta,
        checklist_items=checklist_items,
        critical_errors=crit_list,
        evidence_text=all_candidate_text,
    )

    existing_descs = {_normalize_text(rf.get("description", "")) for rf in red_flags}
    for ce in parsed.get("critical_errors_triggered", []) or []:
        if not isinstance(ce, dict):
            continue
        err_text = str(ce.get("error") or "").strip()
        ce_quote = str(ce.get("evidence_quote") or "").strip()
        if not err_text or err_text not in crit_list:
            continue
        ok_ce, literal_ce, sec_ce, _ = verify_evidence_quote(ce_quote, candidate_log)
        if not ok_ce:
            continue
        if _normalize_text(err_text) not in existing_descs:
            existing_descs.add(_normalize_text(err_text))
            red_flags.append({
                "code": "RF_CLINICAL_SAFETY",
                "title": "Violação de Segurança Clínica",
                "description": err_text,
                "timestamp_sec": sec_ce or 0,
                "score_deduction": 1.5,
                "evidence_quote": literal_ce,
                "clinical_consequence": str(ce.get("rationale") or "Quebra de diretriz de segurança estabelecida no barema."),
            })

    return {
        "evaluated_items": evaluated_items,
        "red_flags": red_flags,
        "graded_with_ai": True,
        "grading_mode": "ai_judge",
        "grading_notice": "Corrigido com IA",
    }
