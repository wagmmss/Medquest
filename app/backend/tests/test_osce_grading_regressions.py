"""Testes de regressão para auditoria e correção do motor de avaliação do OSCE (Bloco 0)."""
from __future__ import annotations

from api import osce
from api.db import get_db
from api.osce_data import CANONICAL_STATIONS
from api.osce_evaluation import _normalize_text, evaluate_critical_safety_violations


def _start_station_by_code(db, code: str, user_id: str = "test_reg_user", mode: str = "blind") -> str:
    osce.seed_osce_stations(db)
    station = db.execute("SELECT id FROM osce_stations WHERE code = ?", (code,)).fetchone()
    assert station is not None, f"Estação {code} não encontrada"
    session = osce.start_osce_session(db, station["id"], user_id, mode=mode)
    return session["session_id"]


def test_spikes_all_refused_scores_at_most_one(app):
    """SPIKES com todas as condutas recusadas deve dar no máximo 1/10."""
    with app.app_context():
        db = get_db()
        user_id = "reg_spikes_user"
        session_id = _start_station_by_code(db, "UNIFESP-2023-PREV-SPIKES", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Não vou garantir privacidade nem chamar acompanhante, "
                "não quero saber a percepção dele nem se gostaria de saber detalhes, "
                "não faço aviso prévio de câncer em linguagem simples, "
                "não vou acolher em silêncio e não faço encaminhamento para oncologia."
            ),
        )
        assert res["final_score"] <= 1.0


def test_cad_negated_potassium_zeros_potassium_item(app):
    """CAD com negação explícita de potássio/KCl deve zerar o item de manejo do potássio."""
    with app.app_context():
        db = get_db()
        user_id = "reg_cad_neg_k"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Expansão com soro fisiológico 1000 ml na primeira hora. "
                "Não vou repor potássio nem usar KCl ou cloreto de potássio."
            ),
        )
        item_4 = next(it for it in res["evaluated_items"] if it.get("id") == "item_4")
        assert item_4["awarded_score"] == 0.0
        assert item_4["status"] == "NONE"


def test_cad_paraphrased_conduct_does_not_trigger_false_potassium_critical_error(app):
    """CAD com menção parafraseada de calemia/ionograma antes da insulina não pode disparar erro de K+."""
    with app.app_context():
        db = get_db()
        user_id = "reg_cad_para_k"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Verifiquei o ionograma e a calemia sérica (4,2 mEq/L) antes de iniciar insulina regular "
                "em bomba de infusão contínua e hidratação com soro fisiológico."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert not ("potássio" in txt or "potassio" in txt or "hipocalemia" in txt)


