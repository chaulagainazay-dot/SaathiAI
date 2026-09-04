"use client";

/**
 * The single Command Core snapshot owner.
 *
 * Exactly one place calls buildCommandCoreSnapshot(). Presence, status and
 * conversation all read the same object, so no component keeps its own copy of
 * the state machine and no two surfaces can disagree.
 *
 * This hook subscribes to nothing new. It reads the voice session that
 * Shell.jsx already mounts and the mission/system data the page already
 * fetched. No second event bus, no second microphone owner, no polling.
 */

import { useMemo, useRef } from "react";
import { buildCommandCoreSnapshot } from "./command-core-adapter.js";

/**
 * @param {object} input
 * @param {object} input.voiceSession  `useVoiceSession().session`
 * @param {Array}  [input.missions]    normalized mission summaries already on the page
 * @param {object} [input.system]      infra health read model already on the page
 * @param {Array}  [input.runEvents]   run event rows, when a run is in context
 * @param {string} [input.runId]
 * @param {object} [input.guardian]    trading-path verdict only
 * @param {object} [input.execution]   trading-path execution truth only
 * @param {number|null} [input.microphoneEnergy] real measured RMS, or null
 */
export function useCommandCoreSnapshot(input = {}) {
  const previousRef = useRef(null);

  const {
    voiceSession,
    missions,
    system,
    runEvents,
    runId,
    guardian,
    execution,
    microphoneEnergy,
  } = input;

  const snapshot = useMemo(() => {
    const next = buildCommandCoreSnapshot({
      voiceSession,
      missions,
      system,
      runEvents,
      runId,
      guardian,
      execution,
      microphoneEnergy,
      previousCoreState: previousRef.current,
    });
    return next;
  }, [voiceSession, missions, system, runEvents, runId, guardian, execution, microphoneEnergy]);

  // Remember the last state for transition reporting. Assigning during render
  // would make the value depend on render count, so it is written after the
  // snapshot is built and only ever read as "the previous one".
  if (previousRef.current !== snapshot.coreState) {
    previousRef.current = snapshot.coreState;
  }

  return snapshot;
}
