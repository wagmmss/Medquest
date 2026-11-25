"""Execução de exame físico, pedidos laboratoriais/imagem, prescrições e procedimentos OSCE."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from ..osce_data import EMERGENCY_DRUGS_CATALOG, PROCEDURES_CATALOG
from .osce_repository import _append_osce_session_entries, _get_task_progress
from .osce_safety_rules import _normalize_text
from .osce_scoring import evaluate_live_barema_progress, get_session_mode

_SPECIFIC_MANEUVER_TERMS = (
    "ausculta", "auscultar", "palpacao", "palpar", "percussao", "percutir",
    "inspecao", "inspecionar", "ectoscopia", "toque", "especular", "valvas",
    "reflexo", "reflexos", "clonus", "descompressao", "blumberg", "jobert",
    "prega", "turgor", "pulsos", "pulso", "perfusao", "enchimento capilar", "tec",
    "otoscopia", "oroscopia", "orofaringe", "glasgow", "pupilas", "pupila",
    "tiragem", "bcf", "batimentos cardiofetais", "altura uterina", "edema",
    "cacifo", "halito", "mucosas", "nivel de consciencia", "estado geral",
    "colar cervical", "via aerea", "pelve", "estabilidade pelvica", "traqueia",
    "turgencia jugular", "jugular", "kussmaul", "atls", "fundo uterino",
    "tonus uterino", "dinamica uterina", "leopold", "linfonodo", "virchow",
    "panturrilha", "homans", "giordano", "murphy", "rovsing", "psoas",
    "lasègue", "lasegue", "kernig", "brudzinski", "babinski", "livedo",
    "exame ginecologico", "exame genital", "exame neurologico", "manobra",
)

_VAGUE_LAB_TERMS = {
    "exame", "exames", "exames de sangue", "exames laboratoriais",
    "laboratorio", "exames complementares", "imagem", "exame de imagem",
    "rotina", "bioquimica",
}


def _resolve_physical_exam_maneuver(exam: dict[str, Any], action_target: str) -> dict[str, Any]:
    """Exige manobra semiológica específica e só entrega achados correspondentes."""
    norm_target = _normalize_text(action_target)
    maneuvers = exam.get("maneuvers") or {}
    findings = exam.get("findings") or {}

    has_specific_term = any(
        re.search(rf"\b{re.escape(_normalize_text(term))}\b", norm_target)
        for term in _SPECIFIC_MANEUVER_TERMS
    )
    direct_key_match = any(
        norm_target == _normalize_text(k) for k in maneuvers.keys()
    )

    if not norm_target or (not has_specific_term and not direct_key_match):
        msg = (
            "Examinador: Especifique a manobra semiológica desejada "
            "(ex.: ausculta pulmonar, palpação abdominal profunda, percussão torácica, inspeção geral)."
        )
        return {
            "examiner_message": msg,
            "finding": msg,
            "requires_specificity": True,
            "available": False,
            "matched_keys": [],
        }

    matched_entries: list[tuple[str, str, str]] = []
    if maneuvers:
        for k, meta in maneuvers.items():
            norm_k = _normalize_text(k).replace("_", " ")
            norm_label = _normalize_text(meta.get("label", ""))
            triggers = [_normalize_text(t) for t in meta.get("triggers", [])]
            candidates = [norm_k, norm_label, *triggers]
            if any(
                cand and (
                    cand in norm_target
                    or norm_target in cand
                    or all(tok in norm_target for tok in cand.split() if len(tok) >= 4)
                )
                for cand in candidates
                if len(cand) >= 3
            ):
                matched_entries.append((k, meta.get("label", k), str(meta.get("finding", ""))))

    if not matched_entries and findings and direct_key_match:
        for k, v in findings.items():
            if _normalize_text(k) == norm_target:
                matched_entries.append((k, k, str(v)))

    if not matched_entries and findings and not maneuvers:
        for k, v in findings.items():
            norm_k = _normalize_text(k)
            if norm_target in norm_k or norm_k in norm_target:
                matched_entries.append((k, k, str(v)))

    if matched_entries:
        combined_finding = " ".join(f"{lbl}: {txt}" if len(matched_entries) > 1 else txt for _, lbl, txt in matched_entries)
        return {
            "examiner_message": f"Exame Físico ({action_target}): {combined_finding}",
            "finding": combined_finding,
            "requires_specificity": False,
            "available": True,
            "matched_keys": [k for k, _, _ in matched_entries],
        }

    neutral_msg = "Normal / sem alterações (ou não disponível)."
    return {
        "examiner_message": f"Exame Físico ({action_target}): {neutral_msg}",
        "finding": neutral_msg,
        "requires_specificity": False,
        "available": True,
        "matched_keys": [],
    }


def _resolve_lab_imaging_order(labs: dict[str, Any], action_target: str) -> dict[str, Any]:
    """Resolve pedido livre de exame complementar sem vazar lista de exames da banca."""
    norm_target = _normalize_text(action_target)
    if not norm_target or norm_target in _VAGUE_LAB_TERMS:
        msg = "Examinador: Especifique qual exame complementar deseja solicitar."
        return {
            "found": False,
            "requires_specificity": True,
            "examiner_message": msg,
            "title": action_target,
            "result_text": "Especifique qual exame complementar deseja solicitar.",
            "image_url": None,
        }

    for k, v in labs.items():
        norm_k = _normalize_text(k).replace("_", " ")
        norm_raw_k = _normalize_text(k)
        norm_title = _normalize_text(v.get("title", ""))
        triggers = [_normalize_text(t) for t in v.get("triggers", [])]
        candidates = [norm_raw_k, norm_k, norm_title, *triggers]
        if any(
            cand and (
                norm_target == cand
                or (len(cand) >= 3 and re.search(rf"\b{re.escape(cand)}\b", norm_target))
                or (len(norm_target) >= 4 and norm_target in cand)
            )
            for cand in candidates
        ):
            if v.get("available", True):
                return {
                    "found": True,
                    "requires_specificity": False,
                    "key": k,
                    "examiner_message": f"Examinador entrega: {v.get('title', action_target)}. Resultado: {v.get('result_text')}",
                    "title": v.get("title", action_target),
                    "result_text": v.get("result_text"),
                    "image_url": v.get("image_url"),
                }

    neutral = "Normal / não disponível."
    return {
        "found": False,
        "requires_specificity": False,
        "examiner_message": f"Examinador ({action_target}): {neutral}",
        "title": action_target,
        "result_text": neutral,
        "image_url": None,
    }


def execute_osce_action(
    db,
    session_id: str,
    user_id: str,
    action_type: str,
    action_target: str,
    elapsed_seconds: int = 0
) -> dict[str, Any]:
    """
    Executa uma ação clínica beira-leito:
    - action_type = 'physical_exam': inspeciona segmento ou ausculta com estetoscópio virtual.
    - action_type = 'vitals': solicita sinais vitais imediatos.
    - action_type = 'lab_imaging': solicita exame complementar (ECG, RX, TC, labs).
    """
    sess = db.execute("""
        SELECT s.id, s.station_id, s.status, s.actions_taken_json, s.transcript_json,
               st.physical_exam_json, st.lab_imaging_json, st.checklist_barema_json, st.duration_seconds
        FROM osce_sessions s
        JOIN osce_stations st ON s.station_id = st.id
        WHERE s.id = ? AND s.user_id = ?
    """, (session_id, user_id)).fetchone()

    if not sess:
        raise ValueError("Sessão não encontrada.")
    if sess["status"] != "in_progress":
        return {"error": "Sessão finalizada."}

    actions = json.loads(sess["actions_taken_json"] or "[]")
    transcript = json.loads(sess["transcript_json"] or "[]")
    exam = json.loads(sess["physical_exam_json"] or "{}")
    labs = json.loads(sess["lab_imaging_json"] or "{}")

    now_iso = datetime.now(timezone.utc).isoformat()
    target_clean = action_target.strip().lower()

    action_record = {
        "action_type": action_type,
        "action_target": action_target,
        "elapsed_seconds": elapsed_seconds,
        "timestamp": now_iso
    }

    examiner_message = ""
    result_payload: dict[str, Any] = {}

    if action_type == "vitals":
        vitals = exam.get("vitals", {})
        examiner_message = (
            f"Sinais Vitais: PA {vitals.get('pa', '120x80')}, FC {vitals.get('fc', '80 bpm')}, "
            f"FR {vitals.get('fr', '16 irpm')}, SatO2 {vitals.get('sato2', '98%')}, "
            f"Temp {vitals.get('temp', '36.5 °C')}"
        )
        if "hgt" in vitals:
            examiner_message += f", Glicemia {vitals.get('hgt')}"
        result_payload = {"vitals": vitals}

    elif action_type == "physical_exam":
        resolved = _resolve_physical_exam_maneuver(exam, action_target)
        audio_key = None
        for mk in resolved.get("matched_keys", []):
            audio_key = exam.get("auscultation_audio", {}).get(mk) or audio_key
        if not audio_key:
            audio_key = exam.get("auscultation_audio", {}).get(target_clean)

        examiner_message = resolved["examiner_message"]
        result_payload = {
            "finding": resolved["finding"],
            "target": action_target,
            "audio_key": audio_key,
            "requires_specificity": resolved["requires_specificity"],
            "available": resolved["available"],
        }

    elif action_type in ("lab_imaging", "exam"):
        lab_res = _resolve_lab_imaging_order(labs, action_target)
        examiner_message = lab_res["examiner_message"]
        if lab_res["found"]:
            result_payload = {
                "title": lab_res["title"],
                "result_text": lab_res["result_text"],
                "image_url": lab_res["image_url"],
                "available": True,
            }
        else:
            result_payload = {
                "available": False,
                "title": lab_res["title"],
                "result_text": lab_res["result_text"],
                "requires_specificity": lab_res["requires_specificity"],
            }

    elif action_type == "complete_task":
        barema_raw = json.loads(sess["checklist_barema_json"] or "{}")
        raw_tasks = barema_raw.get("tasks", []) if isinstance(barema_raw, dict) else []
        progress_before = _get_task_progress(raw_tasks, actions)
        m_step = re.search(r"(\d+)", str(action_target or ""))
        requested_step = int(m_step.group(1)) if m_step else progress_before["current_step"]

        if not raw_tasks or progress_before["all_completed"]:
            examiner_message = "Examinador registra: Todas as tarefas da estação já foram declaradas concluídas."
            action_record["accepted"] = False
            result_payload = {"task_progress": progress_before, "accepted": False}
        elif requested_step != progress_before["current_step"]:
            examiner_message = (
                f"Examinador: Conclua a Tarefa {progress_before['current_step']} antes de avançar."
            )
            action_record["accepted"] = False
            action_record["step"] = requested_step
            result_payload = {"task_progress": progress_before, "accepted": False}
        else:
            action_record["accepted"] = True
            action_record["step"] = requested_step
            progress_after = _get_task_progress(raw_tasks, [*actions, action_record])
            if progress_after["all_completed"]:
                examiner_message = (
                    f"Examinador registra: Tarefa {requested_step} declarada concluída. "
                    "Todas as tarefas da estação foram liberadas."
                )
            else:
                next_step = progress_after["current_step"]
                examiner_message = (
                    f"Examinador registra: Tarefa {requested_step} declarada concluída. "
                    f"Tarefa {next_step} liberada."
                )
            result_payload = {
                "task_progress": progress_after,
                "accepted": True,
                "completed_step": requested_step,
            }

    # Registra ação e intervenção do examinador atomicamente (sem Lost Update)
    transcript_entry = {
        "sender": "examinador",
        "message": examiner_message,
        "timestamp": now_iso,
        "elapsed_seconds": elapsed_seconds,
        "action_payload": result_payload
    }
    latest_transcript, latest_actions = _append_osce_session_entries(
        db,
        session_id,
        user_id,
        new_transcript=[transcript_entry],
        new_actions=[action_record],
        elapsed_seconds=elapsed_seconds,
    )

    res_payload: dict[str, Any] = {
        "action_type": action_type,
        "target": action_target,
        "examiner_message": examiner_message,
        "payload": result_payload,
        "elapsed_seconds": elapsed_seconds
    }

    if get_session_mode(latest_actions) == "guided":
        barema_raw = json.loads(sess["checklist_barema_json"] or "{}")
        checklist_items = barema_raw.get("items", []) if isinstance(barema_raw, dict) else (barema_raw if isinstance(barema_raw, list) else [])
        res_payload["guided_feedback"] = evaluate_live_barema_progress(
            checklist_items, latest_transcript, latest_actions, elapsed_seconds, int(sess["duration_seconds"] or 480)
        )

    return res_payload



def get_emergency_drugs_catalog() -> list[dict[str, Any]]:
    """Retorna o catálogo completo de medicamentos da sala de emergência do OSCE."""
    return EMERGENCY_DRUGS_CATALOG


def get_procedures_catalog() -> list[dict[str, Any]]:
    """Retorna o catálogo de procedimentos beira-leito e janelas E-FAST para o manequim 2D."""
    return PROCEDURES_CATALOG


def prescribe_osce_drugs(
    db,
    session_id: str,
    user_id: str,
    prescription_items: list[dict[str, Any]],
    elapsed_seconds: int = 0
) -> dict[str, Any]:
    """
    Processa a assinatura de uma prescrição médica estruturada na Sala Vermelha / Emergência:
    - Analisa os fármacos e doses prescritos contra o checklist e regras clínicas da estação.
    - Notifica a intervenção da equipe de enfermagem da banca.
    - Enfileira fala do examinador para TTS imediato.
    """
    sess = db.execute("""
        SELECT s.id, s.station_id, s.status, s.actions_taken_json, s.transcript_json,
               st.code, st.title, st.checklist_barema_json, st.scenario_door_markdown, st.duration_seconds
        FROM osce_sessions s
        JOIN osce_stations st ON s.station_id = st.id
        WHERE s.id = ? AND s.user_id = ?
    """, (session_id, user_id)).fetchone()

    if not sess:
        raise ValueError("Sessão não encontrada.")
    if sess["status"] != "in_progress":
        return {"error": "Sessão finalizada."}

    actions = json.loads(sess["actions_taken_json"] or "[]")
    transcript = json.loads(sess["transcript_json"] or "[]")
    barema_raw = json.loads(sess["checklist_barema_json"] or "{}")
    barema_items = barema_raw.get("items", []) if isinstance(barema_raw, dict) else (barema_raw if isinstance(barema_raw, list) else [])
    now_iso = datetime.now(timezone.utc).isoformat()

    if not prescription_items:
        return {"error": "Nenhum medicamento informado na prescrição."}

    # Monta a descrição legível e busca correspondências no barema
    drug_summaries: list[str] = []
    matched_checklist_titles: list[str] = []
    sanitized_items: list[dict[str, Any]] = []

    for item in prescription_items[:30]:
        if not isinstance(item, dict):
            continue
        sanitized_items.append(item)
        name = str(item.get("drug_name") or "Medicamento").strip()[:120]
        dose = str(item.get("dose") or "").strip()[:40]
        unit = str(item.get("unit") or "").strip()[:30]
        route = str(item.get("route") or "").strip()[:60]
        notes = str(item.get("notes") or "").strip()[:240]

        desc_parts = [name]
        if dose:
            desc_parts.append(f"{dose} {unit}".strip())
        if route:
            desc_parts.append(f"via {route}")
        if notes:
            desc_parts.append(f"({notes})")

        drug_summaries.append(" ".join(desc_parts))

        # Checa pertinência com os itens de tratamento do barema da estação
        norm_item = _normalize_text(f"{name} {dose} {unit} {route} {notes}")
        for crit in barema_items:
            if isinstance(crit, dict) and crit.get("category") in ("conduta_tratamento", "tratamento", "conduta"):
                for kw in crit.get("keywords", []):
                    if _normalize_text(kw) in norm_item:
                        if crit.get("title") not in matched_checklist_titles:
                            matched_checklist_titles.append(crit.get("title", ""))

    if not sanitized_items:
        return {"error": "Nenhum medicamento válido informado na prescrição."}

    session_mode = get_session_mode(actions)
    visible_matched = matched_checklist_titles if session_mode == "guided" else []

    prescription_text = "; ".join(drug_summaries)
    examiner_message = (
        f"Prescrição da Sala de Emergência recebida pela equipe de enfermagem: {prescription_text}. "
        "Fármacos checados e administrados conforme prescrito. Sinais vitais em monitorização contínua."
    )

    action_record = {
        "action_type": "prescription",
        "action_target": "emergency_prescription",
        "prescription_items": sanitized_items,
        "matched_criteria": matched_checklist_titles,
        "elapsed_seconds": elapsed_seconds,
        "timestamp": now_iso
    }

    spoken_queue: list[dict[str, str]] = [
        {"speaker": "examinador", "text": f"Prescrição recebida e administrada pela enfermagem beira-leito: {prescription_text}."}
    ]

    transcript_entry = {
        "sender": "examinador",
        "message": examiner_message,
        "timestamp": now_iso,
        "elapsed_seconds": elapsed_seconds,
        "action_payload": {
            "type": "prescription",
            "items": sanitized_items,
            "matched_criteria": visible_matched
        }
    }

    latest_transcript, latest_actions = _append_osce_session_entries(
        db,
        session_id,
        user_id,
        new_transcript=[transcript_entry],
        new_actions=[action_record],
        elapsed_seconds=elapsed_seconds,
    )

    res_presc: dict[str, Any] = {
        "success": True,
        "prescription_text": prescription_text,
        "examiner_message": examiner_message,
        "matched_criteria": visible_matched,
        "spoken_queue": spoken_queue,
        "elapsed_seconds": elapsed_seconds
    }

    if get_session_mode(latest_actions) == "guided":
        res_presc["guided_feedback"] = evaluate_live_barema_progress(
            barema_items, latest_transcript, latest_actions, elapsed_seconds, int(sess["duration_seconds"] or 480)
        )

    return res_presc


def perform_osce_procedure(
    db,
    session_id: str,
    user_id: str,
    procedure_type: str,
    anatomical_site: str,
    elapsed_seconds: int = 0
) -> dict[str, Any]:
    """
    Executa um procedimento invasivo ou varredura ultrassonográfica (E-FAST) no manequim 2D beira-leito.
    """
    sess = db.execute("""
        SELECT s.id, s.station_id, s.status, s.actions_taken_json, s.transcript_json,
               st.code, st.title, st.physical_exam_json, st.lab_imaging_json, st.checklist_barema_json, st.duration_seconds
        FROM osce_sessions s
        JOIN osce_stations st ON s.station_id = st.id
        WHERE s.id = ? AND s.user_id = ?
    """, (session_id, user_id)).fetchone()

    if not sess:
        raise ValueError("Sessão não encontrada.")
    if sess["status"] != "in_progress":
        return {"error": "Sessão finalizada."}

    actions = json.loads(sess["actions_taken_json"] or "[]")
    transcript = json.loads(sess["transcript_json"] or "[]")
    station_code = sess["code"]
    labs = json.loads(sess["lab_imaging_json"] or "{}")
    now_iso = datetime.now(timezone.utc).isoformat()

    site_clean = anatomical_site.strip().lower()
    proc_type_clean = procedure_type.strip().lower()

    examiner_message = ""
    findings_desc = ""
    is_positive_finding = False
    image_url: Optional[str] = None

    # 1. VARREDURA ULTRASSONOGRÁFICA E-FAST (POCUS)
    if proc_type_clean in ("efast", "efast_probe", "fast") or site_clean in (
        "morrison", "splenorenal", "pelvic", "pericardial", "pleural_right", "pleural_left",
        "efast_ruq_morrison", "efast_morrison_ruq", "efast_luq_splenorenal", "efast_splenorenal_luq",
        "efast_subxiphoid_pericardial", "efast_suprapubic_pelvic"
    ):
        is_trauma_fast = "FAST" in station_code or "trauma" in sess["title"].lower() or "politrauma" in sess["title"].lower()

        if site_clean in ("morrison", "efast_ruq_morrison", "efast_morrison_ruq"):
            if is_trauma_fast:
                findings_desc = (
                    "Janela Hepatorrenal (Morrison): Presença de lâmina fina de líquido livre anecoico "
                    "no recesso entre o lobo hepático direito e o córtex renal anterior. Espaço de Morrison POSITIVO para líquido livre."
                )
                is_positive_finding = True
            else:
                findings_desc = "Janela Hepatorrenal (Morrison): Interface hepatorrenal nítida sem acúmulo de líquido anecoico."
        elif site_clean in ("splenorenal", "efast_luq_splenorenal", "efast_splenorenal_luq"):
            if is_trauma_fast:
                findings_desc = (
                    "Janela Esplenorrenal (Recesso de Koller): Presença de volumosa quantidade de líquido livre anecoico "
                    "circundando o polo inferior e hilo do baço, com irregularidade cortical compatível com laceração esplênica ativa. FAST POSITIVO."
                )
                is_positive_finding = True
            else:
                findings_desc = "Janela Esplenorrenal: Recesso de Koller sem coleções ou líquido livre visível."
        elif site_clean in ("pelvic", "efast_suprapubic_pelvic"):
            if is_trauma_fast:
                findings_desc = (
                    "Janela Pélvica / Suprapúbica: Presença de líquido livre anecoico acumulado no fundo de saco peritoneal posterior. FAST POSITIVO."
                )
                is_positive_finding = True
            else:
                findings_desc = "Janela Pélvica: Bexiga fisiologicamente preenchida, sem líquido livre em escavação pélvica."
        elif site_clean in ("pericardial", "efast_subxiphoid_pericardial"):
            findings_desc = (
                "Janela Subxifoide / Pericárdica: Espaço pericárdico virtual preservado, sem lâmina anecoica ou "
                "sinais de tamponamento cardíaco. Contratilidade ventricular preservada."
            )
        elif site_clean in ("pleural_right", "pleural_left"):
            is_right = "right" in site_clean
            findings_desc = (
                f"E-FAST Pleuropulmonar {'Direito' if is_right else 'Esquerdo'}: Deslizamento pleural ('lung sliding') presente, "
                "com linhas A fisiológicas e sinal da praia no Modo M. Ausência de pneumotórax neste hemitórax."
            )
        else:
            findings_desc = f"Varredura ultrassonográfica no sítio {anatomical_site}: Estruturas anatômicas avaliadas sem coleções agudas adicionais."

        examiner_message = f"Examinador entrega imagem do E-FAST: {findings_desc}"

    # 2. TORACOCENTESE DE ALÍVIO COM AGULHA & IATROGENIA DE BORDA DE COSTELA
    elif proc_type_clean in ("puncture", "thoracocentesis", "thoracocentesis_relief") or "thoracocentesis" in site_clean:
        if "inferior_border" in site_clean or "iatrogenic" in site_clean:
            findings_desc = (
                "IATROGENIA GRAVE: Agulha introduzida rente à BORDA INFERIOR da costela superior, "
                "lacerando a artéria intercostal! Observa-se saída de sangue vivo em jato pulsátil e piora hemodinâmica imediata (Hemotórax Iatrogênico)!"
            )
            is_positive_finding = False
        else:
            findings_desc = (
                "Descompressão torácica com Jelco calibroso na borda superior da costela! "
                "Ocorre escape audível e vigoroso de ar sob alta pressão (\"HISS\" audível)! "
                "A turgência jugular atenua e a expansão torácica melhora expressivamente."
            )
            is_positive_finding = True
        examiner_message = f"Procedimento de Toracocentese de Alívio: {findings_desc}"

    # 3. DRENAGEM TORÁCICA TUBULAR EM SELO D'ÁGUA
    elif proc_type_clean in ("drainage", "chest_tube", "chest_tube_insertion") or "chest_tube" in site_clean:
        findings_desc = (
            "Dreno torácico tubular 32 Fr introduzido no 5º EIC na linha axilar média (triângulo de segurança) "
            "e conectado a selo d'água. Dreno posicionado com sucesso e fixado com bailarina. "
            "Observa-se oscilação adequada da coluna d'água e drenagem gasosa/serossanguinolenta imediata."
        )
        examiner_message = f"Drenagem Torácica Fechada: {findings_desc}"
        is_positive_finding = True

    # 4. VIA AÉREA CIRÚRGICA / CRICOTIREOIDOSTOMIA
    elif proc_type_clean in ("cricothyroidotomy", "surgical_cricothyroidotomy") or "cricoid" in site_clean or "thyroid" in site_clean:
        if "thyroid_gland" in site_clean or "iatrogenic" in site_clean:
            findings_desc = (
                "IATROGENIA CRÍTICA: Incisão cirúrgica realizada ABAIXO da cartilagem cricoide sobre o istmo da tireoide! "
                "Hemorragia cervical maciça imediata inundando o campo cirúrgico e a traqueia!"
            )
            is_positive_finding = False
        else:
            findings_desc = (
                "Cricotireoidostomia cirúrgica de emergência executada com perfeição: incisão horizontal na membrana cricotireoidea, "
                "dilatação com pinça hemostática, introdução de tubo traqueal nº 6.0 e balonete insuflado. "
                "Ventilação mecânica restabelecida com expansão torácica bilateral simétrica!"
            )
            is_positive_finding = True
        examiner_message = f"Via Aérea Cirúrgica de Emergência: {findings_desc}"

    # 5. MANOBRA DE HAMILTON (COMPRESSÃO BIMANUAL UTERINA)
    elif proc_type_clean in ("maneuver", "hamilton") or "hamilton" in site_clean:
        is_hpp = "HPP" in station_code or "hemorragia" in sess["title"].lower() or "atonia" in sess["title"].lower()
        if is_hpp:
            findings_desc = (
                "Manobra de compressão bimanual de Hamilton iniciada imediatamente: punho cerrado no fundo de saco anterior "
                "da vagina contra a parede anterior uterina e mão abdominal tracionando o fundo para frente. "
                "O útero contrai parcialmente sob a compressão com redução do sangramento vaginal em jato."
            )
            is_positive_finding = True
        else:
            findings_desc = "Manobra executada conforme a técnica obstétrica padrão."
        examiner_message = f"Manobra Obstétrica Beira-Leito: {findings_desc}"

    # 6. CARDIOVERSÃO ELÉTRICA SINCRONIZADA
    elif proc_type_clean in ("cardioversion",) or "cardioversion" in site_clean:
        is_tv = "TV" in station_code or "taquicardia" in sess["title"].lower()
        if is_tv:
            findings_desc = (
                "Pás de desfibrilador posicionadas com gel (infraclavicular direita e ápice cardíaco). "
                "Modo sincronizado ATIVADO, flag nas ondas R confirmado. Sedação rápida administrada. "
                "A equipe afasta-se e o choque de 100 Joules é disparado! O monitor acusa reversão imediata para Ritmo Sinusal, "
                "FC 84 bpm, pulsos amplos e PA normalizada em 115x75 mmHg!"
            )
            is_positive_finding = True
        else:
            findings_desc = "Cardioversão sincronizada realizada com choque disparado na onda R."
        examiner_message = f"Cardioversão Elétrica Sincronizada: {findings_desc}"

    # 7. ACESSO VENOSO PROFUNDO / INTRAÓSSEO
    elif proc_type_clean in ("vascular", "intraosseous", "intraosseous_access", "central_line_insertion") or "intraosseous" in site_clean or "central_vein" in site_clean or "seldinger" in site_clean or "tibia" in site_clean:
        if "intraosseous" in site_clean or "tibia" in site_clean or proc_type_clean in ("intraosseous", "intraosseous_access"):
            findings_desc = (
                "Punção intraóssea realizada na tíbia proximal (2 cm abaixo e medial à tuberosidade tibial). "
                "Aspiração de medula óssea positiva e infusão livre de soro sem extravasamento. Via de emergência garantida."
            )
        else:
            findings_desc = (
                "Acesso venoso central obtido por punção de veia jugular interna direita sob técnica de Seldinger. "
                "Refluxo venoso escuro livre e infusão em fluxo rápido confirmada."
            )
        examiner_message = f"Acesso Vascular de Urgência: {findings_desc}"
        is_positive_finding = True

    # OUTROS PROCEDIMENTOS
    else:
        findings_desc = f"Procedimento ({procedure_type} no sítio {anatomical_site}) realizado com sucesso pela técnica asséptica beira-leito."
        examiner_message = f"Procedimento Beira-Leito Realizado: {findings_desc}"

    action_record = {
        "action_type": "procedure",
        "procedure_type": procedure_type,
        "anatomical_site": anatomical_site,
        "findings": findings_desc,
        "is_positive": is_positive_finding,
        "elapsed_seconds": elapsed_seconds,
        "timestamp": now_iso
    }

    spoken_queue: list[dict[str, str]] = [
        {"speaker": "examinador", "text": examiner_message}
    ]

    transcript_entry = {
        "sender": "examinador",
        "message": examiner_message,
        "timestamp": now_iso,
        "elapsed_seconds": elapsed_seconds,
        "action_payload": {
            "type": "procedure",
            "procedure_type": procedure_type,
            "anatomical_site": anatomical_site,
            "findings": findings_desc,
            "image_url": image_url
        }
    }

    latest_transcript, latest_actions = _append_osce_session_entries(
        db,
        session_id,
        user_id,
        new_transcript=[transcript_entry],
        new_actions=[action_record],
        elapsed_seconds=elapsed_seconds,
    )

    res_proc: dict[str, Any] = {
        "success": True,
        "procedure_type": procedure_type,
        "anatomical_site": anatomical_site,
        "findings": findings_desc,
        "is_positive": is_positive_finding,
        "examiner_message": examiner_message,
        "spoken_queue": spoken_queue,
        "elapsed_seconds": elapsed_seconds
    }

    if get_session_mode(latest_actions) == "guided":
        barema_raw = json.loads(sess["checklist_barema_json"] or "{}")
        c_items = barema_raw.get("items", []) if isinstance(barema_raw, dict) else (barema_raw if isinstance(barema_raw, list) else [])
        res_proc["guided_feedback"] = evaluate_live_barema_progress(
            c_items, latest_transcript, latest_actions, elapsed_seconds, int(sess["duration_seconds"] or 480)
        )

    return res_proc