def test_queda_estado_geral_does_not_trigger_endoscopy_error(app):
    """'Queda do estado geral' não pode casar substring com 'eda' e disparar erro de endoscopia."""
    with app.app_context():
        db = get_db()
        user_id = "reg_queda_eda"
        session_id = _start_station_by_code(db, "UNICAMP-2023-CG-PERF", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Paciente com queda do estado geral e abdome em tábua por úlcera perfurada. "
                "Indico laparotomia exploradora de urgência, jejum, hidratação e antibiótico."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert "endoscopia" not in txt and "eda" not in txt


def test_polytrauma_negated_ct_not_penalized(app):
    """Politrauma dizendo 'não levar para tomografia' não pode ser punido por pedir tomografia."""
    with app.app_context():
        db = get_db()
        user_id = "reg_fast_no_ct"
        session_id = _start_station_by_code(db, "USP-RP-2023-CG-FAST", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Paciente instável com FAST positivo e hemoperitônio. "
                "Não levar para tomografia computadorizada, indico laparotomia exploradora imediata, "
                "ácido tranexâmico e transfusão maciça 1:1:1."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert "tomografia" not in txt


def test_sexual_violence_requiring_bo_triggers_critical_error_and_zeros_welcoming(app):
    """Exigir BO em violência sexual deve disparar erro crítico e zerar o acolhimento."""
    with app.app_context():
        db = get_db()
        user_id = "reg_pep_bo"
        session_id = _start_station_by_code(db, "REVALIDA-2023-GO-PEP", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes="Exijo o boletim de ocorrência policial como condição antes de realizar o atendimento médico.",
        )
        assert any("boletim de ocorrência" in str(rf.get("description", "")).lower() for rf in res["red_flags_triggered"])
        item_1 = next(it for it in res["evaluated_items"] if it.get("id") == "item_1")
        assert item_1["awarded_score"] == 0.0


def test_prescription_pad_only_scores_checklist_items(app):
    """Prescrição feita só na prancheta deve pontuar na nota final igual ao modo guiado."""
    with app.app_context():
        db = get_db()
        user_id = "reg_pad_only"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id, mode="guided")
        osce.prescribe_osce_drugs(
            db,
            session_id,
            user_id,
            [
                {
                    "drug_name": "Soro Fisiológico 0,9%",
                    "dose": "1000",
                    "unit": "ml",
                    "route": "EV",
                    "notes": "expansão na primeira hora",
                },
                {
                    "drug_name": "Cloreto de Potássio",
                    "dose": "20",
                    "unit": "mEq",
                    "route": "EV",
                    "notes": "repor potássio por litro de soro",
                },
                {
                    "drug_name": "Insulina Regular",
                    "dose": "0,1",
                    "unit": "U/kg/h",
                    "route": "EV",
                    "notes": "bomba de infusão contínua",
                },
            ],
            elapsed_seconds=120,
        )
        live = osce.get_osce_live_feedback(db, session_id, user_id, 120)
        fin = osce.finish_osce_session(db, session_id, user_id, conduct_notes="")
        assert fin["raw_score"] >= 5.0
        assert fin["raw_score"] == live["current_score"]


def test_empty_session_honest_radar_and_review(app):
    """Estação encerrada vazia deve gerar nota 0, radar sem números inventados e parecer sem elogios."""
    with app.app_context():
        db = get_db()
        user_id = "reg_empty_sess"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(db, session_id, user_id, conduct_notes="")
        assert res["final_score"] == 0.0
        assert res["competency_radar_5d"]["communication_empathy"] in (None, 0.0)
        assert res["competency_radar_5d"]["sus_time_efficiency"] == 0.0
        assert all(d["percentage"] in (None, 0.0) for d in res["competency_radar"]["dimensions"])
        assert res["chief_preceptor_review"]["what_went_well"] == []
        assert all(it["timestamp_achieved_sec"] is None for it in res["evaluated_items"])
        assert "Kussmaul" in res["chief_preceptor_review"]["gold_standard_canonical_conduct"]

        # Sessão exemplar 10/10 na mesma estação deve gerar parecer e forças distintos
        sess_gold = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id="reg_gold_sess")
        osce.execute_osce_action(db, sess_gold, "reg_gold_sess", "lab_imaging", "gasometria_eletrólitos", 30)
        res_gold = osce.finish_osce_session(
            db,
            sess_gold,
            "reg_gold_sess",
            conduct_notes=(
                "Paciente com respiração de Kussmaul, hálito cetônico e torpor. "
                "Diagnóstico de cetoacidose diabética grave com acidose metabólica e ânion gap elevado. "
                "Prescrevo soro fisiológico 0,9% 1000 ml na primeira hora para expansão. "
                "Avaliei potássio e prescrevo repor potássio com cloreto de potássio 20 mEq por litro. "
                "Inicio insulina regular em bomba de infusão contínua 0,1 U/kg/h. "
                "Quando atingir glicemia de 250 mg/dL, associar soro glicosado SG 5% para fechar ânion gap."
            ),
        )
        assert res_gold["final_score"] == 10.0
        assert len(res_gold["chief_preceptor_review"]["what_went_well"]) == 3
        assert res_gold["chief_preceptor_review"]["executive_summary"] != res["chief_preceptor_review"]["executive_summary"]
        assert res_gold["chief_preceptor_review"]["critical_corrections"] == []


