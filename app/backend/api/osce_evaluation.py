"""Motores determinísticos de auditoria clínica, red flags, cronologia e radar OSCE."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def _normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos e espaços extras para matching tolerante a grafia."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


_NEGATION_PREFIXES = (
    "nao ", "nunca ", "jamais ", "sem ", "evitar ", "evito ",
    "contraindicad", "proibid", "nao faco ", "nao prescrevo ", "nao administrar ",
    "nao vou ", "nao quero ", "nao solicito ", "nao peco ", "nao indico ",
    "nao realizar ", "recuso ", "dispenso ", "deixo de ",
)

_CLAUSE_SEPARATORS = (".", ";", "!", "?", "\n", ",")


def _find_term_matches(norm_text: str, norm_term: str) -> list[re.Match[str]]:
    """Busca ocorrências de palavra/expressão inteira respeitando fronteiras alfanuméricas."""
    if not norm_text or not norm_term:
        return []
    end_boundary = r"(?!\d)" if norm_term[-1].isdigit() else r"(?![a-z0-9])"
    pattern = r"(?<![a-z0-9])" + re.escape(norm_term) + end_boundary
    return list(re.finditer(pattern, norm_text))


def _extract_clause_prefix(norm_text: str, match_start: int, window: int = 75) -> str:
    """Retorna o trecho imediatamente anterior ao match dentro da mesma cláusula."""
    window_start = max(0, match_start - window)
    prefix = norm_text[window_start:match_start]
    for sep in _CLAUSE_SEPARATORS:
        if sep in prefix:
            prefix = prefix.split(sep)[-1]
    return prefix


def _clause_has_negation(prefix: str) -> bool:
    """Verifica se o prefixo da cláusula contém marcador explícito de negação."""
    if any(neg in prefix for neg in _NEGATION_PREFIXES):
        return True
    if re.search(r"(?<![a-z0-9])nem(?![a-z0-9])", prefix):
        return True
    return False


def _has_affirmative_mention(spoken_norm: str, prescribed_norm: str, terms: list[str]) -> bool:
    """Retorna True se algum termo foi prescrito na prancheta ou mencionado sem negação na mesma cláusula."""
    norm_terms = [_normalize_text(t) for t in terms if _normalize_text(t)]
    if prescribed_norm:
        for t in norm_terms:
            if _find_term_matches(prescribed_norm, t):
                return True
    if not spoken_norm:
        return False
    for t in norm_terms:
        for m in _find_term_matches(spoken_norm, t):
            prefix = _extract_clause_prefix(spoken_norm, m.start())
            if not _clause_has_negation(prefix):
                return True
    return False


def _has_negated_mention(spoken_norm: str, terms: list[str]) -> bool:
    """Retorna True se algum termo foi explicitamente negado na fala do candidato."""
    if not spoken_norm:
        return False
    norm_terms = [_normalize_text(t) for t in terms if _normalize_text(t)]
    for t in norm_terms:
        for m in _find_term_matches(spoken_norm, t):
            prefix = _extract_clause_prefix(spoken_norm, m.start())
            if _clause_has_negation(prefix):
                return True
    return False


def evaluate_critical_safety_violations(
    critical_errors: list[str],
    evidence_text: str,
    actions: list[dict[str, Any]],
    station_meta: dict[str, Any]
) -> list[str]:
    """
    Motor de Auditoria de Segurança Clínica Beira-Leito (ClinicalSafetyGuard).
    Cruza contraindicações formais das bancas com falas, prescrições e procedimentos do candidato.
    """
    norm_evidence = _normalize_text(evidence_text)
    prescriptions: list[dict[str, Any]] = []
    action_tokens: list[str] = []

    for a in actions:
        act_type = str(a.get("action_type") or "").lower()
        if act_type == "prescription":
            prescriptions.extend(a.get("prescription_items", []))
        elif act_type in ("lab_imaging", "exam", "imaging", "procedure", "cardioversion"):
            action_tokens.append(
                _normalize_text(
                    f"{act_type} {a.get('action_target', '')} "
                    f"{a.get('procedure_type', '')} {a.get('anatomical_site', '')}"
                )
            )

    all_prescribed_drugs = " ".join([
        _normalize_text(
            f"{p.get('drug_name', '')} {p.get('dose', '')} {p.get('unit', '')} {p.get('route', '')} {p.get('notes', '')}"
        )
        for p in prescriptions
    ])
    prescribed_and_actions = " ".join(part for part in (all_prescribed_drugs, " ".join(action_tokens)) if part).strip()

    detected_violations: list[str] = []

    for err in critical_errors:
        err_norm = _normalize_text(err)
        flagged = False

        if "bicarbonato" in err_norm:
            if _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["bicarbonato", "nahco3", "bicarb"]):
                flagged = True

        elif "potassio" in err_norm and "insulina" in err_norm:
            has_insulin = _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["insulina", "insulina regular"]
            )
            checked_k = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "potassio", "k+", "gasometria", "eletrolitos", "kcl",
                    "cloreto de potassio", "ionograma", "calemia", "k serico",
                ],
            ) or any(
                a.get("action_type") in ("lab_imaging", "exam")
                and any(
                    k in _normalize_text(str(a.get("action_target", "")))
                    for k in ("gaso", "eletrolito", "potassio", "laboratorio", "ionograma")
                )
                for a in actions
            )
            if has_insulin and not checked_k:
                flagged = True

        elif "suspender" in err_norm and "insulina" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "suspender insulina", "suspendo a insulina", "suspender a infusao de insulina",
                    "desligar insulina", "desligo a insulina", "parar a insulina", "interromper insulina",
                ],
            ):
                flagged = True

        elif "trombolitico" in err_norm or "fibrinolitico" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "trombolise", "trombolitico", "fibrinolitico", "alteplase",
                    "tenecteplase", "estreptoquinase", "metalyse", "actilyse",
                ],
            ):
                flagged = True

        elif "estrategia invasiva" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["cateterismo", "cate", "estrategia invasiva", "hemodinamica", "coronariografia"]
            ) or _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["tratamento conservador exclusivo", "alta sem cateterismo", "nao indicar estrategia invasiva"],
            ):
                flagged = True

        elif "tomografia" in err_norm and ("instavel" in err_norm or "fast" in err_norm):
            has_tc_action = any(
                a.get("action_type") in ("lab_imaging", "exam", "imaging")
                and _normalize_text(str(a.get("action_target", ""))) in ("tc", "tomografia")
                for a in actions
            )
            has_tc_speech = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["tomografia", "levar para tc", "encaminhar para tc", "solicito tc", "fazer tc"],
            )
            if has_tc_action or has_tc_speech:
                flagged = True

        elif "2 litros" in err_norm or "coagulopatia dilucional" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "3 litros", "3000 ml", "4 litros", "4000 ml",
                    "ressuscitacao agressiva", "mais de 2 litros",
                ],
            ):
                flagged = True

        elif ("corticosteroide" in err_norm or "cortico" in err_norm) and "bronquiolite" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["prednisolona", "prednisona", "dexametasona", "hidrocortisona", "corticoide", "corticosteroide"],
            ):
                flagged = True

        elif ("antibiotico" in err_norm or "antimicrobiano" in err_norm) and (
            "bronquiolite" in err_norm or "quadro viral" in err_norm or "diarreia aquosa" in err_norm
        ):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "amoxicilina", "azitromicina", "ceftriaxona", "claritromicina",
                    "ampicilina", "ciprofloxacino", "metronidazol", "antibiotico", "antimicrobiano",
                ],
            ):
                flagged = True

        elif "alta" in err_norm and ("hipoxemia" in err_norm or "observacao" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["dar alta", "libero para casa", "alta hospitalar", "alta para casa", "liberar para casa"],
            ):
                flagged = True

        elif "hamilton" in err_norm or "massagem bimanual" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["massagem", "hamilton", "compressao bimanual", "massagem bimanual"]
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["omitir massagem", "sem massagem bimanual"]
            ):
                flagged = True

        elif "atrasar" in err_norm and "uterotonico" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["ocitocina", "uterotonico", "uterotonicos", "acido tranexamico"]
            ) or _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["atrasar uterotonico", "aguardar exames antes da ocitocina", "esperar laboratorio para ocitocina"],
            ):
                flagged = True

        elif "tudo psicologico" in err_norm or "desmerecer" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["tudo psicologico", "nao tem nada", "coisa da sua cabeca", "frescura"],
            ):
                flagged = True

        elif "bateria excessiva" in err_norm or "prevencao quaternaria" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["bateria de exames", "tomografia de corpo inteiro", "endoscopia e colonoscopia", "exames invasivos"],
            ):
                flagged = True

        elif "benzodiazepinico" in err_norm or "polifarmacia" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["benzodiazepinico", "benzodiazepinicos", "clonazepam", "rivotril", "diazepam", "alprazolam"],
            ):
                flagged = True

        elif "aguardar" in err_norm and ("troponina" in err_norm or "marcador" in err_norm or "enzima" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "aguardar troponina", "aguardo troponina", "aguardo o resultado da troponina",
                    "esperar troponina", "esperar a troponina", "esperar resultado da troponina",
                    "aguardar resultado de troponina", "esperar enzimas",
                ],
            ):
                flagged = True

        elif "nitrato" in err_norm:
            has_nitrate = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["nitrato", "isordil", "mononitrato", "dinitrato", "tridil", "nitroglicerina"],
            )
            checked_contra = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["sildenafila", "viagra", "tadalafila", "erecao", "ventriculo direito", "infarto de vd"],
            )
            if has_nitrate and not checked_contra:
                flagged = True

        elif "oxigenioterapia" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "cateter de o2", "oxigenio de rotina", "oxigenioterapia de rotina",
                    "oxigenio a", "o2 a", "mascara de o2", "o2 2l", "o2 3l", "o2 suplementar",
                ],
            ):
                flagged = True

        elif "nao indicar cirurgia" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["cirurgia", "laparotomia", "operar", "tratamento cirurgico"]
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["tratamento conservador", "conduta expectante"]
            ):
                flagged = True

        elif "endoscopia" in err_norm or "eda" in err_norm:
            if _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["eda", "endoscopia", "endoscopia digestiva"]
            ):
                flagged = True

        elif ("corticoide" in err_norm or "anti-histaminico" in err_norm) and "adrenalina" in err_norm:
            gave_adjunct = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["corticoide", "hidrocortisona", "prednisolona", "anti-histaminico", "prometazina", "difenidramina"],
            )
            gave_adrenaline = _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["adrenalina", "epinefrina"]
            )
            negated_adrenaline = _has_negated_mention(norm_evidence, ["adrenalina", "epinefrina"])
            if gave_adjunct and (not gave_adrenaline or negated_adrenaline):
                flagged = True

        elif "adrenalina" in err_norm and ("subcutanea" in err_norm or "intravenosa pura" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "adrenalina sc", "adrenalina subcutanea", "via subcutanea",
                    "adrenalina iv pura", "adrenalina endovenosa pura", "infusao intravenosa pura",
                ],
            ):
                flagged = True

        elif "nao prescrever sulfato" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["sulfato de magnesio", "magnesio", "zuspan"]
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["sem sulfato de magnesio", "dispensar sulfato de magnesio"]
            ):
                flagged = True

        elif "diazepam" in err_norm or "fenitoina" in err_norm:
            if _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["diazepam", "fenitoina", "hidantal"]):
                flagged = True

        elif "reduzir abruptamente" in err_norm or "120 mmhg" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "reduzir abruptamente", "pa menor que 120", "pa < 120",
                    "baixar pa para 100", "normalizar pa para 110",
                ],
            ):
                flagged = True

        elif "abrupta" in err_norm or "em pe" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["em pe", "no corredor", "de forma abrupta", "sem aviso previo", "voce tem cancer e pronto"],
            ):
                flagged = True

        elif "jargoes" in err_norm or "adenocarcinoma" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["adenocarcinoma invasivo moderadamente diferenciado", "jargao tecnico sem traduzir"],
            ):
                flagged = True

        elif "nao ha nada a fazer" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["nao ha nada a fazer", "nao tem mais o que fazer", "abandonar o vinculo"],
            ):
                flagged = True

        elif "amiodarona" in err_norm:
            if _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["amiodarona", "amiodarona venosa", "amiodarona 300"]
            ):
                flagged = True

        elif "sincronizacao" in err_norm:
            unsync_action = any(
                (a.get("action_type") == "cardioversion" or (a.get("action_type") == "procedure" and "cardioversion" in str(a.get("procedure_type", "")).lower()))
                and (a.get("sync") is False or "desincronizado" in str(a.get("findings", "")).lower())
                for a in actions
            )
            if unsync_action or _has_negated_mention(
                norm_evidence, ["sincronizar", "sincronizado", "sincronizacao", "botao de sincronizacao"]
            ) or _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["desfibrilar", "desfibrilacao", "choque nao sincronizado", "choque dessincronizado", "chocar sem sincronizar"],
            ):
                flagged = True

        elif "atrasar o antibiotico" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "atrasar o antibiotico", "antibiotico apos 3 horas",
                    "aguardar resultado da cultura para iniciar antibiotico", "esperar hemocultura sair",
                ],
            ) or _has_negated_mention(norm_evidence, ["antibiotico"]):
                flagged = True

        elif "dopamina" in err_norm:
            if _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["dopamina"]):
                flagged = True

        elif ("radiografia" in err_norm or "tomografia" in err_norm) and "pneumotorax" in err_norm:
            rx_done = any(
                a.get("action_type") in ("lab_imaging", "exam", "imaging")
                and _normalize_text(str(a.get("action_target", ""))) in ("rx", "raio_x", "rx_torax", "radiografia", "tc", "tomografia")
                for a in actions
            )
            decompression_done = any(
                a.get("action_type") == "procedure"
                and any(k in str(a.get("procedure_type", "")).lower() for k in ("puncture", "thoracocentesis", "chest_tube", "drainage"))
                for a in actions
            )
            if (rx_done and not decompression_done) or _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "solicito radiografia", "solicito rx", "pedir rx", "pedir raio x",
                    "raio-x antes", "radiografia antes", "tomografia antes de descomprimir", "solicito tomografia",
                ],
            ):
                flagged = True

        elif "intubacao" in err_norm and "descomprimir" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["intubar antes de descomprimir", "aguardar intubacao", "intubacao orotraqueal antes", "primeiro intubar"],
            ):
                flagged = True

        elif "plano a ou b" in err_norm or "reidratacao oral" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "plano a", "plano b", "apenas terapia de reidratacao oral",
                    "tro exclusiva", "manter apenas tro", "soro oral exclusivo",
                ],
            ):
                flagged = True

        elif "boletim de ocorrencia" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                [
                    "exigir boletim", "exijo boletim", "exijo o boletim", "exigir bo", "exijo bo",
                    "condicao para realizar o atendimento", "so atendo com boletim", "obrigatorio boletim de ocorrencia",
                ],
            ):
                flagged = True

        elif "nao prescrever a profilaxia de hiv" in err_norm:
            if _has_negated_mention(
                norm_evidence,
                ["pep", "profilaxia de hiv", "profilaxia hiv", "antirretroviral", "tenofovir", "dolutegravir"],
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["sem pep", "nao prescrever pep", "dispensar profilaxia hiv"]
            ):
                flagged = True

        elif ("anti-inflamatorio" in err_norm or "aas" in err_norm) and "dengue" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["aas", "aspirina", "ibuprofeno", "cetoprofeno", "nimesulida", "diclofenaco"],
            ):
                flagged = True

        elif "insulina" in err_norm and "glicose" in err_norm:
            has_insulin = _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["insulina"])
            has_glucose = _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["glicose", "glicosado", "glicoinsulina", "sg 50", "sg50", "sg 10", "sg10", "dextrose"],
            )
            if has_insulin and not has_glucose:
                flagged = True

        elif "espironolactona" in err_norm or "poupador" in err_norm:
            if _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["espironolactona"]):
                flagged = True

        elif "succinilcolina" in err_norm:
            if _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["succinilcolina"]):
                flagged = True

        elif "tocolitico" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["tocolise", "atosibana", "salbutamol", "terbutalina", "nifedipino para tocolise"],
            ):
                flagged = True

        elif "atrasar" in err_norm and "pep" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["atrasar o inicio da pep", "aguardar resultado laboratorial demorado", "esperar resultado em 7 dias"],
            ):
                flagged = True

        elif "espremer" in err_norm and "ferimento" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["espremer o ferimento", "espremer", "cortar o ferimento", "injetar eter"],
            ):
                flagged = True

        elif "sutura primaria" in err_norm and "mordedura" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["sutura primaria fechada", "suturar a mordedura", "dar pontos imediatamente"],
            ):
                flagged = True

        elif "observacao" in err_norm and "cao" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["apenas com observacao domiciliar", "observar o cao por 10 dias", "dispensar sem vacina"],
            ):
                flagged = True

        elif "teste rapido de hiv" in err_norm and "tuberculose" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["hiv", "sorologia", "teste rapido de hiv"]
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["nao solicito hiv", "dispenso teste de hiv"]
            ):
                flagged = True

        elif "contatos intradomiciliares" in err_norm and (
            _has_negated_mention(
                norm_evidence, ["contatos", "contatos intradomiciliares", "convocacao"]
            )
            or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["ignoro a investigacao de contatos", "sem investigar contatos"]
            )
        ):
            flagged = True

        elif "balonete" in err_norm and ("antes de observar" in err_norm or "sonda de foley" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["insuflar o balonete antes", "insuflo o balonete antes", "insuflar balonete sem saida de urina", "antes da saida de urina"],
            ):
                flagged = True

        elif "sonda uretral" in err_norm and ("resistencia" in err_norm or "uretrorragia" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["forcar a passagem da sonda", "forco a passagem da sonda", "forcar contra resistencia", "passo a sonda com uretrorragia"],
            ):
                flagged = True

        elif "puncao lombar" in err_norm and ("papiledema" in err_norm or "hipertensao intracraniana" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["puncao lombar imediata mesmo com sinais focais", "puncao lombar mesmo com papiledema", "puncionar com hipertensao intracraniana"],
            ):
                flagged = True

        elif "liquor" in err_norm and ("seringa" in err_norm or "mandril" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["aspiro o liquor", "aspirar o liquor com seringa", "sem reintroduzir o mandril", "sem recolocar o mandril"],
            ):
                flagged = True

        elif "liquido ascitico" in err_norm and "albumina" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["dreno mais de 5 litros sem", "sem prescrever albumina", "drenar ascite sem albumina"],
            ) or (
                _has_affirmative_mention(norm_evidence, prescribed_and_actions, ["dreno mais de 5 litros", "dreno 6 litros"])
                and _has_negated_mention(norm_evidence, ["albumina"])
            ):
                flagged = True

        elif "paracentese" in err_norm and ("vasos epigastricos" in err_norm or "circulacao colateral" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["trajeto dos vasos epigastricos", "sobre circulacao colateral", "reto abdominal medio"],
            ):
                flagged = True

        elif "alimentacao complementar" in err_norm and "6 meses" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["introducao precoce de agua", "oferecer agua", "oferecer cha", "iniciar papinha", "suco antes dos 6 meses"],
            ):
                flagged = True

        elif "morte subita" in err_norm and ("prona" in err_norm or "decubito lateral" in err_norm):
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["posicao prona", "dormir de brucos", "decubito lateral para dormir", "dormir de lado"],
            ):
                flagged = True

        elif "pre-natal" in err_norm and "sifilis" in err_norm:
            if _has_negated_mention(
                norm_evidence, ["sifilis", "hiv", "tipagem", "abo/rh", "sorologia"]
            ) or _has_affirmative_mention(
                norm_evidence, prescribed_and_actions, ["nao solicito sorologias", "dispenso teste de sifilis"]
            ):
                flagged = True

        elif "virus vivo" in err_norm and "gestacao" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["triplice viral", "vacina de varicela", "vacina da dengue", "vacina de virus vivo"],
            ):
                flagged = True

        elif "parada cardiorrespiratoria" in err_norm and "declaracao de obito" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["parada cardiorrespiratoria como causa basica", "pcr como causa basica", "registro parada cardiorrespiratoria"],
            ):
                flagged = True

        elif "iml" in err_norm and "causa" in err_norm:
            if _has_affirmative_mention(
                norm_evidence,
                prescribed_and_actions,
                ["encaminhar o corpo para o iml", "encaminho ao iml", "mando para o iml", "encaminho o corpo ao iml"],
            ):
                flagged = True

        if flagged and err not in detected_violations:
            detected_violations.append(err)

    return detected_violations


def generate_timeline_post_mortem(
    station_meta: dict[str, Any],
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    evaluated_items: list[dict[str, Any]],
    elapsed_seconds: int
) -> dict[str, Any]:
    """
    Reconstitui a cronologia beira-leito da estação segundo a segundo:
    - Identifica marcos da anamnese, sinais vitais, ECG, labs, manequim e prescrição
    - Detecta atrasos operacionais (porta-ECG, porta-ação inicial)
    - Detecta períodos de hesitação/inércia (> 65s sem ação)
    - Sinaliza quebras críticas de segurança clínica
    """
    events = []

    inst_name = station_meta.get("institution", "Banca Oficial")
    st_title = station_meta.get("title", "Estação Clínica")
    events.append({
        "time_seconds": 0,
        "time_formatted": "00:00",
        "event_type": "start",
        "title": "Entrada na Sala de Exame",
        "description": f"Candidato entra no consultório da banca ({inst_name} • {st_title}).",
        "status": "neutral",
        "feedback": "Início da contagem regressiva oficial. Boa prática: cumprimentar paciente e se identificar.",
        "score_impact": "Início da Prova"
    })

    candidate_action_times = [0]

    for act in actions:
        sec = int(act.get("elapsed_seconds", 0))
        act_type = act.get("action_type")
        act_target = act.get("action_target", "")
        payload = act.get("payload", {})
        candidate_action_times.append(sec)

        m = sec // 60
        s = sec % 60
        tf = f"{m:02d}:{s:02d}"

        if act_type == "vitals":
            status = "timely" if sec <= 90 else ("neutral" if sec <= 180 else "delayed")
            feedback = (
                "Monitorização de sinais vitais realizada com rapidez cirúrgica."
                if status == "timely" else
                "Sinais vitais checados adequadamente."
                if status == "neutral" else
                "Atenção ao tempo: em emergência, sinais vitais devem ser checados nos primeiros 90 segundos."
            )
            events.append({
                "time_seconds": sec,
                "time_formatted": tf,
                "event_type": "vitals",
                "title": "Aferição de Sinais Vitais & Monitor",
                "description": "Sinais vitais checados no monitor: PA, FC, FR, SatO2 e temperatura.",
                "status": status,
                "feedback": feedback,
                "score_impact": "+ Pontos Vitais"
            })

        elif act_type == "physical_exam":
            status = "timely" if sec <= 180 else "neutral"
            target_label = act_target.replace("_", " ").capitalize()
            events.append({
                "time_seconds": sec,
                "time_formatted": tf,
                "event_type": "physical_exam",
                "title": f"Exame Físico: {target_label}",
                "description": f"Palpação e ausculta direcionada ao segmento {target_label}.",
                "status": status,
                "feedback": f"Segmento {target_label} examinado com busca ativa de achados do barema.",
                "score_impact": "+1.0 pt"
            })

        elif act_type == "lab_imaging":
            target_norm = act_target.lower()
            is_ecg = any(k in target_norm for k in ["ecg", "eletro", "eletrocardiograma"])
            is_fast = any(k in target_norm for k in ["fast", "efast", "ultrassom"])

            if is_ecg:
                status = "timely" if sec <= 120 else ("neutral" if sec <= 240 else "delayed")
                feedback = (
                    "Meta Porta-ECG de excelência: solicitado em menos de 2 minutos de prova."
                    if status == "timely" else
                    "ECG solicitado em tempo aceitável para a queixa apresentada."
                    if status == "neutral" else
                    "Atraso Porta-ECG: dor torácica/isquemia exige solicitação imediata (< 2-3 min)."
                )
                events.append({
                    "time_seconds": sec,
                    "time_formatted": tf,
                    "event_type": "lab_imaging",
                    "title": "Solicitação de ECG 12 Derivações",
                    "description": "Eletrocardiograma de 12 derivações entregue pela banca.",
                    "status": status,
                    "feedback": feedback,
                    "score_impact": "Porta-ECG"
                })
            elif is_fast:
                status = "timely" if sec <= 180 else "neutral"
                events.append({
                    "time_seconds": sec,
                    "time_formatted": tf,
                    "event_type": "procedure",
                    "title": "Ultrassom E-FAST Beira-Leito",
                    "description": "Rastreamento ultrassonográfico de líquido livre em janelas torácicas e abdominais.",
                    "status": status,
                    "feedback": "Protocolo ATLS: busca precoce de hemoperitônio ou hemo/pneumotórax.",
                    "score_impact": "+2.0 pts"
                })
            else:
                events.append({
                    "time_seconds": sec,
                    "time_formatted": tf,
                    "event_type": "lab_imaging",
                    "title": f"Exame Complementar: {act_target.upper()}",
                    "description": f"Solicitado exame {act_target.upper()} e interpretado laudo.",
                    "status": "neutral",
                    "feedback": "Exame complementar solicitado e analisado junto à banca examinadora.",
                    "score_impact": "+0.5 a 1.0 pt"
                })

        elif act_type == "prescription":
            drugs_summary = payload.get("text", act_target)
            status = "timely" if sec <= 360 else "delayed"
            feedback = (
                "Prescrição administrada oportunamente antes da fase final da estação."
                if status == "timely" else
                "Prescrição realizada tardiamente no final da prova. Priorize estabilização precoce."
            )
            events.append({
                "time_seconds": sec,
                "time_formatted": tf,
                "event_type": "prescription",
                "title": "Prescrição Farmacológica na Prancheta",
                "description": f"Administração assinada na prancheta de emergência: {drugs_summary[:120]}...",
                "status": status,
                "feedback": feedback,
                "score_impact": "Conduta Terapêutica"
            })

        elif act_type == "procedure":
            proc_title = payload.get("title", act_target)
            events.append({
                "time_seconds": sec,
                "time_formatted": tf,
                "event_type": "procedure",
                "title": f"Procedimento: {proc_title}",
                "description": "Execução de procedimento beira-leito no manequim interativo.",
                "status": "timely",
                "feedback": "Procedimento invasivo executado com indicação e técnica corretas.",
                "score_impact": "+2.0 pts"
            })

    for item in transcript:
        if item.get("sender") == "candidato":
            sec = int(item.get("elapsed_seconds", 0))
            candidate_action_times.append(sec)
            msg = item.get("message", "")
            msg_lower = msg.lower()

            m = sec // 60
            s = sec % 60
            tf = f"{m:02d}:{s:02d}"

            if any(w in msg_lower for w in ["minha conduta", "prescrevo", "indico cirurgia", "encaminho", "passo o caso"]):
                events.append({
                    "time_seconds": sec,
                    "time_formatted": tf,
                    "event_type": "conduct",
                    "title": "Verbalização da Conduta Definitiva",
                    "description": msg[:140] + ("..." if len(msg) > 140 else ""),
                    "status": "timely" if sec >= 240 else "neutral",
                    "feedback": "Conduta e encaminhamento verbalizados claramente para o examinador.",
                    "score_impact": "+1.5 pts"
                })
            elif len(msg) > 15 and not any(e["time_seconds"] == sec and e["event_type"] == "anamnese" for e in events):
                events.append({
                    "time_seconds": sec,
                    "time_formatted": tf,
                    "event_type": "anamnese",
                    "title": "Interação Clínica com o Paciente",
                    "description": f'"{msg[:110]}..."',
                    "status": "timely" if sec <= 180 else "neutral",
                    "feedback": "Investigação sintomática, acolhimento e escuta atenta do paciente.",
                    "score_impact": "+ Diálogo"
                })

    candidate_action_times.sort()
    unique_times = sorted(list(set(candidate_action_times)))
    for i in range(len(unique_times) - 1):
        t1 = unique_times[i]
        t2 = unique_times[i + 1]
        gap = t2 - t1
        if gap >= 70:
            gap_mid = t1 + (gap // 2)
            m = gap_mid // 60
            s = gap_mid % 60
            events.append({
                "time_seconds": gap_mid,
                "time_formatted": f"{m:02d}:{s:02d}",
                "event_type": "hesitacao",
                "title": f"Período de Hesitação ({gap}s sem ação)",
                "description": f"Intervalo de {gap} segundos sem perguntas ou intervenções ativas do candidato.",
                "status": "delayed",
                "feedback": f"Atenção ao ritmo: {gap} segundos sem conduta. Na 2ª fase presencial, cada minuto ocioso consome tempo crucial de barema.",
                "score_impact": "Ritmo Comprometido"
            })

    st_title_lower = station_meta.get("title", "").lower()
    st_subtema_lower = station_meta.get("subtema", "").lower()
    all_targets = [str(a.get("action_target", "")).lower() for a in actions]
    all_types = [str(a.get("action_type", "")).lower() for a in actions]

    if "vitals" not in all_types:
        events.append({
            "time_seconds": elapsed_seconds or 480,
            "time_formatted": f"{(elapsed_seconds or 480)//60:02d}:{(elapsed_seconds or 480)%60:02d}",
            "event_type": "omissao",
            "title": "Omissão Crítica: Sinais Vitais Não Checados",
            "description": "Candidato não solicitou monitorização ou sinais vitais durante toda a estação.",
            "status": "critical_gap",
            "feedback": "Falta de segurança: todo atendimento beira-leito deve iniciar com a checagem dos sinais vitais.",
            "score_impact": "Perda Grave de Barema"
        })

    if ("sca" in st_title_lower or "coronariana" in st_subtema_lower or "taquicardia" in st_title_lower) and not any("ecg" in t for t in all_targets):
        events.append({
            "time_seconds": elapsed_seconds or 480,
            "time_formatted": f"{(elapsed_seconds or 480)//60:02d}:{(elapsed_seconds or 480)%60:02d}",
            "event_type": "omissao",
            "title": "Omissão Crítica: Eletrocardiograma Não Solicitado",
            "description": "Em queixa de dor torácica/isquemia, o ECG de 12 derivações é item obrigatório do barema.",
            "status": "critical_gap",
            "feedback": "Erro eliminatório: tempo porta-ECG não atingido porque o exame não foi solicitado.",
            "score_impact": "Eliminatório / -2.0 pts"
        })

    events.sort(key=lambda x: x["time_seconds"])

    timely_count = sum(1 for e in events if e.get("status") == "timely")
    delayed_count = sum(1 for e in events if e.get("status") == "delayed")
    critical_count = sum(1 for e in events if e.get("status") == "critical_gap")

    first_action_sec = unique_times[1] if len(unique_times) > 1 else elapsed_seconds
    ecg_sec = next((e["time_seconds"] for e in events if "ecg" in e["title"].lower()), None)

    if critical_count > 0 or delayed_count >= 3:
        pace_label = "Hesitante / Atrasos Críticos"
    elif timely_count >= 4 and delayed_count <= 1:
        pace_label = "Ritmo Cirúrgico / Ágil"
    else:
        pace_label = "Equilibrado / Médio"

    return {
        "events": events,
        "summary": {
            "total_events": len(events),
            "timely_count": timely_count,
            "delayed_count": delayed_count,
            "critical_gaps_count": critical_count,
            "door_to_first_action_seconds": first_action_sec,
            "door_to_ecg_seconds": ecg_sec,
            "pace_label": pace_label
        }
    }


def generate_competency_radar(
    station_meta: dict[str, Any],
    evaluated_items: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    elapsed_seconds: int,
    critical_warnings: Optional[list[str]] = None
) -> dict[str, Any]:
    """
    Calcula o Radar de Competências Médicas em 6 dimensões fundamentais de prova prática:
    1. Comunicação & Empatia
    2. Raciocínio Clínico & Anamnese
    3. Exame Físico & Habilidades Práticas
    4. Indicação & Interpretação de Exames Complementares
    5. Tomada de Decisão & Segurança Farmacológica
    6. Gestão do Tempo Beira-Leito
    """
    category_scores = {
        "comunicacao_empatia": {"earned": 0.0, "max": 0.0, "items": []},
        "raciocinio_clinico": {"earned": 0.0, "max": 0.0, "items": []},
        "exame_fisico": {"earned": 0.0, "max": 0.0, "items": []},
        "exames_complementares": {"earned": 0.0, "max": 0.0, "items": []},
        "seguranca_farmacologica": {"earned": 0.0, "max": 0.0, "items": []},
        "gestao_tempo": {"earned": 0.0, "max": 0.0, "items": []}
    }

    for it in evaluated_items:
        cat = it.get("category", "").lower()
        earned = float(it.get("score_earned", 0.0))
        weight = float(it.get("weight", 1.0))

        if "comunicacao" in cat or "empatia" in cat or "relacao" in cat:
            key = "comunicacao_empatia"
        elif "anamnese" in cat or "diagnostico" in cat or "raciocinio" in cat:
            key = "raciocinio_clinico"
        elif "fisico" in cat or "manobra" in cat or "procedimento" in cat:
            key = "exame_fisico"
        elif "lab" in cat or "imagem" in cat or "complementar" in cat or ("exame" in cat and "fisico" not in cat):
            key = "exames_complementares"
        elif "farmaco" in cat or "prescricao" in cat or "tratamento" in cat or "conduta" in cat:
            key = "seguranca_farmacologica"
        else:
            key = "raciocinio_clinico"

        category_scores[key]["earned"] += earned
        category_scores[key]["max"] += weight
        category_scores[key]["items"].append(it)

    real_actions = [a for a in actions if a.get("action_type") != "session_init"]
    cand_transcripts = [t for t in transcript if t.get("sender") == "candidato"]
    total_items_earned = sum(float(it.get("score_earned", 0.0)) for it in evaluated_items)

    time_score_max = 2.0
    if (not real_actions and not cand_transcripts) or total_items_earned == 0:
        time_score_earned = 0.0
    else:
        time_score_earned = 2.0
        if elapsed_seconds > 450:
            time_score_earned -= 0.5
        action_times = sorted([int(a.get("elapsed_seconds", 0)) for a in real_actions if a.get("elapsed_seconds")])
        for i in range(len(action_times) - 1):
            if action_times[i + 1] - action_times[i] >= 75:
                time_score_earned -= 0.5
                break
        time_score_earned = max(0.5, time_score_earned)
    category_scores["gestao_tempo"]["earned"] = time_score_earned
    category_scores["gestao_tempo"]["max"] = time_score_max

    dim_configs = [
        ("comunicacao_empatia", "Comunicação & Empatia", "Relação médico-paciente, acolhimento e clareza de linguagem."),
        ("raciocinio_clinico", "Raciocínio & Anamnese", "Investigação sintomática, fatores de risco e hipótese diagnóstica."),
        ("exame_fisico", "Exame Físico & Habilidades", "Ausculta, palpação, monitorização e procedimentos beira-leito."),
        ("exames_complementares", "Exames Complementares", "Indicação criteriosa de ECG, imagem, gasometria e laboratoriais."),
        ("seguranca_farmacologica", "Segurança Farmacológica", "Doses corretas, vias seguras, contraindicações e drogas prioritárias."),
        ("gestao_tempo", "Gestão do Tempo", "Ritmo, dinamismo e tomada de decisão antes dos avisos da banca.")
    ]

    dimensions = []
    total_pct = 0.0
    evaluated_dims_count = 0

    for key, name, desc in dim_configs:
        earned = category_scores[key]["earned"]
        c_max = category_scores[key]["max"]
        if c_max == 0:
            dimensions.append({
                "key": key,
                "name": name,
                "score_earned": 0.0,
                "score_max": 0.0,
                "percentage": None,
                "level": "Sem evidência",
                "description": desc,
                "feedback": "Dimensão sem critérios avaliados no barema desta estação."
            })
            continue

        pct = round(min(100.0, max(0.0, (earned / c_max) * 100)), 1)
        if key == "seguranca_farmacologica" and critical_warnings:
            floor_pct = 0.0 if earned == 0 else 15.0
            penal_pct = max(floor_pct, pct - (len(critical_warnings) * 35.0))
            pct = round(penal_pct, 1)
        total_pct += pct
        evaluated_dims_count += 1

        if pct >= 80.0:
            level = "Excelente"
            feedback = "Domínio seguro nesta competência. Execução precisa segundo o gabarito."
        elif pct >= 60.0:
            level = "Satisfatório"
            feedback = "Bom desempenho, com oportunidades de refinamento e maior agilidade."
        else:
            level = "Necessita Atenção"
            feedback = "Ponto de atenção na prova prática. Revise os passos capitais no FSRS."

        dimensions.append({
            "key": key,
            "name": name,
            "score_earned": round(earned, 1),
            "score_max": round(c_max, 1),
            "percentage": pct,
            "level": level,
            "description": desc,
            "feedback": feedback
        })

    overall_avg = round(total_pct / evaluated_dims_count, 1) if evaluated_dims_count > 0 else 0.0

    evaluated_dims = [d for d in dimensions if d["percentage"] is not None]
    sorted_dims = sorted(evaluated_dims, key=lambda d: d["percentage"], reverse=True)
    strengths = [d["name"] for d in sorted_dims[:2] if d["percentage"] >= 65]
    weaknesses = [d["name"] for d in sorted_dims[-2:] if d["percentage"] < 75]

    return {
        "overall_average": overall_avg,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "dimensions": dimensions
    }


def evaluate_osce_red_flags(
    actions: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    station_meta: dict[str, Any],
    checklist_items: list[dict[str, Any]],
    critical_errors: Optional[list[str]] = None,
    evidence_text: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Motor Determinístico Unificado de Detecção de Erros Críticos (Red Flags + Segurança Clínica).
    Identifica iatrogenias anatômicas, quebra de sequência do ATLS e violações do barema sem duplicidade.
    """
    red_flags: list[dict[str, Any]] = []
    proc_actions = [a for a in actions if a.get("action_type") == "procedure"]
    exam_actions = [a for a in actions if a.get("action_type") in ("exam", "lab_imaging", "vitals", "labs", "imaging")]

    for p in proc_actions:
        site = str(p.get("anatomical_site", "")).lower()
        proc = str(p.get("procedure_type", "")).lower()
        elapsed = p.get("elapsed_seconds", 0)

        if "inferior_border" in site or ("iatrogenic" in site and ("thoracocentesis" in proc or "relief" in proc or "r2" in site)):
            red_flags.append({
                "code": "RF_ANAT_NEUROVASC",
                "title": "Lesão Iatrogênica do Feixe Vásculo-Nervoso Intercostal",
                "description": "Punção realizada rente à BORDA INFERIOR da costela superior. Risco iminente de hemotórax maciço por laceração de artéria e veia intercostais.",
                "timestamp_sec": elapsed,
                "score_deduction": 2.5,
                "caps_station_at": 4.0,
                "clinical_consequence": "Hemotórax iatrogênico agudo decorrente de sítio cirúrgico incorreto."
            })

        if "thyroid_gland" in site or ("iatrogenic" in site and ("crico" in proc or "cricothyroidotomy" in site or "thyroid" in site)):
            red_flags.append({
                "code": "RF_ANAT_THYROID",
                "title": "Erro Anatômico Crítico em Via Aérea Cirúrgica",
                "description": "Incisão cirúrgica realizada sobre o istmo da glândula tireoide em vez da membrana cricotireoidea.",
                "timestamp_sec": elapsed,
                "score_deduction": 3.0,
                "caps_station_at": 3.0,
                "clinical_consequence": "Hemorragia cervical maciça com inundação traqueal e impossibilidade de oxigenação."
            })

    for a in actions:
        if a.get("action_type") == "cardioversion" or (a.get("action_type") == "procedure" and "cardioversion" in str(a.get("procedure_type", "")).lower()):
            if a.get("sync") is False or "desincronizado" in str(a.get("findings", "")).lower():
                red_flags.append({
                    "code": "RF_ELEC_UNSYNC_VT",
                    "title": "Choque Desincronizado em Taquiarritmia com Pulso",
                    "description": "Disparo elétrico não-sincronizado aplicado em paciente com pulso presente (Fenômeno R-sobre-T).",
                    "timestamp_sec": a.get("elapsed_seconds", 0),
                    "score_deduction": 3.0,
                    "caps_station_at": 3.0,
                    "clinical_consequence": "Indução iatrogênica de Fibrilação Ventricular e Parada Cardiorrespiratória."
                })

    station_code = str(station_meta.get("code", "")).upper()
    is_trauma = any(k in station_code for k in ("FAST", "TRAUMA", "PNEUMO")) or "trauma" in str(station_meta.get("title", "")).lower()
    if is_trauma:
        imaging_requests = [
            a for a in exam_actions
            if _normalize_text(str(a.get("action_target", ""))) in ("tc", "tomografia", "raio", "rx", "raio_x", "rx_torax")
        ]
        has_decompression = any(
            any(k in str(p.get("procedure_type", "")).lower() for k in ("thoracocentesis", "chest_tube", "puncture", "drainage"))
            for p in proc_actions
        )
        if imaging_requests and not has_decompression and "PNEUMO" in station_code:
            first_img_time = imaging_requests[0].get("elapsed_seconds", 0)
            red_flags.append({
                "code": "RF_ABCDE_VIOLATION",
                "title": "Atropelo da Sequência do ATLS (Quebra do ABCDE)",
                "description": "Solicitou exames de imagem secundários antes de realizar a descompressão de emergência em tórax hipertensivo.",
                "timestamp_sec": first_img_time,
                "score_deduction": 2.0,
                "caps_station_at": 4.5,
                "clinical_consequence": "Atraso crítico na reversão de choque obstrutivo com evolução para PCR em AESP."
            })

    spoken_only = _normalize_text(" ".join([
        str(t.get("message", "")) for t in transcript if t.get("sender") == "candidato"
    ]))
    title_norm = _normalize_text(station_meta.get("title", ""))
    subtema_norm = _normalize_text(station_meta.get("subtema", ""))
    if ("choque cardiogenico" in title_norm or "cocaina" in subtema_norm) and _has_affirmative_mention(
        spoken_only, "", ["betabloqueador", "metoprolol", "propranolol", "atenolol"]
    ):
        red_flags.append({
            "code": "RF_PHARM_CONTRA",
            "title": "Prescrição Farmacológica de Alto Risco",
            "description": "Prescrição de betabloqueador em vigência de choque cardiogênico ou intoxicação por cocaína.",
            "timestamp_sec": 0,
            "score_deduction": 2.0,
            "caps_station_at": 4.5,
            "clinical_consequence": "Depressão miocárdica aguda e agravamento de choque cardiogênico."
        })

    if critical_errors:
        eval_text = evidence_text if evidence_text is not None else spoken_only
        safety_violations = evaluate_critical_safety_violations(
            critical_errors=critical_errors,
            evidence_text=eval_text,
            actions=actions,
            station_meta=station_meta,
        )
        existing_codes = {rf.get("code") for rf in red_flags}
        existing_descs = {_normalize_text(rf.get("description", "")) for rf in red_flags}
        for warn in safety_violations:
            warn_norm = _normalize_text(warn)
            if "RF_ABCDE_VIOLATION" in existing_codes and "pneumotorax" in warn_norm and ("radiografia" in warn_norm or "tomografia" in warn_norm):
                continue
            if "RF_ELEC_UNSYNC_VT" in existing_codes and "sincronizacao" in warn_norm:
                continue
            if warn_norm in existing_descs:
                continue
            existing_descs.add(warn_norm)
            red_flags.append({
                "code": "RF_CLINICAL_SAFETY",
                "title": "Violação de Segurança Clínica",
                "description": warn,
                "timestamp_sec": 0,
                "score_deduction": 1.5,
                "clinical_consequence": "Quebra de diretriz de segurança estabelecida no barema.",
            })

    return red_flags


