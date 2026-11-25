"""Motores determinísticos de auditoria clínica, red flags, cronologia e radar OSCE."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


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


