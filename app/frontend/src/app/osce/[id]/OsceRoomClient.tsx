"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import {
  Stethoscope, FileText,
  Volume2, VolumeX,
  ChevronRight, Lock, AlertTriangle,
  Radio, Headphones, Zap, CheckCircle2, Lightbulb
} from "lucide-react";
import { toast } from "react-hot-toast";
import { OsceStationDetail, OsceTranscriptItem, OsceFinishResponse, OsceSpokenQueueItem, OsceLiveFeedback, OsceTaskProgress } from "@/types/api";
import { api } from "@/lib/api";
import { useVitalStateStore, useVitalSnapshot, VitalStateStore } from "./useVitalStateEngine";
import { useOsceAudio } from "./useOsceAudio";
import { SessionTimer } from "@/components/ui/SessionTimer";
import { OsceDoorBriefing } from "./OsceDoorBriefing";
import { OsceFinishView } from "./OsceFinishView";

const GhostPreceptorHUD = dynamic(
  () => import("./GhostPreceptorHUD").then((m) => m.GhostPreceptorHUD),
  { ssr: false }
);
const ClinicalStage = dynamic(
  () => import("./ClinicalStage").then((m) => m.ClinicalStage),
  { ssr: false }
);
const PrescriptionPad = dynamic(
  () => import("./PrescriptionPad").then((m) => m.PrescriptionPad),
  { ssr: false }
);
const ProcedureMannequin = dynamic(
  () => import("./ProcedureMannequin").then((m) => m.ProcedureMannequin),
  { ssr: false }
);
const MultiparameterMonitor = dynamic(
  () => import("./MultiparameterMonitor").then((m) => m.MultiparameterMonitor),
  { ssr: false }
);

interface OsceRoomClientProps {
  station: OsceStationDetail;
  circuitId?: string;
  step?: number;
}

function LiveMultiparameterMonitor({ store }: { store: VitalStateStore }) {
  const snap = useVitalSnapshot(store);
  return (
    <MultiparameterMonitor
      vitals={snap.vitals}
      isMonitored={snap.isMonitored}
      displayedNibp={snap.displayedNibp}
      isMeasuringNibp={snap.isMeasuringNibp}
      activeAlarms={snap.activeAlarms}
      isAlarmSilenced={snap.isAlarmSilenced}
      isAudioMuted={snap.isAudioMuted}
      onMeasureNibp={store.measureNibp}
      onConnectSensors={store.connectSensors}
      onSilenceAlarms={store.silenceAlarms}
      onToggleAudio={store.toggleAudio}
      onExecuteCardioversion={store.executeCardioversion}
    />
  );
}

function LivePhysicalVitalsCard({
  store,
  fallbackVitals,
}: {
  store: VitalStateStore;
  fallbackVitals: Record<string, string> | null;
}) {
  const snap = useVitalSnapshot(store);
  if (!fallbackVitals && !snap.isMonitored.ecg && !snap.displayedNibp) {
    return null;
  }
  return (
    <div className="grid grid-cols-3 gap-2 p-3 rounded-xl bg-muted/20 border border-border font-mono text-[11px]">
      <div>
        PA:{" "}
        <span className="font-bold text-foreground">
          {snap.displayedNibp
            ? `${snap.displayedNibp.sbp}x${snap.displayedNibp.dbp}`
            : snap.isMeasuringNibp
            ? "Aferindo..."
            : fallbackVitals?.pa || "--/--"}
        </span>
      </div>
      <div>
        FC:{" "}
        <span className="font-bold text-emerald-500">
          {snap.isMonitored.ecg ? `${snap.vitals.hr} bpm` : fallbackVitals?.fc || "--"}
        </span>
      </div>
      <div>
        FR:{" "}
        <span className="font-bold text-foreground">
          {snap.vitals.rr} irpm
        </span>
      </div>
      <div>
        SatO2:{" "}
        <span className="font-bold text-cyan-500">
          {snap.isMonitored.spo2 ? `${snap.vitals.spo2}%` : fallbackVitals?.sato2 || "--"}
        </span>
      </div>
      <div>
        Temp:{" "}
        <span className="font-bold text-foreground">
          {snap.vitals.temp || 36.5} °C
        </span>
      </div>
      <div>
        Ritmo:{" "}
        <span className="font-bold text-emerald-500 truncate block text-[10px]">
          {snap.vitals.rhythm}
        </span>
      </div>
    </div>
  );
}