def compute_competency_radar_5d(
    station_meta: dict[str, Any],
    evaluated_items: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    elapsed_seconds: int,
    red_flags: list[dict[str, Any]]
) -> dict[str, Any]:
    """Computa o Radar Psicométrico em 5 Dimensões Médicas Fundamentais (0 a 100 ou None sem evidência)."""
    diag_items = [
        it for it in evaluated_items
        if any(k in str(it.get("category", "")).lower() for k in ("anamnese", "diagnostico", "raciocinio"))
    ]
    diag_pct: Optional[float] = (
        round((sum(float(it.get("score_earned", 0.0)) for it in diag_items) / max(1.0, sum(float(it.get("weight", 1.0)) for it in diag_items))) * 100, 1)
        if diag_items else None
    )

    comm_items = [
        it for it in evaluated_items
        if any(k in str(it.get("category", "")).lower() for k in ("relacao", "comunicacao", "empatia"))
    ]
    comm_pct: Optional[float] = (
        round((sum(float(it.get("score_earned", 0.0)) for it in comm_items) / max(1.0, sum(float(it.get("weight", 1.0)) for it in comm_items))) * 100, 1)
        if comm_items else None
    )

    proc_items = [
        it for it in evaluated_items
        if any(k in str(it.get("category", "")).lower() for k in ("fisico", "procedimento", "manobra", "ausculta"))
    ]
    proc_pct: Optional[float] = (
        round((sum(float(it.get("score_earned", 0.0)) for it in proc_items) / max(1.0, sum(float(it.get("weight", 1.0)) for it in proc_items))) * 100, 1)
        if proc_items else None
    )

    real_actions = [a for a in actions if a.get("action_type") != "session_init"]
    cand_transcripts = [t for t in transcript if t.get("sender") == "candidato"]
    total_items_earned = sum(float(it.get("score_earned", 0.0)) for it in evaluated_items)
    has_activity = bool(real_actions or cand_transcripts)

    if not has_activity and total_items_earned == 0:
        safety_pct: Optional[float] = None
    else:
        raw_safety = 100.0 - (len(red_flags) * 25.0)
        safety_pct = round(max(10.0, min(100.0, raw_safety)), 1)

    if not has_activity or total_items_earned == 0:
        time_pct = 0.0
    else:
        action_secs = [
            int(a.get("elapsed_seconds", 0)) for a in real_actions if a.get("elapsed_seconds") is not None
        ] + [
            int(t.get("elapsed_seconds", 0)) for t in cand_transcripts if t.get("elapsed_seconds") is not None
        ]
        first_action_time = min(action_secs, default=150)
        time_pct = 95.0 if first_action_time <= 90 else (75.0 if first_action_time <= 150 else 50.0)

    return {
        "clinical_reasoning": diag_pct,
        "communication_empathy": comm_pct,
        "surgical_semiotics": proc_pct,
        "patient_safety": safety_pct,
        "sus_time_efficiency": round(time_pct, 1),
    }


