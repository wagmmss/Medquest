"use client";

import { useEffect, useRef, useCallback, useMemo, useSyncExternalStore } from "react";
import {
  OscePhysiologyVitals,
  OscePhysiologyEngineConfig,
  OsceInterventionModifier,
} from "@/types/api";

export interface ActiveInterventionItem {
  id: string;
  key: string;
  label: string;
  appliedAtElapsed: number;
  modifier: OsceInterventionModifier;
  active: boolean;
}

export interface VitalAlarm {
  id: string;
  level: "red" | "yellow";
  message: string;
}

export interface DisplayedNibp {
  sbp: number;
  dbp: number;
  pam: number;
  measuredAtElapsed: number;
}

export interface UseVitalStateEngineProps {
  initialConfig?: OscePhysiologyEngineConfig | null;
  fallbackVitals?: Record<string, string> | null;
  getElapsedSeconds: () => number;
  isActive: boolean;
}

function parseFallbackVitals(vitals?: Record<string, string> | null): OscePhysiologyVitals {
  if (!vitals) {
    return {
      hr: 78,
      sbp: 120,
      dbp: 80,
      spo2: 98,
      rr: 16,
      temp: 36.5,
      gcs: 15,
      rhythm: "NORMAL_SINUS",
      etco2: 38,
      perfusion_index: 2.5,
    };
  }

  const fcMatch = vitals.fc?.match(/\b(\d{2,3})\b/);
  const hr = fcMatch ? parseInt(fcMatch[1], 10) : 78;

  const paMatch = vitals.pa?.match(/(\d{2,3})\s*[xX/]\s*(\d{2,3})/);
  const sbp = paMatch ? parseInt(paMatch[1], 10) : 120;
  const dbp = paMatch ? parseInt(paMatch[2], 10) : 80;

  const satMatch = vitals.sato2?.match(/(\d{2,3})%/);
  const spo2 = satMatch ? parseInt(satMatch[1], 10) : 97;

  const frMatch = vitals.fr?.match(/\b(\d{1,2})\b/);
  const rr = frMatch ? parseInt(frMatch[1], 10) : 16;

  const tempMatch = vitals.temp?.match(/(\d{2}[.,]\d)/);
  const temp = tempMatch ? parseFloat(tempMatch[1].replace(",", ".")) : 36.5;

  let rhythm = "NORMAL_SINUS";
  if (hr > 150) rhythm = "UNSTABLE_SVT";
  else if (hr >= 100) rhythm = "SINUS_TACHYCARDIA";
  else if (hr < 50) rhythm = "SINUS_BRADYCARDIA";

  return {
    hr,
    sbp,
    dbp,
    spo2,
    rr,
    temp,
    gcs: sbp >= 90 ? 15 : 13,
    rhythm,
    etco2: 36,
    perfusion_index: sbp >= 90 ? 2.2 : 0.8,
  };
}

export interface VitalMonitorState {
  ecg: boolean;
  spo2: boolean;
  nibp: boolean;
  capno: boolean;
}

export interface VitalHistoryPoint {
  elapsed: number;
  hr: number;
  sbp: number;
  dbp: number;
  pam: number;
  spo2: number;
  rhythm: string;
}

export interface VitalStateSnapshot {
  vitals: OscePhysiologyVitals;
  isMonitored: VitalMonitorState;
  displayedNibp: DisplayedNibp | null;
  isMeasuringNibp: boolean;
  interventions: ActiveInterventionItem[];
  iatrogenicAlerts: string[];
  activeAlarms: VitalAlarm[];
  isAlarmSilenced: boolean;
  isAudioMuted: boolean;
  vitalsHistory: VitalHistoryPoint[];
}