def _build_trigger_phrase_for_error(err: str) -> str:
    """Constrói frase representativa de violação para testar cobertura determinística de cada erro crítico."""
    e = _normalize_text(err)
    if "bicarbonato" in e:
        return "Prescrevo bicarbonato de sódio venoso para corrigir o pH."
    if "potassio" in e and "insulina" in e:
        return "Inicio insulina regular em bomba imediatamente."
    if "suspender" in e and "insulina" in e:
        return "Vou suspender insulina assim que a glicemia baixar."
    if "trombolitico" in e or "fibrinolitico" in e:
        return "Prescrevo alteplase para trombólise química."
    if "estrategia invasiva" in e:
        return "Não indico cateterismo nem estratégia invasiva, sigo tratamento conservador exclusivo."
    if "tomografia" in e and ("instavel" in e or "fast" in e):
        return "Encaminho paciente para tomografia computadorizada agora."
    if "2 litros" in e or "coagulopatia dilucional" in e:
        return "Realizo ressuscitação agressiva com 3 litros de soro fisiológico."
    if ("corticosteroide" in e or "cortico" in e) and "bronquiolite" in e:
        return "Prescrevo prednisolona oral para esta bronquiolite."
    if ("antibiotico" in e or "antimicrobiano" in e) and ("bronquiolite" in e or "quadro viral" in e or "diarreia aquosa" in e):
        return "Prescrevo amoxicilina de rotina."
    if "alta" in e and ("hipoxemia" in e or "observacao" in e):
        return "Vou dar alta hospitalar para casa agora."
    if "hamilton" in e or "massagem bimanual" in e:
        return "Não realizo massagem bimanual nem manobra de Hamilton."
    if "atrasar" in e and "uterotonico" in e:
        return "Vou aguardar exames antes da ocitocina e não administro uterotônico agora."
    if "tudo psicologico" in e or "desmerecer" in e:
        return "Isso é tudo psicológico, a senhora não tem nada."
    if "bateria excessiva" in e or "prevencao quaternaria" in e:
        return "Solicito bateria de exames e tomografia de corpo inteiro."
    if "benzodiazepinico" in e or "polifarmacia" in e:
        return "Prescrevo clonazepam de uso contínuo."
    if "aguardar" in e and "troponina" in e:
        return "Vou aguardar troponina antes de definir reperfusão."
    if "nitrato" in e:
        return "Prescrevo isordil sublingual imediatamente."
    if "oxigenioterapia" in e:
        return "Prescrevo cateter de O2 de rotina para a paciente."
    if "nao indicar cirurgia" in e:
        return "Não indico cirurgia, vou manter tratamento conservador."
    if "endoscopia" in e or "eda" in e:
        return "Solicito endoscopia digestiva alta imediata."
    if ("corticoide" in e or "anti-histaminico" in e) and "adrenalina" in e:
        return "Prescrevo hidrocortisona e prometazina apenas."
    if "adrenalina" in e and ("subcutanea" in e or "intravenosa pura" in e):
        return "Administro adrenalina subcutânea agora."
    if "nao prescrever sulfato" in e:
        return "Não vou prescrever sulfato de magnésio neste caso."
    if "diazepam" in e or "fenitoina" in e:
        return "Prescrevo diazepam e fenitoína para profilaxia de convulsão."
    if "reduzir abruptamente" in e or "120 mmhg" in e:
        return "Vou reduzir abruptamente a PA para valores menores que 120 mmHg."
    if "abrupta" in e or "em pe" in e:
        return "Comunico em pé no corredor de forma abrupta sem aviso prévio."
    if "jargoes" in e or "adenocarcinoma" in e:
        return "Você tem adenocarcinoma invasivo moderadamente diferenciado."
    if "nao ha nada a fazer" in e:
        return "Infelizmente não há nada a fazer neste caso."
    if "amiodarona" in e:
        return "Administro amiodarona 300 mg venosa antes do choque."
    if "sincronizacao" in e:
        return "Vou chocar sem sincronizar com desfibrilação imediata."
    if "atrasar o antibiotico" in e:
        return "Vou esperar hemocultura sair antes de iniciar antibiótico."
    if "dopamina" in e:
        return "Inicio dopamina em bomba como vasopressor inicial."
    if ("radiografia" in e or "tomografia" in e) and "pneumotorax" in e:
        return "Solicito radiografia de tórax antes de descomprimir."
    if "intubacao" in e and "descomprimir" in e:
        return "Vou intubar antes de descomprimir o tórax."
    if "plano a ou b" in e or "reidratacao oral" in e:
        return "Vou manter apenas terapia de reidratação oral pelo Plano B."
    if "boletim de ocorrencia" in e:
        return "Exijo o boletim de ocorrência para atender a paciente."
    if "nao prescrever a profilaxia de hiv" in e:
        return "Não vou prescrever PEP nem profilaxia de HIV."
    return ""


def test_all_canonical_critical_errors_have_working_detection_rule():
    """Todo erro crítico cadastrado em CANONICAL_STATIONS deve possuir uma regra capaz de detectá-lo."""
    assert len(CANONICAL_STATIONS) >= 16
    for station in CANONICAL_STATIONS:
        for err in station.get("critical_errors", []):
            phrase = _build_trigger_phrase_for_error(err)
            assert phrase, f"Sem frase de disparo definida para [{station['code']}] {err}"
            detected = evaluate_critical_safety_violations([err], phrase, [], station)
            assert detected == [err], (
                f"Erro crítico sem regra funcional em {station['code']}: '{err}' (frase='{phrase}')"
            )