def build_chief_preceptor_review(
    station_meta: dict[str, Any],
    evaluated_items: list[dict[str, Any]],
    red_flags: list[dict[str, Any]],
    final_score: float
) -> dict[str, Any]:
    """Sintetiza parecer executivo honesto baseado nos itens reais do checklist e erros críticos."""
    title = str(station_meta.get("title", ""))
    inst = str(station_meta.get("institution", "USP-RP"))

    full_items = [
        str(it.get("title"))
        for it in evaluated_items
        if it.get("status") in ("FULL", "cumprido_total") and it.get("title")
    ]
    what_went_well = full_items[:3]

    unfulfilled = [
        str(it.get("title"))
        for it in evaluated_items
        if it.get("status") in ("NONE", "nao_cumprido")
        and it.get("title")
        and not it.get("optional")
        and float(it.get("max_score", it.get("weight", 1.0)) or 0.0) > 0.0
    ]
    rf_descriptions = [str(rf.get("description")) for rf in red_flags if rf.get("description")]
    critical_corrections: list[str] = []
    for entry in rf_descriptions + unfulfilled[:3]:
        if entry not in critical_corrections:
            critical_corrections.append(entry)

    canonical_lines = [
        f"{idx}. {it.get('title')}{' [Opcional / Neutro]' if it.get('optional') else ''}: {it.get('description')}"
        for idx, it in enumerate(evaluated_items, 1)
        if it.get("title") or it.get("description")
    ]
    canonical = "\n".join(canonical_lines) if canonical_lines else f"Revisar checklist da estação {title}."

    if final_score <= 0.0 and not full_items:
        summary = (
            f"Desempenho de {final_score:.1f}/10.0 na estação de {title} ({inst}). "
            "Nenhum critério do checklist foi cumprido nesta tentativa."
        )
    elif final_score >= 8.5:
        summary = (
            f"Desempenho de {final_score:.1f}/10.0 na estação de {title} ({inst}). "
            "Execução consistente dos passos essenciais do barema e manejo seguro."
        )
    elif final_score >= 7.0:
        summary = (
            f"Desempenho de {final_score:.1f}/10.0 na estação de {title} ({inst}). "
            "Atendimento satisfatório, com lacunas pontuais que limitaram a pontuação final."
        )
    else:
        summary = (
            f"Desempenho de {final_score:.1f}/10.0 na estação de {title} ({inst}). "
            "Pontuação abaixo da referência de treino (7,0); revise os itens não cumpridos e eventuais violações de segurança."
        )

    return {
        "executive_summary": summary,
        "what_went_well": what_went_well,
        "critical_corrections": critical_corrections,
        "gold_standard_canonical_conduct": canonical,
    }


def build_medquest_remediation(
    station_meta: dict[str, Any],
    weaknesses: list[str]
) -> dict[str, Any]:
    """Gera prescrição de estudo focado para remediação no MedQuest."""
    area = str(station_meta.get("area", "Clínica Médica"))
    subtema = str(station_meta.get("subtema", "Emergências"))

    return {
        "recommended_qbank_filters": [
            {"specialty": area, "subtopic": subtema, "difficulty": "Médio / Difícil"}
        ],
        "suggested_retry_station_id": str(station_meta.get("id", ""))
    }