export interface VitalStateStore {
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => VitalStateSnapshot;
  measureNibp: () => void;
  connectSensors: (sensors?: ("all" | "ecg" | "spo2" | "nibp" | "capno")[]) => void;
  silenceAlarms: (seconds?: number) => void;
  toggleAudio: () => void;
  applyIntervention: (key: string, label: string) => void;
  executeCardioversion: (synchronized: boolean, joules: number) => void;
}

function computeActiveAlarms(vitals: OscePhysiologyVitals, isMonitored: VitalMonitorState): VitalAlarm[] {
  const list: VitalAlarm[] = [];

  if (!isMonitored.ecg && !isMonitored.spo2) {
    list.push({ id: "sensors_disconnected", level: "yellow", message: "CABOS DE MONITORIZAÇÃO DESCONECTADOS" });
    return list;
  }

  if (vitals.rhythm === "VENTRICULAR_FIBRILLATION") {
    list.push({ id: "vf", level: "red", message: "🚨 FIBRILAÇÃO VENTRICULAR / PCR" });
  } else if (vitals.rhythm === "VENTRICULAR_TACHYCARDIA") {
    list.push({ id: "tv", level: "red", message: "🚨 TAQUICARDIA VENTRICULAR MONOMÓRFICA" });
  } else if (vitals.sbp <= 0 || vitals.hr <= 35) {
    list.push({ id: "arrest", level: "red", message: "🚨 COLAPSO HEMODINÂMICO / AESP" });
  } else if (vitals.sbp < 75) {
    list.push({ id: "hypotension", level: "red", message: `🚨 HIPOTENSÃO CRÍTICA (PAS ${vitals.sbp} mmHg)` });
  } else if (vitals.spo2 < 85) {
    list.push({ id: "hypoxemia", level: "red", message: `🚨 HIPOXEMIA SEVERA (SpO2 ${vitals.spo2}%)` });
  } else if (vitals.hr > 150) {
    list.push({ id: "tachycardia", level: "yellow", message: `TAQUICARDIA SEVERA (${vitals.hr} bpm)` });
  }

  return list;
}