export function OsceRoomClient({ station, circuitId, step = 1 }: OsceRoomClientProps) {
  const router = useRouter();

  // Fases: 'door' (porta da estação) | 'exam' (sala de exame) | 'finished' (espelho da banca)
  const [phase, setPhase] = useState<"door" | "exam" | "finished">("door");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const defaultDuration = station.duration_seconds || 480;
  const [examTiming, setExamTiming] = useState<{ duration: number; deadlineAt: number }>({
    duration: defaultDuration,
    deadlineAt: 0,
  });
  const examTimingRef = useRef(examTiming);
  const [finalElapsedSeconds, setFinalElapsedSeconds] = useState(0);
  const [transcript, setTranscript] = useState<OsceTranscriptItem[]>([]);
  const [inputText, setInputText] = useState("");
  const [conductText, setConductText] = useState("");
  const [activeTab, setActiveTab] = useState<"physical" | "procedures" | "labs" | "conduct">("physical");
  const [vitals, setVitals] = useState<Record<string, string> | null>(null);
  const [selectedExam, setSelectedExam] = useState<{ title: string; image_url?: string; result_text?: string } | null>(null);
  const [physicalInput, setPhysicalInput] = useState("");
  const [labInput, setLabInput] = useState("");
  const [requestedPhysicalExams, setRequestedPhysicalExams] = useState<Array<{ target: string; finding: string }>>([]);
  const [requestedLabs, setRequestedLabs] = useState<Array<{ title: string; result_text: string; image_url?: string }>>([]);
  const [taskProgress, setTaskProgress] = useState<OsceTaskProgress>(() => {
    const initialTasks = station.tasks || [];
    return {
      total_steps: initialTasks.length,
      completed_steps: [],
      current_step: 1,
      all_completed: false,
      visible_tasks: initialTasks,
    };
  });
  const [report, setReport] = useState<OsceFinishResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const getElapsedSeconds = useCallback(() => {
    const { duration, deadlineAt } = examTimingRef.current;
    if (deadlineAt <= 0) return 0;
    const remaining = Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000));
    return Math.max(0, duration - remaining);
  }, []);

  // Estados do Modo Duplo (Prova Cega padrão vs Treino Guiado com Preceptor Fantasma)
  const [selectedMode, setSelectedMode] = useState<"blind" | "guided">("blind");
  const [sessionMode, setSessionMode] = useState<"blind" | "guided">("blind");
  const [liveFeedback, setLiveFeedback] = useState<OsceLiveFeedback | null>(null);
  const neutralStationLabel = `${station.area} · ${station.institution} · Estação #${station.id}`;
  const stationKind = station.station_kind || "emergencia";
  const showMonitor = stationKind === "emergencia" || stationKind === "procedimento";
  const showMannequin = stationKind === "emergencia" || stationKind === "procedimento";
  const showPrescriptionPad = stationKind === "emergencia" || stationKind === "procedimento";

  const quickVoiceSuggestions = useMemo(() => {
    const patientFirstName = station.patient_persona.name?.split(" ")[0] || "senhor(a)";
    if (stationKind === "comunicacao") {
      return [
        { label: "“Como você está hoje?”", message: `Olá ${patientFirstName}, como você está se sentindo hoje?` },
        { label: "“O que já sabe?”", message: "O que você já sabe até agora sobre o motivo dos seus exames?" },
        { label: "“Posso explicar com calma?”", message: "Você gostaria que eu explicasse o resultado com calma e detalhes agora?" },
        { label: "“Estou aqui com você”", message: "Entendo o quanto isso é difícil. Estou aqui para responder tudo e planejar os próximos passos juntos." },
      ];
    }
    if (stationKind === "ambulatorio") {
      return [
        { label: "“Como posso ajudar?”", message: `Olá ${patientFirstName}, acolho sua queixa. Me conte com calma o que aconteceu.` },
        { label: "“Inspeção geral”", message: "Examinador, solicito inspeção geral e sinais vitais." },
        { label: "“História prévia”", message: "Você usa algum medicamento contínuo ou tem alergias?" },
        { label: "“Orientação e seguimento”", message: "Vou orientar os exames, medidas de proteção e o retorno ambulatorial." },
      ];
    }
    if (stationKind === "procedimento") {
      return [
        { label: "“Examinador, sinais vitais”", message: "Examinador, solicito sinais vitais completos e monitorização." },
        { label: "“Avaliação primária ABCDE”", message: "Realizo avaliação primária ABCDE e checo via aérea e ventilação." },
        { label: "“Exame focado à beira do leito”", message: "Realizo janela de E-FAST / inspeção direcionada ao foco do quadro." },
        { label: "“Gasometria e lactato”", message: "Examinador, solicito gasometria arterial e lactato sérico." },
      ];
    }
    return [
      { label: "“Examinador, sinais vitais”", message: "Examinador, solicito sinais vitais completos e PA" },
      { label: "“Solicito ECG 12d”", message: "Examinador, solicito eletrocardiograma de 12 derivações" },
      { label: "“Ausculta pulmonar”", message: "Gostaria de realizar ausculta cardíaca e pulmonar" },
      { label: "“Onde começou a dor?”", message: `Olá ${patientFirstName}, onde começou essa dor e como ela é?` },
    ];
  }, [stationKind, station.patient_persona.name]);

  // Motor Fisiológico Dinâmico Beira-Leito (isolado via external store para evitar re-render 1Hz da sala inteira)
  const vitalStore = useVitalStateStore({
    initialConfig: station.physiology_engine,
    fallbackVitals: vitals,
    getElapsedSeconds,
    isActive: phase === "exam",
  });

  const getAuscultationVitals = useCallback(
    () => vitalStore.getSnapshot().vitals,
    [vitalStore]
  );

  // Estados do Circuito Oficial de 5 Estações
  const [circuitPlan, setCircuitPlan] = useState<import("@/types/api").OsceCircuitPlanResponse | null>(null);
  const [circuitSummary, setCircuitSummary] = useState<import("@/types/api").OsceCircuitSummaryResponse | null>(null);
  const [showCircuitModal, setShowCircuitModal] = useState(false);
  const [isLoadingCircuit, setIsLoadingCircuit] = useState(false);

  useEffect(() => {
    if (!circuitId) return;
    api.osce.getCircuitPlan(station.institution || "USP-RP")
      .then((plan) => {
        if (plan) setCircuitPlan(plan);
      })
      .catch(() => {});
  }, [circuitId, station.institution]);

  const handleAdvanceCircuit = () => {
    if (!circuitPlan?.stations) {
      router.push("/osce");
      return;
    }
    const nextItem = circuitPlan.stations.find((s) => s.step === step + 1);
    if (nextItem) {
      router.push(`/osce/${nextItem.station_id}?circuit=${circuitId}&step=${step + 1}`);
    } else {
      router.push("/osce");
    }
  };

  const handleOpenCircuitSummary = async () => {
    if (!circuitId) return;
    setIsLoadingCircuit(true);
    try {
      const summary = await api.osce.getCircuitSummary(circuitId);
      if (summary) {
        setCircuitSummary(summary);
        setShowCircuitModal(true);
      }
    } catch {
      toast.error("Erro ao carregar parecer global do circuito.");
    } finally {
      setIsLoadingCircuit(false);
    }
  };

  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const startingRef = useRef(false);
  const finishingRef = useRef(false);
  const handleDispatchSpeechRef = useRef<(spokenText: string) => Promise<void>>(async () => {});
  const dispatchSpeechViaRef = useCallback(
    (spokenText: string) => handleDispatchSpeechRef.current(spokenText),
    []
  );

  const {
    voiceEnabled,
    setVoiceEnabled,
    isListening,
    handsFreeMode,
    interimSpeechText,
    setInterimSpeechText,
    activeSpeaker,
    micPermission,
    micErrorMsg,
    playExamBell,
    stopRecognition,
    speakSpokenQueue,
    cancelSpeechSynthesis,
    requestMicrophonePermission,
    startListening,
    toggleHandsFreeMode,
    toggleListening,
    resumeAfterSpeechFailure,
  } = useOsceAudio({
    phase,
    patientGender: station.patient_persona.gender,
    isLoading,
    onDispatchSpeech: dispatchSpeechViaRef,
  });

  // Autoscroll no transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  // Dispatcher Unificado de Voz (Modo Hands-Free)
  const handleDispatchSpeech = useCallback(async (spokenText: string) => {
    const text = spokenText.trim();
    if (!text || !sessionId || isLoading) return;

    const elapsed = getElapsedSeconds();
    setIsLoading(true);
    setInterimSpeechText("");

    // Adiciona fala otimista no transcript
    setTranscript((prev) => [
      ...prev,
      {
        sender: "candidato",
        message: text,
        timestamp: new Date().toISOString(),
        elapsed_seconds: elapsed
      }
    ]);

    try {
      const res = await api.osce.dispatchSpeech(sessionId, text, elapsed);

      if (res.guided_feedback) {
        setLiveFeedback(res.guided_feedback);
      }

      if (res.transcript && res.transcript.length > 0) {
        setTranscript(res.transcript);
      }

      if (res.actions_executed && res.actions_executed.length > 0) {
        for (const act of res.actions_executed) {
          if (act.action_type === "vitals" && act.payload?.vitals) {
            setVitals(act.payload.vitals as Record<string, string>);
          }
          if (act.action_type === "lab_imaging" && act.payload?.title) {
            const examObj = {
              title: String(act.payload.title),
              image_url: act.payload.image_url ? String(act.payload.image_url) : undefined,
              result_text: act.payload.result_text ? String(act.payload.result_text) : undefined
            };
            setSelectedExam(examObj);
            setRequestedLabs((prev) => [...prev, { title: examObj.title, result_text: examObj.result_text || "Normal / não disponível.", image_url: examObj.image_url }]);
            setActiveTab("labs");
          }
          if (act.action_type === "physical_exam") {
            const findingStr = String(act.payload?.finding || act.examiner_message || "Sem alterações.");
            setRequestedPhysicalExams((prev) => [...prev, { target: String(act.target || "Exame Físico"), finding: findingStr }]);
            setActiveTab("physical");
          }
          if (act.action_type === "procedure") {
            setActiveTab("procedures");
          }
          if (act.action_type === "prescription") {
            setActiveTab("conduct");
          }
        }
      }

      if (res.spoken_queue && res.spoken_queue.length > 0) {
        speakSpokenQueue(res.spoken_queue);
      } else {
        resumeAfterSpeechFailure();
      }
    } catch (err) {
      console.error("Falha no speech dispatcher:", err);
      resumeAfterSpeechFailure();
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, isLoading, getElapsedSeconds, setInterimSpeechText, speakSpokenQueue, resumeAfterSpeechFailure]);

  // Sincroniza ref para chamadas livres de ciclo
  useEffect(() => {
    handleDispatchSpeechRef.current = handleDispatchSpeech;
  }, [handleDispatchSpeech]);

  // Iniciar sessão
  const handleStartExam = async () => {
    if (startingRef.current || isLoading) return;
    startingRef.current = true;
    finishingRef.current = false;
    setIsLoading(true);
    try {
      const res = await api.osce.startSession(station.id, circuitId, selectedMode);
      setSessionId(res.session_id);
      setSessionMode(res.mode || selectedMode);
      if (res.guided_feedback) {
        setLiveFeedback(res.guided_feedback);
      }
      if (res.task_progress) {
        setTaskProgress(res.task_progress);
      }
      setTranscript(res.transcript || []);
      const duration = res.duration_seconds || 480;
      const nextTiming = { duration, deadlineAt: Date.now() + duration * 1000 };
      examTimingRef.current = nextTiming;
      setExamTiming(nextTiming);
      setPhase("exam");
      playExamBell("start");

      // Anúncio do Examinador
      const introQueue: OsceSpokenQueueItem[] = [
        {
          speaker: "examinador",
          text: "Candidato, pode entrar na sala de exame. Seu tempo de prova começou."
        }
      ];

      if (voiceEnabled) {
        speakSpokenQueue(introQueue);
      } else if (handsFreeMode) {
        setTimeout(() => startListening(false), 500);
      }
    } catch (err) {
      console.error("Falha ao iniciar estação:", err);
      toast.error("Não foi possível iniciar a estação OSCE. Tente novamente.");
    } finally {
      startingRef.current = false;
      setIsLoading(false);
    }
  };

  // Finalizar sessão
  const handleCompleteCurrentTask = async () => {
    if (!sessionId || isLoading || taskProgress.all_completed || taskProgress.total_steps === 0) return;
    const elapsed = getElapsedSeconds();
    setIsLoading(true);
    try {
      const res = await api.osce.executeAction(
        sessionId,
        "complete_task",
        String(taskProgress.current_step),
        elapsed
      );
      const nextProg = res.payload?.task_progress as OsceTaskProgress | undefined;
      if (nextProg) {
        setTaskProgress(nextProg);
      }
      setTranscript((prev) => [
        ...prev,
        {
          sender: "examinador",
          message: res.examiner_message,
          timestamp: new Date().toISOString(),
          elapsed_seconds: elapsed,
          action_payload: res.payload,
        },
      ]);
    } catch {
      toast.error("Não foi possível avançar para a próxima tarefa.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFinishExam = useCallback(async () => {
    if (!sessionId || finishingRef.current) return;
    finishingRef.current = true;
    setFinalElapsedSeconds(getElapsedSeconds());
    stopRecognition();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setIsLoading(true);
    playExamBell("finish");

    try {
      const res = await api.osce.finishSession(sessionId, conductText);
      setReport(res);
      setPhase("finished");
    } catch (err) {
      finishingRef.current = false;
      console.error("Erro ao finalizar sessão:", err);
      toast.error("Não foi possível finalizar a avaliação da estação. Tente novamente.");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, conductText, getElapsedSeconds, playExamBell, stopRecognition]);

  const timerMilestones = useMemo(() => {
    const midWarningSeconds = Math.round(examTiming.duration * 0.375);
    const map: Record<number, () => void> = {
      60: () => {
        playExamBell("warning");
        toast("Atenção: Falta 1 minuto para o término da estação! Conclua suas condutas e prescrição.", {
          duration: 6000
        });
        if (voiceEnabled) {
          speakSpokenQueue([
            {
              speaker: "examinador",
              text: "Atenção candidato: resta um minuto para o encerramento da estação. Conclua sua conduta."
            }
          ]);
        }
      },
    };
    if (midWarningSeconds > 60) {
      map[midWarningSeconds] = () => playExamBell("warning");
    }
    return map;
  }, [examTiming.duration, playExamBell, voiceEnabled, speakSpokenQueue]);

  // Listener de atalhos de teclado: Abas (Alt+1..4), Microfone (Alt+M / Espaço) e Silenciar (Escape)
  useEffect(() => {
    if (phase !== "exam") return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Atalhos com tecla Alt: navegação ultrarrápida entre abas da estação
      if (e.altKey && !e.ctrlKey && !e.shiftKey) {
        if (e.key === "1") {
          e.preventDefault();
          setActiveTab("physical");
          return;
        }
        if (e.key === "2" && showMannequin) {
          e.preventDefault();
          setActiveTab("procedures");
          return;
        }
        if (e.key === "3") {
          e.preventDefault();
          setActiveTab("labs");
          return;
        }
        if (e.key === "4") {
          e.preventDefault();
          setActiveTab("conduct");
          return;
        }
        if (e.key.toLowerCase() === "m") {
          e.preventDefault();
          toggleHandsFreeMode();
          return;
        }
      }

      if (e.key === "Escape") {
        cancelSpeechSynthesis();
      }
      // Barra de espaço fora de inputs aciona o microfone
      if (e.code === "Space" && e.target instanceof HTMLElement && !["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
        e.preventDefault();
        if (isListening) {
          stopRecognition();
        } else {
          startListening(true);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [phase, isListening, startListening, stopRecognition, setActiveTab, toggleHandsFreeMode, cancelSpeechSynthesis, showMannequin]);

  // Enviar mensagem manual por texto ou clique
  const handleSendMessage = async (msgToSend?: string, targetOverride?: "PATIENT" | "EXAMINER") => {
    const text = (msgToSend || inputText).trim();
    if (!text || !sessionId || isLoading) return;

    setInputText("");
    if (targetOverride) {
      const elapsed = getElapsedSeconds();
      setIsLoading(true);
      setTranscript((prev) => [
        ...prev,
        {
          sender: "candidato",
          message: text,
          timestamp: new Date().toISOString(),
          elapsed_seconds: elapsed,
          target: targetOverride.toLowerCase()
        }
      ]);

      try {
        const res = await api.osce.interact(sessionId, text, elapsed, targetOverride, vitalStore.getSnapshot().vitals);
        if (res.guided_feedback) {
          setLiveFeedback(res.guided_feedback);
        }
        setTranscript((prev) => [
          ...prev,
          {
            sender: res.sender as ("paciente" | "examinador"),
            message: res.reply,
            timestamp: new Date().toISOString(),
            elapsed_seconds: elapsed
          }
        ]);
        if (voiceEnabled) {
          speakSpokenQueue([
            {
              speaker: res.sender as ("paciente" | "examinador"),
              text: res.reply
            }
          ]);
        }
      } catch (err) {
        console.error("Erro ao enviar mensagem pelo palco clínico:", err);
      } finally {
        setIsLoading(false);
      }
    } else {
      await handleDispatchSpeech(text);
    }
  };

  // Solicitar Ação Clínica (Exame Físico / Sinais Vitais / Exames)
  const handleClinicalAction = async (actionType: "physical_exam" | "vitals" | "lab_imaging", target: string) => {
    if (!sessionId || isLoading) return;
    const elapsed = getElapsedSeconds();
    setIsLoading(true);

    try {
      const res = await api.osce.executeAction(sessionId, actionType, target, elapsed);
      
      if (res.guided_feedback) {
        setLiveFeedback(res.guided_feedback);
      }

      setTranscript((prev) => [
        ...prev,
        {
          sender: "examinador",
          message: res.examiner_message,
          timestamp: new Date().toISOString(),
          elapsed_seconds: elapsed,
          action_payload: res.payload
        }
      ]);

      if (actionType === "vitals") {
        vitalStore.connectSensors(["all"]);
        vitalStore.measureNibp();
        if (res.payload.vitals) {
          setVitals(res.payload.vitals as Record<string, string>);
        }
      }
      if (actionType === "physical_exam") {
        const findingStr = String(res.payload?.finding || res.examiner_message || "Sem alterações.");
        setRequestedPhysicalExams((prev) => [...prev, { target, finding: findingStr }]);
        setPhysicalInput("");
      }
      if (actionType === "lab_imaging" && res.payload.title) {
        const examObj = {
          title: String(res.payload.title),
          image_url: res.payload.image_url ? String(res.payload.image_url) : undefined,
          result_text: res.payload.result_text ? String(res.payload.result_text) : undefined
        };
        setSelectedExam(examObj);
        setRequestedLabs((prev) => [...prev, { title: examObj.title, result_text: examObj.result_text || res.examiner_message, image_url: examObj.image_url }]);
        setLabInput("");
      }
    } catch (err) {
      console.error("Falha ao executar ação:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // Callback de prescrição assinada na prancheta da sala de emergência
  const handlePrescriptionSubmitted = (
    prescriptionText: string, 
    examinerMessage: string, 
    spokenQueue: OsceSpokenQueueItem[],
    guidedFeedback?: OsceLiveFeedback
  ) => {
    if (guidedFeedback) {
      setLiveFeedback(guidedFeedback);
    }

    // Alimenta o motor fisiológico com as drogas administradas
    if (prescriptionText) {
      const lower = prescriptionText.toLowerCase();
      if (lower.includes("adrenalina") || lower.includes("epinefrina")) {
        vitalStore.applyIntervention("adrenalina", "Adrenalina");
      }
      if (lower.includes("noradrenalina")) {
        vitalStore.applyIntervention("noradrenalina", "Noradrenalina");
      }
      if (lower.includes("amiodarona")) {
        vitalStore.applyIntervention("amiodarona", "Amiodarona");
      }
      if (lower.includes("adenosina")) {
        vitalStore.applyIntervention("adenosina", "Adenosina");
      }
      if (lower.includes("sf 0,9") || lower.includes("soro") || lower.includes("cristaloide")) {
        vitalStore.applyIntervention("sf09", "Soro Fisiológico 0,9%");
      }
      if (lower.includes("insulina")) {
        vitalStore.applyIntervention("insulina", "Insulina Regular");
      }
      if (lower.includes("kcl") || lower.includes("potassio")) {
        vitalStore.applyIntervention("kcl", "Cloreto de Potássio");
      }
      if (lower.includes("sangue") || lower.includes("transfusao") || lower.includes("1:1:1")) {
        vitalStore.applyIntervention("sangue_111", "Transfusão Maciça 1:1:1");
      }
      if (lower.includes("tranexamico") || lower.includes("transamin")) {
        vitalStore.applyIntervention("acido_tranexamico", "Ácido Tranexâmico");
      }
      if (lower.includes("midazolam") || lower.includes("etomidato") || lower.includes("fentanil")) {
        vitalStore.applyIntervention("sedacao", "Sedação / Analgesia");
      }
    }

    const elapsed = getElapsedSeconds();
    setTranscript((prev) => [
      ...prev,
      {
        sender: "examinador",
        message: examinerMessage,
        timestamp: new Date().toISOString(),
        elapsed_seconds: elapsed,
        action_payload: { type: "prescription", text: prescriptionText }
      }
    ]);

    if (voiceEnabled && spokenQueue && spokenQueue.length > 0) {
      speakSpokenQueue(spokenQueue);
    }
  };

  // Callback de procedimento realizado no manequim 2D
  const handleProcedureExecuted = (
    title: string, 
    findings: string, 
    examinerMessage: string, 
    spokenQueue: OsceSpokenQueueItem[],
    guidedFeedback?: OsceLiveFeedback
  ) => {
    if (guidedFeedback) {
      setLiveFeedback(guidedFeedback);
    }

    // Alimenta o motor fisiológico com o procedimento realizado
    if (title.toLowerCase().includes("cardiovers") || title.toLowerCase().includes("choque")) {
      vitalStore.executeCardioversion(true, 100);
    } else {
      vitalStore.applyIntervention("procedure", title);
    }

    const elapsed = getElapsedSeconds();
    setTranscript((prev) => [
      ...prev,
      {
        sender: "examinador",
        message: examinerMessage,
        timestamp: new Date().toISOString(),
        elapsed_seconds: elapsed,
        action_payload: { type: "procedure", title, findings }
      }
    ]);

    if (voiceEnabled && spokenQueue && spokenQueue.length > 0) {
      speakSpokenQueue(spokenQueue);
    }
  };

  // Polling suave do Preceptor Fantasma para atualizar alertas proativos baseados no tempo decorrido
  useEffect(() => {
    if (phase !== "exam" || sessionMode !== "guided" || !sessionId) return;

    const interval = setInterval(async () => {
      try {
        const elapsed = getElapsedSeconds();
        const feedback = await api.osce.getLiveFeedback(sessionId, elapsed);
        if (feedback) {
          setLiveFeedback(feedback);
        }
      } catch {
        // Silencioso em caso de atraso na rede
      }
    }, 20000);

    return () => clearInterval(interval);
  }, [phase, sessionMode, sessionId, getElapsedSeconds]);

  return (
    <div className="flex-1 flex flex-col min-h-full w-full max-w-7xl mx-auto p-3 md:p-6">
      {/* ========================================================================= */}
      {/* FASE 1: PORTA DA ESTAÇÃO */}
      {/* ========================================================================= */}
      {phase === "door" && (
        <OsceDoorBriefing
          station={station}
          circuitId={circuitId}
          step={step}
          selectedMode={selectedMode}
          neutralStationLabel={neutralStationLabel}
          taskProgress={taskProgress}
          isLoading={isLoading}
          onSelectMode={setSelectedMode}
          onStartExam={handleStartExam}
        />
      )}

      {/* ========================================================================= */}
      {/* FASE 2: SALA DE EXAME BEIRA-LEITO */}
      {/* ========================================================================= */}
      {phase === "exam" && (
        <div className="flex-1 flex flex-col min-h-0 w-full gap-4 pb-12">
          {/* Topbar da Estação */}
          <div className="flex items-center justify-between p-3 md:p-4 rounded-2xl border border-border bg-card shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <span className="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-primary/10 text-primary">
                {station.institution}
              </span>
              <div>
                <h2 className="text-sm md:text-base font-bold text-foreground line-clamp-1">
                  {sessionMode === "blind" ? neutralStationLabel : station.title}
                </h2>
                <p className="text-xs text-muted-foreground hidden md:block">
                  {station.patient_persona.name || "Paciente"}, {station.patient_persona.age || "Adulto"} anos
                </p>
              </div>
            </div>

            {/* Cronômetro e Ações Rápidas */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                title={voiceEnabled ? "Desativar áudio do paciente" : "Ativar áudio do paciente"}
                className={`p-2 rounded-lg border text-xs ${
                  voiceEnabled ? "bg-primary/10 text-primary border-primary/20" : "bg-muted text-muted-foreground border-border"
                }`}
              >
                {voiceEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
              </button>

              <SessionTimer
                deadlineAt={examTiming.deadlineAt}
                fallbackSeconds={examTiming.duration}
                active={phase === "exam"}
                format="mmss"
                variant="osce"
                milestones={timerMilestones}
                onExpire={handleFinishExam}
              />

              <button
                onClick={handleFinishExam}
                disabled={isLoading}
                className="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-rose-500 hover:bg-rose-600 text-white shadow-sm transition-transform active:scale-95"
              >
                Finalizar Conduta
              </button>
            </div>
          </div>

          {/* HUD do Preceptor Fantasma (Modo Guiado) ou Indicador de Prova Cega */}
          <GhostPreceptorHUD feedback={liveFeedback} mode={sessionMode} />

          {/* Tarefas Sequenciais da Estação */}
          {taskProgress.visible_tasks.length > 0 && (
            <div className="rounded-lg border border-line-subtle bg-surface p-3.5 space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Tarefas Sequenciais ({taskProgress.completed_steps.length}/{taskProgress.total_steps} concluídas)
                </div>
                {!taskProgress.all_completed && (
                  <button
                    type="button"
                    onClick={handleCompleteCurrentTask}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 disabled:opacity-50 cursor-pointer"
                  >
                    <span>
                      {taskProgress.current_step < taskProgress.total_steps
                        ? `Declarar Tarefa ${taskProgress.current_step} Concluída → Liberar Tarefa ${taskProgress.current_step + 1}`
                        : `Declarar Última Tarefa Concluída`}
                    </span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {taskProgress.visible_tasks.map((t) => (
                  <div
                    key={t.id}
                    className={`flex items-start gap-2 p-2.5 rounded-lg border text-xs ${
                      t.completed
                        ? "border-emerald-500/30 bg-emerald-500/10 text-foreground"
                        : t.locked
                        ? "border-border/60 bg-muted/40 text-muted-foreground"
                        : "border-primary/40 bg-primary/10 text-foreground"
                    }`}
                  >
                    {t.locked ? (
                      <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <CheckCircle2
                        className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                          t.completed ? "text-emerald-500" : "text-primary"
                        }`}
                      />
                    )}
                    <div>
                      <span className="font-mono font-bold mr-1">T{t.step}:</span>
                      <span>
                        {t.locked
                          ? `Bloqueada — declare a Tarefa ${t.step - 1} concluída para liberar`
                          : t.description}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Banner de Sala Real Hands-Free (Viva-Voz Beira-Leito) */}
          <div className="rounded-lg border border-line-subtle bg-surface p-3.5 md:p-4 space-y-2.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={toggleHandsFreeMode}
                  className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-bold transition-colors ${
                    handsFreeMode
                      ? "bg-accent text-white"
                      : "bg-canvas text-muted-foreground hover:bg-muted border border-line-subtle"
                  }`}
                >
                  <Radio className="w-3.5 h-3.5" />
                  <span>{handsFreeMode ? "Modo Hands-Free ATIVADO" : "Modo Hands-Free Desligado"}</span>
                </button>

                {/* Status Dinâmico de Fala / Escuta */}
                <div className="flex items-center gap-2 text-xs">
                  {activeSpeaker ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/15 text-amber-600 dark:text-amber-400 font-bold">
                      <Volume2 className="w-3.5 h-3.5" />
                      <span>{activeSpeaker === "examinador" ? "Examinador da Banca Falando..." : `${station.patient_persona.name || "Paciente"} Falando...`}</span>
                      <span className="text-[10px] opacity-75 font-normal ml-1">(Esc para interromper)</span>
                    </span>
                  ) : isListening ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold">
                      <Radio className="w-3.5 h-3.5" />
                      <span>Ouvindo sua voz em tempo real...</span>
                    </span>
                  ) : isLoading ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-accent/15 text-accent font-bold">
                      <Zap className="w-3.5 h-3.5" />
                      <span>Processando comando clínico...</span>
                    </span>
                  ) : micPermission === "unsupported" ? (
                    <span className="text-muted-foreground text-xs">Modo texto / atalhos ativo</span>
                  ) : (
                    <span className="text-muted-foreground text-xs">Microfone aguardando ativação</span>
                  )}
                </div>
              </div>

              {/* Dica de Teclado */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                <Headphones className="w-3.5 h-3.5 text-accent hidden sm:inline" />
                <span className="text-[11px] hidden sm:inline">Use fones •</span>
                <kbd className="px-1.5 py-0.5 rounded bg-muted border border-line-subtle text-[10px] font-mono">Espaço</kbd>
                <span className="text-[11px]">ligar mic •</span>
                <kbd className="px-1.5 py-0.5 rounded bg-muted border border-line-subtle text-[10px] font-mono">Alt+1..4</kbd>
                <span className="text-[11px] hidden sm:inline">trocar abas •</span>
                <kbd className="px-1.5 py-0.5 rounded bg-muted border border-line-subtle text-[10px] font-mono">Alt+M</kbd>
                <span className="text-[11px] hidden sm:inline">viva-voz •</span>
                <kbd className="px-1.5 py-0.5 rounded bg-muted border border-line-subtle text-[10px] font-mono">Esc</kbd>
                <span className="text-[11px] hidden md:inline">corta fala</span>
              </div>
            </div>

            {/* Alerta de Diagnóstico ou Orientação de Microfone */}
            {micPermission === "unsupported" && micErrorMsg && (
              <div className="flex items-center justify-between gap-3 p-3 rounded-md bg-blue-500/10 border border-blue-500/30 text-xs text-blue-300">
                <div className="flex items-start sm:items-center gap-2">
                  <Lightbulb className="w-4 h-4 shrink-0" />
                  <span className="leading-relaxed">{micErrorMsg}</span>
                </div>
              </div>
            )}

            {micPermission === "denied" && micErrorMsg && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 p-3 rounded-xl bg-destructive/15 border border-destructive/30 text-xs text-destructive animate-in fade-in">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{micErrorMsg}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                  <button
                    type="button"
                    onClick={() => requestMicrophonePermission().then(ok => { if (ok) startListening(true); })}
                    className="px-2.5 py-1 rounded-lg bg-destructive text-destructive-foreground text-[11px] font-bold hover:bg-destructive/90 cursor-pointer"
                  >
                    Tentar Novamente
                  </button>
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="px-2.5 py-1 rounded-lg bg-muted border border-border text-foreground text-[11px] font-medium hover:bg-muted/80 cursor-pointer"
                  >
                    Recarregar Página
                  </button>
                </div>
              </div>
            )}

            {/* Balão de Transcrição Ao Vivo */}
            {interimSpeechText && (
              <div className="p-2.5 rounded-xl bg-card border border-primary/40 text-xs text-foreground flex items-center gap-2 animate-in fade-in">
                <span className="font-bold text-primary shrink-0">Transcrição ao vivo:</span>
                <span className="italic truncate text-foreground/90">&ldquo;{interimSpeechText}&rdquo;</span>
              </div>
            )}

            {/* Pílulas de Exemplos de Comandos Clínicos para Treinamento Verbal */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px]">
              <span className="text-muted-foreground font-semibold">Comandos por voz:</span>
              {quickVoiceSuggestions.map((item) => (
                <button
                  key={item.label}
                  onClick={() => handleSendMessage(item.message)}
                  className="px-2 py-0.5 rounded-md bg-muted/60 hover:bg-primary/20 hover:text-primary transition-colors text-muted-foreground border border-border/60"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* MONITOR MULTIPARAMÉTRICO VIRTUAL EM TEMPO REAL (APENAS EMERGÊNCIA E PROCEDIMENTO) */}
          {showMonitor && <LiveMultiparameterMonitor store={vitalStore} />}

          {/* Grid Principal: Chat com Paciente (Esq) + Painel de Ações Clínicas (Dir) */}
          <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-0">
            {/* Coluna Esquerda: Palco Clínico Triplo & Semiotécnica Bruta (7 cols) */}
            <div className="lg:col-span-7 flex flex-col min-h-[440px] lg:min-h-0">
              <ClinicalStage
                station={station}
                getAuscultationVitals={getAuscultationVitals}
                transcript={transcript}
                isLoading={isLoading}
                onSendMessage={async (text, target) => {
                  await handleSendMessage(text, target);
                }}
                isListening={isListening}
                onToggleListening={toggleListening}
                micPermission={micPermission}
              />
            </div>

            {/* Coluna Direita: Ações Médicas & Exame Físico (5 cols) */}
            <div className="lg:col-span-5 flex flex-col rounded-2xl border border-border bg-card overflow-hidden min-h-0">
              {/* Abas Laterais */}
              <div className="flex border-b border-border bg-muted/30">
                <button
                  onClick={() => setActiveTab("physical")}
                  className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 transition-colors flex items-center justify-center gap-1 ${
                    activeTab === "physical"
                      ? "border-primary text-primary bg-background"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                  title="Atalho: Alt + 1"
                >
                  <span>Exame Físico</span>
                  <span className="hidden xl:inline text-[9px] opacity-60 font-mono font-normal bg-muted/60 px-1 rounded">1</span>
                </button>
                {showMannequin && (
                  <button
                    onClick={() => setActiveTab("procedures")}
                    className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 transition-colors flex items-center justify-center gap-1 ${
                      activeTab === "procedures"
                        ? "border-primary text-primary bg-background"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                    title="Atalho: Alt + 2"
                  >
                    <span>Manequim</span>
                    <span className="hidden xl:inline text-[9px] opacity-60 font-mono font-normal bg-muted/60 px-1 rounded">2</span>
                  </button>
                )}
                <button
                  onClick={() => setActiveTab("labs")}
                  className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 transition-colors flex items-center justify-center gap-1 ${
                    activeTab === "labs"
                      ? "border-primary text-primary bg-background"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                  title="Atalho: Alt + 3"
                >
                  <span>Exames</span>
                  <span className="hidden xl:inline text-[9px] opacity-60 font-mono font-normal bg-muted/60 px-1 rounded">3</span>
                </button>
                <button
                  onClick={() => setActiveTab("conduct")}
                  className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 transition-colors flex items-center justify-center gap-1 ${
                    activeTab === "conduct"
                      ? "border-primary text-primary bg-background"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                  title="Atalho: Alt + 4"
                >
                  <span>Conduta</span>
                  <span className="hidden xl:inline text-[9px] opacity-60 font-mono font-normal bg-muted/60 px-1 rounded">4</span>
                </button>
              </div>

              {/* Conteúdo da Aba */}
              <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs">
                {/* ABA 1: EXAME FÍSICO */}
                {activeTab === "physical" && (
                  <div className="space-y-4">
                    {/* Botão Sinais Vitais */}
                    <div className="flex items-center justify-between p-3 rounded-xl bg-muted/40 border border-border">
                      <span className="font-bold text-foreground">Monitor e Sinais Vitais</span>
                      <button
                        onClick={() => handleClinicalAction("vitals", "vitals")}
                        className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-bold text-[11px] hover:bg-primary/90"
                      >
                        Checar Sinais
                      </button>
                    </div>

                    {/* Sinais Vitais Exibidos Dinâmicos */}
                    <LivePhysicalVitalsCard store={vitalStore} fallbackVitals={vitals} />

                    {/* Pedido Livre de Manobra Semiológica (Sem menu de spoilers) */}
                    <div className="space-y-2.5">
                      <span className="text-muted-foreground font-semibold block">
                        Solicitar Manobra do Exame Físico ao Examinador:
                      </span>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          const clean = physicalInput.trim();
                          if (clean && !isLoading) {
                            handleClinicalAction("physical_exam", clean);
                          }
                        }}
                        className="flex gap-2"
                      >
                        <input
                          type="text"
                          value={physicalInput}
                          onChange={(e) => setPhysicalInput(e.target.value)}
                          placeholder="Ex: ausculta pulmonar, palpação abdominal profunda, percussão torácica..."
                          className="flex-1 px-3 py-2 rounded-xl border border-border bg-background text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary"
                        />
                        <button
                          type="submit"
                          disabled={isLoading || !physicalInput.trim()}
                          className="px-3.5 py-2 rounded-xl bg-primary text-primary-foreground font-bold text-[11px] hover:bg-primary/90 disabled:opacity-50 shrink-0 cursor-pointer flex items-center gap-1.5"
                        >
                          <Stethoscope className="w-3.5 h-3.5" />
                          <span>Solicitar Manobra</span>
                        </button>
                      </form>
                      <p className="text-[11px] text-muted-foreground">
                        Especifique a manobra desejada. Pedidos vagos como &ldquo;abdome&rdquo; ou &ldquo;exame físico&rdquo; exigem detalhamento.
                      </p>

                      {requestedPhysicalExams.length > 0 && (
                        <div className="space-y-2 pt-2">
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground block">
                            Achados Entregues pela Banca
                          </span>
                          {requestedPhysicalExams.map((pe, idx) => (
                            <div key={idx} className="p-3 rounded-xl border border-border bg-card space-y-1">
                              <div className="font-bold text-primary text-[11px] capitalize">{pe.target}</div>
                              <p className="text-foreground/90 leading-relaxed">{pe.finding}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* ABA 2: MANEQUIM INTERATIVO & E-FAST */}
                {showMannequin && activeTab === "procedures" && (
                  <div className="space-y-4">
                    {sessionId ? (
                      <ProcedureMannequin
                        sessionId={sessionId}
                        getElapsedSeconds={getElapsedSeconds}
                        onProcedureExecuted={handleProcedureExecuted}
                        isLoading={isLoading}
                      />
                    ) : (
                      <div className="p-4 text-center text-muted-foreground text-xs">
                        Iniciando sessão do manequim...
                      </div>
                    )}
                  </div>
                )}

                {/* ABA 3: EXAMES COMPLEMENTARES */}
                {activeTab === "labs" && (
                  <div className="space-y-4">
                    <span className="text-muted-foreground font-semibold block">
                      Solicitar Exame Complementar à Banca Examinadora:
                    </span>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const clean = labInput.trim();
                        if (clean && !isLoading) {
                          handleClinicalAction("lab_imaging", clean);
                        }
                      }}
                      className="flex gap-2"
                    >
                      <input
                        type="text"
                        value={labInput}
                        onChange={(e) => setLabInput(e.target.value)}
                        placeholder="Ex: ECG 12 derivações, gasometria arterial, RX de tórax em PA, troponina..."
                        className="flex-1 px-3 py-2 rounded-xl border border-border bg-background text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary"
                      />
                      <button
                        type="submit"
                        disabled={isLoading || !labInput.trim()}
                        className="px-3.5 py-2 rounded-xl bg-primary text-primary-foreground font-bold text-[11px] hover:bg-primary/90 disabled:opacity-50 shrink-0 cursor-pointer flex items-center gap-1.5"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>Solicitar Exame</span>
                      </button>
                    </form>
                    <p className="text-[11px] text-muted-foreground">
                      Digite exatamente o exame que deseja pedir. Exames não previstos na estação retornam laudo neutro.
                    </p>

                    {/* Visualizador de Exame Selecionado */}
                    {selectedExam && (
                      <div className="p-3.5 rounded-xl border-2 border-primary/20 bg-card space-y-2 mt-2">
                        <div className="font-bold text-foreground text-xs border-b border-border pb-1">
                          {selectedExam.title}
                        </div>
                        <p className="text-foreground/90 font-medium leading-relaxed">
                          {selectedExam.result_text}
                        </p>
                      </div>
                    )}

                    {requestedLabs.length > 1 && (
                      <div className="space-y-2 pt-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground block">
                          Histórico de Exames Solicitados
                        </span>
                        {requestedLabs.slice(0, -1).reverse().map((lab, idx) => (
                          <div key={idx} className="p-2.5 rounded-xl border border-border bg-muted/30 space-y-1">
                            <div className="font-semibold text-foreground text-[11px]">{lab.title}</div>
                            <p className="text-muted-foreground text-[11px]">{lab.result_text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* ABA 4: PRANCHETA DE PRESCRIÇÃO E CONDUTA VERBAL */}
                {activeTab === "conduct" && (
                  <div className="space-y-4">
                    {sessionId && showPrescriptionPad && (
                      <PrescriptionPad
                        sessionId={sessionId}
                        getElapsedSeconds={getElapsedSeconds}
                        onPrescriptionSubmitted={handlePrescriptionSubmitted}
                        isLoading={isLoading}
                      />
                    )}

                    <div className="pt-3 border-t border-border space-y-2">
                      <span className="text-muted-foreground font-semibold block text-[11px]">
                        Verbalização Final & Conclusão de Prova (Resumo da Conduta):
                      </span>
                      <textarea
                        value={conductText}
                        onChange={(e) => setConductText(e.target.value)}
                        onKeyDown={(e) => {
                          if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && conductText.trim() && !isLoading) {
                            e.preventDefault();
                            handleFinishExam();
                          }
                        }}
                        placeholder="Ex: Confirmo monitorização contínua, paciente estabilizado com a prescrição acima e indico laparotomia exploradora imediata... (ou pressione Ctrl+Enter)"
                        className="w-full h-24 p-3 bg-muted/40 border border-border rounded-xl text-xs focus:outline-none focus:border-primary resize-none leading-relaxed"
                      />
                      <button
                        onClick={handleFinishExam}
                        disabled={isLoading || !conductText.trim()}
                        className="w-full py-2.5 rounded-xl font-bold bg-primary text-primary-foreground hover:bg-primary/90 text-xs shadow-sm transition-transform active:scale-98 flex items-center justify-center gap-1.5"
                      >
                        <span>Registrar Conduta e Concluir Prova</span>
                        <span className="hidden sm:inline text-[10px] opacity-70 font-mono font-normal bg-primary-foreground/20 px-1 rounded">[Ctrl+Enter]</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* FASE 3: ESPELHO OFICIAL DE CORREÇÃO (BAREMA) */}
      {/* ========================================================================= */}
      {phase === "finished" && report && (
        <OsceFinishView
          station={station}
          report={report}
          finalElapsedSeconds={finalElapsedSeconds}
          circuitId={circuitId}
          step={step}
          circuitPlan={circuitPlan}
          circuitSummary={circuitSummary}
          showCircuitModal={showCircuitModal}
          isLoadingCircuit={isLoadingCircuit}
          onAdvanceCircuit={handleAdvanceCircuit}
          onOpenCircuitSummary={handleOpenCircuitSummary}
          onCloseCircuitModal={() => setShowCircuitModal(false)}
          onNavigateHub={() => router.push("/osce")}
        />
      )}
    </div>
  );
}