export function useVitalStateStore({
  initialConfig,
  fallbackVitals,
  getElapsedSeconds,
  isActive,
}: UseVitalStateEngineProps): VitalStateStore {
  const getElapsedSecondsRef = useRef(getElapsedSeconds);
  const initialConfigRef = useRef(initialConfig);
  useEffect(() => {
    getElapsedSecondsRef.current = getElapsedSeconds;
  }, [getElapsedSeconds]);
  useEffect(() => {
    initialConfigRef.current = initialConfig;
  }, [initialConfig]);

  // Estado base inicial
  const baseVitals = useMemo<OscePhysiologyVitals>(() => {
    if (initialConfig?.initial_state) {
      return { ...initialConfig.initial_state };
    }
    return parseFallbackVitals(fallbackVitals);
  }, [initialConfig, fallbackVitals]);

  const initialMonitorState: VitalMonitorState = {
    ecg: false,
    spo2: false,
    nibp: false,
    capno: false,
  };

  const snapshotRef = useRef<VitalStateSnapshot>({
    vitals: baseVitals,
    isMonitored: initialMonitorState,
    displayedNibp: null,
    isMeasuringNibp: false,
    interventions: [],
    iatrogenicAlerts: [],
    activeAlarms: computeActiveAlarms(baseVitals, initialMonitorState),
    isAlarmSilenced: false,
    isAudioMuted: false,
    vitalsHistory: [],
  });
  const listenersRef = useRef<Set<() => void>>(new Set());
  const prevBaseVitalsRef = useRef<OscePhysiologyVitals>(baseVitals);
  const lastHistorySlotRef = useRef<number>(-1);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const nibpTimerRef = useRef<NodeJS.Timeout | null>(null);

  const notify = useCallback(() => {
    listenersRef.current.forEach((listener) => listener());
  }, []);

  const commitSnapshot = useCallback((updater: (prev: VitalStateSnapshot) => VitalStateSnapshot) => {
    const next = updater(snapshotRef.current);
    if (next !== snapshotRef.current) {
      if (next.vitals !== snapshotRef.current.vitals || next.isMonitored !== snapshotRef.current.isMonitored) {
        next.activeAlarms = computeActiveAlarms(next.vitals, next.isMonitored);
      }
      snapshotRef.current = next;
      notify();
    }
  }, [notify]);

  useEffect(() => {
    return () => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      if (nibpTimerRef.current) {
        clearTimeout(nibpTimerRef.current);
        nibpTimerRef.current = null;
      }
    };
  }, []);

  // Sincroniza estado base caso baseVitals mude sem causar re-render do pai no tick de 1s
  useEffect(() => {
    if (baseVitals !== prevBaseVitalsRef.current) {
      prevBaseVitalsRef.current = baseVitals;
      lastHistorySlotRef.current = -1;
      commitSnapshot((prev) => ({
        ...prev,
        vitals: baseVitals,
      }));
    }
  }, [baseVitals, commitSnapshot]);

  // Aferir PNI sob demanda (lê snapshotRef síncrono sem side-effect em updater React 19)
  const measureNibp = useCallback(() => {
    if (snapshotRef.current.isMeasuringNibp) return;
    commitSnapshot((prev) => ({ ...prev, isMeasuringNibp: true }));

    if (nibpTimerRef.current) {
      clearTimeout(nibpTimerRef.current);
    }
    nibpTimerRef.current = setTimeout(() => {
      const elapsedNow = getElapsedSecondsRef.current();
      const curr = snapshotRef.current.vitals;
      const pam = Math.round((curr.sbp + 2 * curr.dbp) / 3);
      commitSnapshot((prev) => ({
        ...prev,
        isMeasuringNibp: false,
        displayedNibp: {
          sbp: curr.sbp,
          dbp: curr.dbp,
          pam,
          measuredAtElapsed: elapsedNow,
        },
      }));
    }, 2800);
  }, [commitSnapshot]);

  // Conectar sensores beira-leito
  const connectSensors = useCallback(
    (sensors: ("all" | "ecg" | "spo2" | "nibp" | "capno")[] = ["all"]) => {
      commitSnapshot((prev) => {
        const nextMonitored = sensors.includes("all")
          ? { ecg: true, spo2: true, nibp: true, capno: true }
          : {
              ecg: sensors.includes("ecg") ? true : prev.isMonitored.ecg,
              spo2: sensors.includes("spo2") ? true : prev.isMonitored.spo2,
              nibp: sensors.includes("nibp") ? true : prev.isMonitored.nibp,
              capno: sensors.includes("capno") ? true : prev.isMonitored.capno,
            };
        return { ...prev, isMonitored: nextMonitored };
      });

      if (!snapshotRef.current.displayedNibp) {
        measureNibp();
      }
    },
    [commitSnapshot, measureNibp]
  );

  // Silenciar alarmes por 120s
  const silenceAlarms = useCallback((seconds = 120) => {
    commitSnapshot((prev) => ({ ...prev, isAlarmSilenced: true }));
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    silenceTimerRef.current = setTimeout(() => {
      commitSnapshot((prev) => ({ ...prev, isAlarmSilenced: false }));
    }, seconds * 1000);
  }, [commitSnapshot]);

  // Alternar mudo geral de áudio
  const toggleAudio = useCallback(() => {
    commitSnapshot((prev) => ({ ...prev, isAudioMuted: !prev.isAudioMuted }));
  }, [commitSnapshot]);

  // Aplicar intervenção farmacológica ou clínica
  const applyIntervention = useCallback(
    (key: string, label: string) => {
      const modifier = initialConfigRef.current?.intervention_modifiers?.[key] || {
        onset_seconds: 10,
        duration_seconds: 60,
      };

      const newItem: ActiveInterventionItem = {
        id: `interv-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        key,
        label,
        appliedAtElapsed: getElapsedSecondsRef.current(),
        modifier,
        active: true,
      };

      commitSnapshot((prev) => ({
        ...prev,
        interventions: [...prev.interventions, newItem],
        vitals: modifier.instant && modifier.target_vitals
          ? { ...prev.vitals, ...modifier.target_vitals }
          : prev.vitals,
        iatrogenicAlerts: modifier.iatrogenic_alert
          ? [...prev.iatrogenicAlerts, modifier.iatrogenic_alert]
          : prev.iatrogenicAlerts,
      }));
    },
    [commitSnapshot]
  );

  // Executar cardioversão elétrica / desfibrilação
  const executeCardioversion = useCallback(
    (synchronized: boolean, joules: number) => {
      const currentRhythm = snapshotRef.current.vitals.rhythm;
      const isTV = currentRhythm === "VENTRICULAR_TACHYCARDIA" || currentRhythm === "UNSTABLE_SVT";

      if (isTV) {
        if (synchronized) {
          applyIntervention("cardioversion_sync", `Cardioversão Elétrica Sincronizada (${joules}J)`);
          commitSnapshot((prev) => ({
            ...prev,
            vitals: {
              ...prev.vitals,
              hr: 82,
              sbp: 116,
              dbp: 72,
              spo2: 97,
              rr: 18,
              gcs: 15,
              rhythm: "NORMAL_SINUS",
            },
          }));
        } else {
          applyIntervention("cardioversion_unsync", `Choque Desincronizado ${joules}J (R sobre T)`);
          commitSnapshot((prev) => ({
            ...prev,
            vitals: {
              ...prev.vitals,
              hr: 250,
              sbp: 0,
              dbp: 0,
              spo2: 0,
              rr: 0,
              gcs: 3,
              rhythm: "VENTRICULAR_FIBRILLATION",
            },
          }));
        }
      } else if (currentRhythm === "VENTRICULAR_FIBRILLATION") {
        applyIntervention("defibrillation", `Desfibrilação Bifásica ${joules}J`);
        commitSnapshot((prev) => ({
          ...prev,
          vitals: {
            ...prev.vitals,
            hr: 92,
            sbp: 104,
            dbp: 68,
            spo2: 95,
            rr: 16,
            gcs: 14,
            rhythm: "NORMAL_SINUS",
          },
        }));
      }
    },
    [applyIntervention, commitSnapshot]
  );

  // Ciclo fisiológico dinâmico rodando a cada segundo
  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(() => {
      const elapsedSeconds = getElapsedSecondsRef.current();
      const activeInterventions = snapshotRef.current.interventions;

      let updated = { ...snapshotRef.current.vitals };

      // 1. Aplica modificadores de intervenções ativas (farmacocinética)
      activeInterventions.forEach((item) => {
        const deltaT = elapsedSeconds - item.appliedAtElapsed;
        const onset = item.modifier.onset_seconds || 10;
        const duration = item.modifier.duration_seconds || 60;

        if (deltaT >= onset && deltaT <= onset + duration) {
          const dv = item.modifier.delta_vitals;
          if (dv) {
            if (dv.sbp) updated.sbp = Math.min(200, Math.max(0, updated.sbp + dv.sbp * 0.05));
            if (dv.dbp) updated.dbp = Math.min(130, Math.max(0, updated.dbp + (dv.dbp || 0) * 0.05));
            if (dv.hr) updated.hr = Math.min(220, Math.max(0, updated.hr + dv.hr * 0.05));
            if (dv.spo2) updated.spo2 = Math.min(100, Math.max(0, updated.spo2 + (dv.spo2 || 0) * 0.05));
          }
        }
      });

      // 2. Aplica progressão natural (deterioração se sem intervenção)
      if (initialConfig?.natural_progression) {
        const appliedKeys = activeInterventions.map((i) => i.key);
        initialConfig.natural_progression.forEach((rule) => {
          const conditionMet =
            (rule.condition.includes("time_elapsed > 120") && elapsedSeconds > 120) ||
            (rule.condition.includes("time_elapsed > 180") && elapsedSeconds > 180) ||
            (rule.condition.includes("sbp < 55") && updated.sbp < 55);

          const hasCounterIntervention = appliedKeys.some((k) => rule.condition.includes(k));

          if (conditionMet && !hasCounterIntervention) {
            if (rule.effects_per_minute) {
              const em = rule.effects_per_minute;
              if (em.sbp) updated.sbp = Math.max(0, updated.sbp + em.sbp / 60);
              if (em.dbp) updated.dbp = Math.max(0, updated.dbp + em.dbp / 60);
              if (em.hr) updated.hr = Math.min(240, updated.hr + (em.hr || 0) / 60);
              if (em.spo2) updated.spo2 = Math.max(0, updated.spo2 + (em.spo2 || 0) / 60);
              if (em.gcs && updated.gcs) updated.gcs = Math.max(3, updated.gcs + (em.gcs || 0) / 60);
            }

            if (rule.override_vitals && updated.sbp <= 50) {
              updated = { ...updated, ...rule.override_vitals };
            }
          }
        });
      }

      // 3. Jitter Fisiológico Estocástico (pequena flutuação realista ±1%)
      const jitter = (Math.random() - 0.5) * 1.2;
      if (updated.sbp > 30) {
        updated.sbp = Math.round(updated.sbp + jitter);
        updated.dbp = Math.round(updated.dbp + jitter * 0.5);
        updated.hr = Math.round(updated.hr + jitter * 0.8);
      }

      // Arredondamentos e travas
      updated.sbp = Math.max(0, Math.min(240, Math.round(updated.sbp)));
      updated.dbp = Math.max(0, Math.min(140, Math.round(updated.dbp)));
      updated.hr = Math.max(0, Math.min(260, Math.round(updated.hr)));
      updated.spo2 = Math.max(0, Math.min(100, Math.round(updated.spo2)));

      const historySlot = Math.floor(elapsedSeconds / 5);
      commitSnapshot((prev) => {
        let nextHistory = prev.vitalsHistory;
        if (historySlot > lastHistorySlotRef.current) {
          lastHistorySlotRef.current = historySlot;
          nextHistory = [
            ...prev.vitalsHistory,
            {
              elapsed: elapsedSeconds,
              hr: updated.hr,
              sbp: updated.sbp,
              dbp: updated.dbp,
              pam: Math.round((updated.sbp + 2 * updated.dbp) / 3),
              spo2: updated.spo2,
              rhythm: updated.rhythm,
            },
          ];
        }
        return {
          ...prev,
          vitals: updated,
          vitalsHistory: nextHistory,
        };
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isActive, initialConfig, commitSnapshot]);

  const subscribe = useCallback((listener: () => void) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const getSnapshot = useCallback(() => snapshotRef.current, []);

  return useMemo<VitalStateStore>(
    () => ({
      subscribe,
      getSnapshot,
      measureNibp,
      connectSensors,
      silenceAlarms,
      toggleAudio,
      applyIntervention,
      executeCardioversion,
    }),
    [
      subscribe,
      getSnapshot,
      measureNibp,
      connectSensors,
      silenceAlarms,
      toggleAudio,
      applyIntervention,
      executeCardioversion,
    ]
  );
}

export function useVitalSnapshot(store: VitalStateStore): VitalStateSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}

export function useVitalStateEngine(props: UseVitalStateEngineProps) {
  const store = useVitalStateStore(props);
  const snapshot = useVitalSnapshot(store);
  return {
    ...snapshot,
    measureNibp: store.measureNibp,
    connectSensors: store.connectSensors,
    silenceAlarms: store.silenceAlarms,
    toggleAudio: store.toggleAudio,
    applyIntervention: store.applyIntervention,
    executeCardioversion: store.executeCardioversion,
  };
}
