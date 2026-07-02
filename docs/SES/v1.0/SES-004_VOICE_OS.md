```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Voice OS — Real-Time Conversational Operating System
Document ID         : SES-004
Version             : 1.0.0
Status              : Approved
Maturity            : L3
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : 2026-07-02
Last Updated        : 2026-07-02
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft |
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — 10-part Voice OS specification with CSM and capability matrix |

---

## Why This Document Exists

Voice is the oldest human interface. It requires no literacy, no fine motor control, no screen. It is the interface that works when the user's hands are occupied, when the environment is dark, when the user is stressed and needs to think aloud. An AI platform that is only reachable through a keyboard is a platform that serves a narrow slice of human experience.

SaathiAI's Voice OS is not a voice assistant feature. It is a real-time conversational operating system — a dedicated layer that manages the full complexity of spoken human interaction: listening while speaking, handling interruptions, tracking conversation context across multiple turns, verifying who is speaking, and adapting its vocal character to the emotional register of the conversation.

Voice OS sits at the intersection of three other major SES documents:

- **SES-002 Agent System** — the agents Voice OS invokes are exactly the agents defined there; the SafetyHarness governs voice-triggered actions exactly as it governs API-triggered actions
- **SES-003 Memory** — the conversation context that Voice OS builds is assembled by the Context Assembly Engine; what Voice OS learns from a conversation is written back through the Memory Promotion Engine
- **SES-005 AI Studio (future)** — Voice OS and AI Studio will share a Multimodal Interaction Layer; the abstractions defined here become the foundation for avatar speech, live streaming narration, and future AR/VR interfaces

The architectural principle governing this document: **Voice OS is a platform service, not a product feature.** Every product — pielts, HCG POS, Mr. Yeti — accesses voice capabilities through the same Voice OS layer. This ensures consistent latency, consistent safety, consistent memory behavior, and consistent user experience across all products.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | Parts 1, 2, CSM | Core pipeline and state machine that every voice implementation uses |
| Voice / Real-time Engineers | Parts 2–4, 8 | Pipeline implementation, speaker identity, orchestration |
| Agent Engineers | Parts 3, 7, 9 | Conversation engine, safety, device integration |
| Product Architects | Parts 5, 10 | Emotion/prosody, future roadmap |
| Privacy / Governance | Parts 4, 7, 9 | Speaker identity, biometric data, voice safety policies |

---

## Reading Order

```
SES-002 Agent System (SafetyHarness, Agent Contracts)
SES-003 Memory (Context Assembly, Voice Memory)
        │
        ▼
SES-004 Voice OS  ← You are here
        │
        ├── SES-005 AI Studio (Avatar speech uses Voice OS TTS)
        ├── SES-006 Video Pipeline (Narration uses Voice OS)
        └── SES-007 Character System (Mr. Yeti voice persona uses Voice OS)
```

---

## Multimodal Interaction Layer (Architectural Foundation)

Before specifying Voice OS itself, this document establishes the abstraction it belongs to. Voice OS is the first instantiation of the Multimodal Interaction Layer — the shared foundation for all real-time human-facing interaction in SaathiAI.

```
┌─────────────────────────────────────────────────────────────────┐
│               MULTIMODAL INTERACTION LAYER (MIL)                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  Voice OS    │  │  AI Studio   │  │   Live Streaming      │ │
│  │  (SES-004)   │  │  (SES-005)   │  │   (SES-006 partial)   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬────────────┘ │
│         │                 │                      │              │
│  ┌──────▼─────────────────▼──────────────────────▼───────────┐ │
│  │              SHARED CAPABILITIES                           │ │
│  │  OmniVoice TTS │ Whisper STT │ Speaker Identity           │ │
│  │  Audio Buffer  │ VAD Engine  │ Prosody Controller         │ │
│  │  Pipecat       │ WebRTC      │ Audio I/O Abstraction      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

The MIL contract: any capability that produces or consumes audio in SaathiAI is built on the shared capabilities listed here. No product builds its own TTS integration, its own VAD, or its own audio buffer. Platform-first (AP-01) applies at the human interface layer exactly as it applies to agents and providers.

Future MIL extensions: Avatar Engine (SES-007), AR/VR Interface (future), Phone Call Automation (future).

---

## Document Structure

| Part | Title | The Question It Answers |
|------|-------|------------------------|
| 1 | Voice Philosophy | What is Voice OS trying to be? What are the non-negotiables? |
| 2 | Voice Pipeline | What happens to audio from microphone to speaker, and how fast? |
| 3 | Conversation Engine | How does continuous dialogue work? What makes it feel natural? |
| 4 | Speaker Identity | Who is speaking? How confident are we? What do we do with that? |
| 5 | Emotion & Prosody | How does Voice OS sound? How does it vary its vocal character? |
| 6 | Voice Memory | What does Voice OS remember? What does it learn? |
| 7 | Device Integration | Where does Voice OS run? What are the constraints per platform? |
| 8 | Real-Time Orchestration | How are the components wired together? What fails and how? |
| 9 | Safety | Which voice commands require confirmation? What is the emergency stop? |
| 10 | Future Voice | Real-time translation, multi-speaker, avatar sync, voice cloning |
| Appendix A | Conversation State Machine | Formal state definitions, transitions, timeouts |
| Appendix B | Voice Capability Matrix | What can each user tier do via voice? |

---

# Part 1 — Voice Philosophy

---

## 1.1 The Problem Voice Solves

A keyboard interface requires the user to stop, look, type, and wait. That workflow imposes a cognitive cost. It breaks the user's train of thought. It is particularly costly for users who are not native English typists — Nepali speakers, for example, may think fluidly in Nepali but must context-switch to type in English.

Voice removes that barrier. A user who is reviewing an IELTS response while practicing speaking should be able to say "how does this compare to a band 7?" without breaking stride. A canteen operator managing a lunch rush should be able to say "what's the inventory status for dal bhat?" without navigating screens. A content creator developing a Mr. Yeti script should be able to say "make the third paragraph more conversational" while walking.

Voice OS is the mechanism by which SaathiAI becomes accessible to users in motion, under time pressure, or in environments where screens are inconvenient.

---

## 1.2 Six Non-Negotiables

These are properties Voice OS must have. They are not features on a roadmap — they are definitional. A Voice OS that does not satisfy these is not Voice OS; it is a dictation tool.

---

**V-N1: Natural conversation.**

A natural conversation does not consist of discrete commands. It consists of turns, where each turn builds on the previous, where the system remembers what was said two minutes ago, and where a follow-up question ("what about for writing?") is understood in the context of the previous question about speaking scores.

Voice OS maintains a conversation window. Every utterance is understood in context. The system never requires the user to repeat themselves because it lost the thread.

---

**V-N2: Continuous dialogue.**

Once a conversation is started, it continues until explicitly ended or until a configurable silence timeout is reached. The user does not need to trigger the system for each turn. They speak when they are ready. The system listens.

This is in contrast to push-to-talk or command-response models, where the user must explicitly activate each interaction. Continuous dialogue feels like talking to a person. Push-to-talk feels like using a walkie-talkie.

---

**V-N3: Low latency.**

The time between the user finishing a sentence and hearing the beginning of the response must feel immediate. Human conversational tolerance for latency is approximately 500ms. Beyond that, conversations feel broken. Beyond 1,000ms, they feel like phone calls with bad connections.

Voice OS targets:

| Stage | Target | Hard Limit |
|-------|--------|-----------|
| VAD end-of-speech detection | < 50ms | 100ms |
| STT transcript (first token) | < 300ms | 600ms |
| Agent response (first token) | < 400ms | 800ms |
| TTS audio (first chunk) | < 150ms | 300ms |
| **Total first-audio latency** | **< 900ms** | **1,500ms** |

These are end-to-end targets measured from end-of-user-speech to start-of-system-audio. The targets are achievable with streaming throughout the pipeline — STT streams transcripts, agents stream tokens, TTS streams audio. No stage waits for the previous stage to complete before beginning.

---

**V-N4: Interruptibility (Barge-In).**

The user must be able to interrupt the system at any point during a response. If the system is speaking and the user starts talking, the system must immediately:
1. Detect the interruption via VAD
2. Stop audio playback
3. Begin processing the new utterance

A system that cannot be interrupted is not a conversation. It is a monologue. Users who cannot interrupt feel disrespected and lose trust in the interface.

Barge-in is the hardest technical problem in Voice OS. It requires echo cancellation (otherwise the system hears its own voice as a user interruption) and careful state management (the incomplete response must be tracked and recoverable).

---

**V-N5: Multilingual support.**

English and Nepali are the first two languages. The pipeline must:
1. Detect language automatically from the first few words of each utterance
2. Route to the appropriate STT model configuration
3. Process through agents (which respond in the same language)
4. Synthesize TTS in the detected language

Nepali support in 2026 is limited by available STT accuracy (Whisper medium achieves approximately 85% WER on accented Nepali speech). The platform accepts this limitation and adds it to the Voice Capability Matrix — users are informed when Nepali accuracy is lower than English.

---

**V-N6: Voice as primary interface, not an add-on.**

Voice OS is not a nice-to-have layer on top of a text-first product. It is an equal interface. Every capability exposed via the API must also be expressible via voice (subject to the safety constraints in Part 9). A feature that cannot be reached by voice is an accessibility gap.

This principle has a corollary: Voice OS cannot be built as a translation layer that converts voice to text and then calls the text API. That approach produces unacceptable latency and breaks the conversational context model. Voice OS requires a dedicated streaming pipeline.

---

## 1.3 What Voice OS Is Not

**Not a voice assistant.** Voice assistants (Siri, Alexa) are designed for one-shot commands. Voice OS is designed for extended dialogue. The interaction model is fundamentally different.

**Not a dictation tool.** Dictation converts speech to text and hands it to another system. Voice OS manages the full interaction loop including context, memory, safety, and multi-turn dialogue.

**Not a product-specific feature.** Voice OS is a platform service. It does not belong to pielts or Mr. Yeti. Those products call Voice OS through the shared MIL layer.

---

# Part 2 — Voice Pipeline

---

## 2.1 Full Pipeline Overview

```
MICROPHONE INPUT
      │
      ▼
┌─────────────────────────────────────────────────┐
│ STAGE 1: AUDIO CAPTURE                          │
│ Backend: PyAudio / WebAudio API (browser)       │
│ Format: PCM 16-bit, 16kHz, mono                 │
│ Buffer: 20ms chunks                             │
│ Latency target: < 5ms                           │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 2: ECHO CANCELLATION                      │
│ Backend: WebRTC AEC3 (browser) / SpeexDSP (mac) │
│ Purpose: Remove system's own TTS from input     │
│ Required for barge-in to function               │
│ Latency target: < 5ms (real-time)               │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 3: VOICE ACTIVITY DETECTION (VAD)         │
│ Backend: Silero VAD v4 (local, ~50ms inference) │
│ Threshold: speech_prob > 0.5                    │
│ Purpose: Detect speech start/end               │
│ Latency target: < 30ms detection               │
│ Failure: False triggers handled by Stage 7      │
└──────────────────────────┬──────────────────────┘
                           │
                  ┌────────┴─────────┐
                  │ Speech detected? │
                  └──────┬───────────┘
                    yes  │   no → continue buffering
                         ▼
┌─────────────────────────────────────────────────┐
│ STAGE 4: WAKE WORD DETECTION                    │
│ Backend: OpenWakeWord (local)                   │
│ Default word: "Baadar" / "Hey Baadar"           │
│ Required: only in IDLE state                    │
│ In ACTIVE CONVERSATION: skipped                 │
│ Latency target: < 50ms                          │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 5: STREAMING STT                          │
│ Backend: Whisper (local, Ollama) primary        │
│         Groq Whisper API fallback              │
│ Model: whisper-large-v3 (local)                 │
│         whisper-large-v3-turbo (Groq)           │
│ Streaming: partials emitted every 200ms         │
│ Language detection: from first 3 seconds        │
│ Latency target: first partial < 300ms           │
│ Failure: fall back to Groq within 500ms         │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 6: LANGUAGE DETECTION                     │
│ Backend: langdetect (local, from STT output)    │
│ Supported: en, ne (Nepali)                      │
│ Confidence threshold: 0.85                      │
│ Below threshold: prompt user to clarify         │
│ Latency target: < 20ms (post-STT)               │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 7: CONTEXT ASSEMBLY                       │
│ Backend: SES-003 ContextAssemblyEngine          │
│ Priority order: CSM state + conversation        │
│   window + user preferences + episodic +        │
│   semantic + knowledge graph                    │
│ Token budget: 1,200 (voice-optimized, tighter   │
│   than text API due to latency constraints)     │
│ Latency target: < 100ms                         │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 8: AGENT PROCESSING (SES-002)             │
│ Backend: BMA loop, routed by intent             │
│ Safety: SafetyHarness checks all tool calls     │
│ Streaming: tokens emitted as generated          │
│ LLM: Groq (standard) / Claude (reasoning)       │
│ Latency target: first token < 400ms             │
│ Failure: graceful apology response              │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 9: RESPONSE SHAPING                       │
│ Purpose: Adapt text response for speech         │
│ Operations:                                     │
│   - Remove markdown (**, ##, bullet points)     │
│   - Insert SSML pause markers                   │
│   - Expand abbreviations (e.g., "Band 7" → OK) │
│   - Detect sentence boundaries for streaming    │
│   - Truncate if > voice_max_tokens              │
│ Latency target: < 30ms                          │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 10: STREAMING TTS                         │
│ Backend: OmniVoice (local, port 8920) primary   │
│          Gemini TTS or ElevenLabs fallback      │
│ Voice persona: per product + per speaker role   │
│ Streaming: audio chunks emitted sentence-by-    │
│            sentence (< 150ms/sentence)          │
│ Latency target: first audio chunk < 150ms       │
│ Failure: fall back to cloud TTS within 300ms    │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ STAGE 11: AUDIO PLAYBACK                        │
│ Backend: PyAudio (native) / WebAudio (browser)  │
│ Buffer: 20ms jitter buffer                      │
│ Interrupt handling: immediately mutable         │
│ Barge-in: VAD running in parallel during play   │
│ Latency target: < 20ms from TTS chunk receipt  │
└─────────────────────────────────────────────────┘

SPEAKER OUTPUT
```

---

## 2.2 Pipeline as Python Interface

Every stage is a well-defined async generator or coroutine. The pipeline is composable:

```python
class VoicePipeline:
    def __init__(self, config: VoiceConfig, state_machine: ConversationStateMachine):
        self.config = config
        self.csm = state_machine

    async def run(self):
        audio_stream = AudioCapture(
            sample_rate=16000, chunk_ms=20, channels=1
        )
        echo_cancelled = EchoCanceller(audio_stream, reference=self.tts_output)
        vad = SileroVAD(echo_cancelled, threshold=0.5)
        wake_word = OpenWakeWord(vad, words=self.config.wake_words)
        stt = WhisperSTT(
            wake_word,
            model=self.config.stt_model,
            fallback=GroqWhisperSTT(),
        )
        lang_detected = LanguageDetector(stt, supported=["en", "ne"])
        context = ContextAssembler(lang_detected, engine=context_assembly_engine)
        agent_output = AgentProcessor(context, registry=AGENT_REGISTRY)
        shaped = ResponseShaper(agent_output)
        tts_chunks = OmniVoiceTTS(
            shaped,
            voice=self.config.voice_persona,
            fallback=GeminiTTS(),
        )
        self.tts_output = AudioPlayer(tts_chunks, interrupt_on_vad=True)

        await self.tts_output.run()
```

---

## 2.3 Streaming Contracts

Every stage in the pipeline emits and consumes streams. The contract:

```python
class AudioChunk(BaseModel):
    data: bytes              # PCM audio
    sample_rate: int = 16000
    timestamp_ms: int
    is_final: bool = False

class TranscriptChunk(BaseModel):
    text: str
    is_final: bool           # True = end of utterance
    confidence: float        # 0.0–1.0
    language: str            # "en" | "ne"
    timestamp_ms: int

class AgentTokenChunk(BaseModel):
    token: str
    is_final: bool
    intent: str | None       # Set on first token of each response
    timestamp_ms: int

class TTSAudioChunk(BaseModel):
    data: bytes              # PCM audio, 22050Hz, mono
    sentence_boundary: bool  # True if this chunk ends a sentence
    timestamp_ms: int
    duration_ms: int
```

No stage blocks waiting for a complete message. Partial results flow downstream immediately. This is what achieves the sub-900ms end-to-end latency target.

---

## 2.4 Stage Failure Handling

| Stage | Failure Mode | Recovery |
|-------|-------------|---------|
| Audio Capture | Device not found | Alert user; wait for device reconnect |
| Echo Cancellation | AEC failure | Continue without AEC; warn that barge-in may not work |
| VAD | No speech detected for 30s | Transition to IDLE state |
| Wake Word | False positive | Response shaper adds "Did you mean to say something?" if CSM detects confusion |
| STT (local) | Whisper timeout > 500ms | Fall back to Groq Whisper API |
| STT (Groq) | Rate limit / error | Return error phrase: "I didn't catch that — could you repeat it?" |
| Language Detection | Confidence < 0.85 | Default to English; note uncertainty in context |
| Context Assembly | > 200ms | Return partial context with L0+L1 only; skip L2/L3 |
| Agent Processing | Error / timeout > 2s | Apologize verbally: "I'm having trouble with that right now" |
| TTS (OmniVoice) | Latency > 300ms | Fall back to Gemini TTS |
| TTS (fallback) | Error | Deliver response as text only; log incident |
| Audio Playback | Device error | Alert user; retry with default device |

---

# Part 3 — Conversation Engine

---

## 3.1 The Conversational Model

A conversation is not a sequence of independent request-response pairs. It is a continuous, stateful exchange where each turn inherits context from all previous turns in the session.

Voice OS models a conversation as a **conversation window** — a sliding context of the last N turns, maintained in L0 Working Memory for the duration of a session and promoted to L1 Episodic Memory when the session ends.

```python
class ConversationWindow:
    def __init__(self, max_turns: int = 20, max_tokens: int = 4_000):
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self.max_tokens = max_tokens
        self.session_id: str = str(uuid4())
        self.started_at: datetime = datetime.utcnow()

    def add_user_turn(self, transcript: str, language: str) -> None:
        self.turns.append(ConversationTurn(
            role="user",
            content=transcript,
            language=language,
            timestamp=datetime.utcnow(),
        ))

    def add_assistant_turn(self, response: str, intent: str) -> None:
        self.turns.append(ConversationTurn(
            role="assistant",
            content=response,
            intent=intent,
            timestamp=datetime.utcnow(),
        ))

    def to_context(self) -> list[dict]:
        """Format for injection into Context Assembly Engine."""
        return [{"role": t.role, "content": t.content} for t in self.turns]

    def token_estimate(self) -> int:
        return sum(len(t.content.split()) * 1.3 for t in self.turns)

    def is_near_limit(self) -> bool:
        return self.token_estimate() > self.max_tokens * 0.8
```

---

## 3.2 Barge-In (Interruption Handling)

Barge-in is the ability to interrupt the system mid-response. It is technically the hardest capability in Voice OS and the one that most distinguishes it from a command-response system.

**The barge-in problem:**

When the system is speaking, the microphone also picks up the TTS audio. Without echo cancellation, VAD would detect the system's own voice as speech and trigger barge-in on every response. Echo cancellation (Stage 2 of the pipeline) removes the reference signal before VAD processes the audio.

**Barge-in state machine integration:**

Barge-in is a state transition: SPEAKING → INTERRUPTED. This transition is triggered when:
1. Echo-cancelled VAD detects speech probability > 0.7 for > 150ms during playback
2. The system immediately: stops TTS playback, cancels any in-flight TTS generation, and transitions to LISTENING state

**What happens to the interrupted response:**

The incomplete response is logged to the conversation window as a partial turn. The agent that was generating the response is notified of the interruption and marks its cycle as `outcome = "interrupted"`. The incomplete content is stored in the conversation window with flag `is_partial = True`.

When the user's new utterance is processed, the agent has access to the partial previous response. If the interruption was a clarification ("wait, did you mean..."), the agent can reference the partial response it was giving.

```python
class BargeinHandler:
    async def on_barge_in(
        self,
        playback: AudioPlayer,
        in_flight_response: AgentResponseStream,
        window: ConversationWindow,
    ) -> None:
        # Stop playback immediately
        await playback.stop()

        # Capture what was said so far
        partial_content = in_flight_response.content_so_far
        await in_flight_response.cancel()

        # Log the interrupted turn
        window.add_assistant_turn(
            response=partial_content,
            intent=in_flight_response.intent,
        )
        window.turns[-1].is_partial = True

        # Transition state machine
        await self.csm.transition(VoiceState.INTERRUPTED)
```

---

## 3.3 Turn Management

**Detecting end-of-user-turn:**

VAD detects speech probability, but end-of-turn detection is different from silence detection. A user may pause mid-sentence. A 200ms silence does not mean the turn is over.

Voice OS uses a two-signal approach:

1. **VAD silence duration**: if VAD detects no speech for > 600ms, the turn is tentatively complete
2. **Transcript completeness**: the STT partial transcript is evaluated for sentence completeness (ends with punctuation, or the language model predicts the utterance is complete)

Both signals must agree before the turn is passed to the agent. If VAD detects silence but the transcript appears mid-sentence, Voice OS waits an additional 300ms before confirming end-of-turn.

```python
class TurnDetector:
    SILENCE_THRESHOLD_MS = 600
    SENTENCE_COMPLETENESS_THRESHOLD = 0.8

    async def detect_end_of_turn(
        self, vad_stream: VADStream, transcript_stream: TranscriptStream
    ) -> TranscriptChunk:
        silence_ms = 0
        last_chunk: TranscriptChunk | None = None

        async for chunk in transcript_stream:
            last_chunk = chunk
            if not chunk.is_final:
                silence_ms = 0  # Reset on any speech
                continue

            silence_ms += chunk.duration_ms
            if silence_ms >= self.SILENCE_THRESHOLD_MS:
                completeness = await self._score_completeness(chunk.text)
                if completeness >= self.SENTENCE_COMPLETENESS_THRESHOLD:
                    return chunk
                # Incomplete sentence — wait a bit more
                if silence_ms >= self.SILENCE_THRESHOLD_MS + 300:
                    return chunk  # Give up waiting; process what we have

        return last_chunk
```

---

## 3.4 Follow-Up Context

A follow-up question must be understood in the context of the previous turn. "What about for writing?" after a discussion about speaking scores must be understood as "What is the IELTS writing band score requirement equivalent?" — not as a literal standalone question.

Voice OS injects the conversation window into every Context Assembly call. The agent always sees the last 20 turns of dialogue. For follow-up resolution, the agent uses the conversation window to fill in implicit references.

**Pronoun and reference resolution:**

Common follow-up patterns:
- "What about for [X]?" → X refers to a different aspect of the same topic discussed previously
- "Can you give me another example?" → refers to the type of example just provided
- "Make that shorter" → refers to the response just given
- "In Nepali please" → apply language switch to next response

These are handled by the agent's reasoning phase (SES-002, Understand Phase) with the conversation window as context.

---

## 3.5 Silence Handling

| Silence Duration | State | Action |
|-----------------|-------|--------|
| 0–600ms | LISTENING | Wait; VAD continues |
| 600ms–3s | LISTENING | Tentative end-of-turn; process if transcript complete |
| 3s–8s (in ACTIVE CONVERSATION) | WAITING | Soft prompt: "Still there?" or just wait |
| 8s–30s (in ACTIVE CONVERSATION) | IDLE_PENDING | System stops listening actively; waits for wake word or movement |
| > 30s | IDLE | Session ends; conversation window promoted to L1 |
| > 30s (during important workflow) | PAUSED | CEO Agent notified; Telegram message sent |

---

## 3.6 Confirmation Strategies

Some voice commands require explicit confirmation before execution (see Part 9 — Safety). Voice OS uses one of three confirmation strategies:

**Verbal confirmation (default for L3 MODIFY actions):**
> "I'll reschedule that content post from Tuesday to Thursday. Should I go ahead?"
> User: "Yes" / "Go ahead" / "No wait" / "Cancel"

**Repeat-back confirmation (for L4 EXTERNAL actions):**
> "Just to confirm — you want me to send the Telegram update to subscribers now. That's the message starting with 'New IELTS practice test available.' Is that right?"
> User must confirm the content, not just the action.

**Code confirmation (for L5 CRITICAL actions):**
> "This will deploy to production. Please say your confirmation code."
> User: [speaks the code set during enrollment]
> System verifies spoken code against enrolled voice + PIN combination.

If the user is in the middle of a confirmation flow and goes silent for > 10s, the action is **automatically cancelled** and Voice OS speaks: "I've cancelled that action since I didn't hear a confirmation."

---

# Part 4 — Speaker Identity

---

## 4.1 Why Speaker Identity Matters for Voice OS

Speaker identity is the voice equivalent of authentication. Without it, anyone who can speak to a SaathiAI device can:
- Access the operator's memory and personal data
- Trigger automations
- Modify platform configuration
- Approve production actions

The Voice Capability Matrix (Appendix B) is only enforceable if Voice OS knows who is speaking. Speaker identity transforms voice from an open channel into an authenticated one.

---

## 4.2 Speaker Tiers

| Tier | Identity Verification | Capabilities |
|------|--------------------|-------------|
| **GUEST** | No verification | General conversation only; read-only memory; no automations |
| **VERIFIED USER** | Voice fingerprint match (confidence ≥ 0.85) | Full personal capabilities; query memory; trigger non-critical automations |
| **ADMIN** | Voice fingerprint + confirmation code | All capabilities including production actions |

Tier assignment happens automatically at conversation start. The system identifies the speaker within the first 2–3 seconds of speech (after collecting enough audio for fingerprint comparison).

---

## 4.3 Voice Enrollment

Enrollment is a one-time process performed in a quiet environment. It cannot be completed via voice — it requires the setup UI to ensure enrollment quality.

```python
class VoiceEnrollment:
    REQUIRED_PHRASES = 5
    MIN_DURATION_PER_PHRASE_MS = 2000
    TARGET_SNR_DB = 15

    async def enroll(
        self, user_id: str, tier: SpeakerTier
    ) -> EnrollmentResult:
        audio_samples: list[AudioChunk] = []

        for i, prompt in enumerate(ENROLLMENT_PROMPTS):
            # Display prompt: "Please say: '...'"
            sample = await self._record_phrase(
                prompt=prompt,
                min_duration_ms=self.MIN_DURATION_PER_PHRASE_MS,
            )
            quality = await self._check_quality(sample)
            if quality.snr_db < self.TARGET_SNR_DB:
                raise EnrollmentQualityError(
                    f"Too much background noise. SNR: {quality.snr_db}dB, "
                    f"required: {self.TARGET_SNR_DB}dB"
                )
            audio_samples.append(sample)

        embedding = await self._compute_embedding(audio_samples)

        # Store embedding — biometric data stays on device
        await biometric_store.save(
            user_id=user_id,
            embedding=embedding,
            tier=tier,
            enrolled_at=datetime.utcnow(),
        )

        return EnrollmentResult(success=True, user_id=user_id, tier=tier)

ENROLLMENT_PROMPTS = [
    "I use SaathiAI every day to manage my work.",
    "Baadar, what's on my schedule for today?",
    "Please send the morning report to the team.",
    "The quick brown fox jumps over the lazy dog.",
    "My voice is my password for SaathiAI.",
]
```

**Biometric storage policy:** Voice embeddings are stored locally only. They never leave the device. Cloud backup of voice embeddings requires explicit opt-in and is disabled by default. This is the same policy as OmniVoice (noted in SES-001 Part 8).

---

## 4.4 Speaker Verification

```python
class SpeakerVerifier:
    CONFIDENCE_THRESHOLD = 0.85
    GUEST_FALLBACK_THRESHOLD = 0.6

    async def verify(
        self, audio_sample: list[AudioChunk]
    ) -> SpeakerVerificationResult:
        embedding = await self._compute_embedding(audio_sample)
        enrolled_users = await biometric_store.get_all()

        best_match: EnrolledUser | None = None
        best_score: float = 0.0

        for user in enrolled_users:
            score = cosine_similarity(embedding, user.embedding)
            if score > best_score:
                best_score = score
                best_match = user

        if best_score >= self.CONFIDENCE_THRESHOLD:
            return SpeakerVerificationResult(
                user_id=best_match.user_id,
                tier=best_match.tier,
                confidence=best_score,
                verified=True,
            )
        elif best_score >= self.GUEST_FALLBACK_THRESHOLD:
            # Recognizable but below threshold — treat as guest with soft flag
            return SpeakerVerificationResult(
                user_id=None,
                tier=SpeakerTier.GUEST,
                confidence=best_score,
                verified=False,
                note="Possible user match; below confidence threshold",
            )
        else:
            return SpeakerVerificationResult(
                user_id=None,
                tier=SpeakerTier.GUEST,
                confidence=best_score,
                verified=False,
            )
```

---

## 4.5 Multiple Authorized Users

Voice OS supports multiple enrolled users on the same device. This is relevant for the HCG canteen scenario (multiple staff members) and the pielts classroom scenario (teacher + student).

Each enrolled user has their own voice embedding, their own speaker tier, and their own conversation memory. When a new person speaks, Voice OS re-identifies them and loads their profile automatically — no explicit login required.

**Conflict resolution:** if two people speak simultaneously (which VAD will detect as overlapping energy patterns), Voice OS speaks: "I can only help one person at a time. Who should I respond to?" and waits for one voice to become dominant.

---

## 4.6 Guest Mode

A guest user (unrecognized voice) gets access to general conversation only. Their conversation is not saved to L1 Episodic Memory by default. If a guest wants their session saved, they must say "remember this conversation" — Voice OS then prompts them to give a name for the guest session.

---

# Part 5 — Emotion & Prosody

---

## 5.1 Why Prosody Matters

A technically correct response delivered in a monotone voice is worse than a slightly imperfect response delivered with warmth and appropriate emphasis. Prosody — pitch, rate, pauses, emphasis, emotional register — is what makes synthesized speech feel like communication rather than text-to-speech output.

Voice OS controls prosody at two levels:
1. **SSML-level** — pause durations, pitch modulation, rate, emphasis on specific words
2. **Persona-level** — the voice character associated with each product (Baadar's voice, Mr. Yeti's voice, the pielts coach voice)

---

## 5.2 Voice Personas

Each product has a defined voice persona. Personas are not just voice samples — they are complete speaking styles.

```python
class VoicePersona(BaseModel):
    name: str
    voice_id: str              # OmniVoice clone ID
    fallback_voice_id: str     # Cloud TTS voice ID
    speaking_rate: float       # 1.0 = normal, 0.9 = slightly slower for clarity
    pitch_shift: float         # Semitones from baseline (0.0 = no change)
    energy_level: float        # 0.0–1.0; affects TTS energy injection

    # Emotional registers
    registers: dict[str, RegisterConfig]

    # Pause behavior
    sentence_pause_ms: int = 200
    paragraph_pause_ms: int = 400
    list_item_pause_ms: int = 150
    ellipsis_pause_ms: int = 500

VOICE_PERSONAS = {
    "baadar": VoicePersona(
        name="Baadar",
        voice_id="omnivoice-baadar-v2",
        fallback_voice_id="gemini-journey-d",
        speaking_rate=1.05,       # Slightly faster — energetic operator assistant
        pitch_shift=0.0,
        energy_level=0.75,
        sentence_pause_ms=180,
        registers={
            "default": RegisterConfig(rate=1.05, pitch=0.0, energy=0.75),
            "alert":   RegisterConfig(rate=1.1, pitch=1.5, energy=0.9),
            "calm":    RegisterConfig(rate=0.95, pitch=-0.5, energy=0.6),
            "success": RegisterConfig(rate=1.1, pitch=2.0, energy=0.9),
        }
    ),
    "mr_yeti": VoicePersona(
        name="Mr. Yeti",
        voice_id="omnivoice-mryeti-v1",
        fallback_voice_id="gemini-journey-o",
        speaking_rate=0.95,       # Slightly slower — teacher, clear articulation
        pitch_shift=-1.0,         # Slightly lower — warm, authoritative
        energy_level=0.7,
        sentence_pause_ms=250,    # More deliberate pauses — pedagogical effect
        registers={
            "default":    RegisterConfig(rate=0.95, pitch=-1.0, energy=0.7),
            "encourage":  RegisterConfig(rate=1.0, pitch=1.0, energy=0.8),
            "correct":    RegisterConfig(rate=0.9, pitch=-1.5, energy=0.65),
            "celebrate":  RegisterConfig(rate=1.1, pitch=2.5, energy=0.95),
            "explain":    RegisterConfig(rate=0.88, pitch=-0.5, energy=0.65),
        }
    ),
    "pielts_coach": VoicePersona(
        name="pielts Coach",
        voice_id="omnivoice-coach-v1",
        fallback_voice_id="gemini-journey-f",
        speaking_rate=0.92,       # Clear, considered
        pitch_shift=0.5,
        energy_level=0.65,
        sentence_pause_ms=280,
        registers={
            "default":   RegisterConfig(rate=0.92, pitch=0.5, energy=0.65),
            "feedback":  RegisterConfig(rate=0.88, pitch=0.0, energy=0.6),
            "question":  RegisterConfig(rate=0.95, pitch=1.5, energy=0.7),
            "example":   RegisterConfig(rate=0.85, pitch=-0.5, energy=0.6),
        }
    ),
}
```

---

## 5.3 Context-Aware Register Selection

The Response Shaper (Stage 9 of the pipeline) determines the emotional register of the response and injects it into the TTS call.

```python
class RegisterSelector:
    async def select(
        self, response_text: str, intent: str, agent_context: dict
    ) -> str:
        # Check for explicit register signals
        if any(word in response_text.lower() for word in ["great", "excellent", "well done", "perfect"]):
            return "celebrate"
        if intent in ["correction", "feedback", "error_explanation"]:
            return "correct"
        if intent in ["encouragement", "motivation"]:
            return "encourage"
        if intent in ["explanation", "teaching"]:
            return "explain"
        if agent_context.get("is_alert"):
            return "alert"
        return "default"
```

---

## 5.4 SSML Annotation

Before TTS synthesis, the Response Shaper annotates the text with SSML markers:

```python
class SSMLAnnotator:
    def annotate(self, text: str, persona: VoicePersona, register: str) -> str:
        reg = persona.registers[register]

        # Wrap in speak + prosody envelope
        ssml = f'<speak><prosody rate="{reg.rate}" pitch="{reg.pitch:+.1f}st">'

        # Sentence boundaries → pauses
        text = re.sub(r'\. ', f'. <break time="{persona.sentence_pause_ms}ms"/> ', text)
        text = re.sub(r'\n\n', f'<break time="{persona.paragraph_pause_ms}ms"/>', text)

        # Emphasis on capitalized important words
        text = re.sub(
            r'\b(IELTS|Band [0-9]|[A-Z]{3,})\b',
            r'<emphasis level="moderate">\1</emphasis>',
            text,
        )

        # Numbers → slow down for clarity
        text = re.sub(
            r'\b(\d+\.?\d*)\b',
            r'<prosody rate="0.85">\1</prosody>',
            text,
        )

        ssml += text + '</prosody></speak>'
        return ssml
```

---

## 5.5 Speaking Rate Adaptation

Voice OS monitors comprehension signals and adapts speaking rate over a session:

| Signal | Rate Adjustment |
|--------|----------------|
| User says "slower" / "too fast" | rate -= 0.05 (minimum 0.75) |
| User says "faster" / "too slow" | rate += 0.05 (maximum 1.2) |
| User asks for repeat > 3× in session | rate -= 0.05 |
| User is confirmed Nepali speaker | rate -= 0.03 (initial adjustment) |
| User regularly interrupts | rate += 0.03 (they can keep up) |

Rate adjustments are saved to L2 Semantic Memory as user preferences and applied in future sessions.

---

# Part 6 — Voice Memory

---

## 6.1 How Voice OS Interacts with SES-003 Memory

Voice OS is both a consumer and a producer of platform memory. It consumes memory to provide contextual, personalized responses. It produces memory through every conversation — building a richer understanding of the user over time.

```
SES-003 Memory System
        ▲               ▼
        │               │
   Memory writes    Memory reads
        │               │
        ▼               ▲
    VOICE OS
   (consumer + producer)
```

---

## 6.2 What Voice OS Remembers

| Memory Type | What | Where Stored | Lifetime |
|------------|------|-------------|---------|
| Conversation turns | Every turn in the current session | L0 Working Memory (deque) | Session only |
| Session summary | Compressed summary of what was discussed | L1 Episodic Memory | 90 days |
| Speaking preferences | Rate, language, persona preference | L2 Semantic Memory | Permanent |
| Pronunciation corrections | "It's 'Ajay', not 'Ah-jay'" | L2 Semantic Memory | Permanent |
| Frequently asked topics | Topics user returns to repeatedly | L2 Semantic Memory | Permanent |
| Wake word personalization | Custom wake word per user | L2 Semantic Memory | Until changed |
| Voice fingerprint | Speaker embedding | Biometric store (local only) | Until un-enrolled |

---

## 6.3 Session Promotion

At the end of each voice session, Voice OS promotes the conversation to L1 and optionally summarizes to L2:

```python
class SessionPromoter:
    async def promote(
        self, window: ConversationWindow, user_id: str, product: str
    ) -> None:
        # Write full conversation to L1
        await episodic_memory.write(EpisodicEntry(
            agent="voice_os",
            department="voice",
            product=product,
            user_id=user_id,
            session_id=window.session_id,
            intent="voice_conversation",
            content=window.to_text_log(),
            outcome="success",
            created_at=window.started_at,
            expires_at=datetime.utcnow() + timedelta(days=90),
        ))

        # Extract preferences and corrections
        preferences = await self._extract_preferences(window)
        for pref in preferences:
            await semantic_memory.upsert(pref)

        # If session was substantive (> 10 turns), create a summary
        if len(window.turns) > 10:
            summary = await self._summarize_session(window)
            await semantic_memory.write(SemanticPattern(
                pattern_key=f"session_summary_{window.session_id}",
                category="conversation",
                scope=f"product:{product}",
                pattern_value=summary,
                confidence=1.0,
                source_episodic_ids=[window.session_id],
            ))
```

---

## 6.4 Pronunciation Memory

When a user corrects pronunciation, Voice OS learns it permanently:

**User:** "It's pronounced 'Tribhuvan', not 'Tribh-oo-van'."

```python
class PronunciationMemory:
    async def learn_correction(
        self, wrong: str, right: str, phonetic: str, user_id: str
    ) -> None:
        await semantic_memory.upsert(SemanticPattern(
            pattern_key=f"pronunciation_{wrong.lower().replace(' ', '_')}",
            category="preference",
            scope=f"user:{user_id}",
            pattern_value=json.dumps({
                "word": wrong,
                "correct_pronunciation": right,
                "phonetic": phonetic,
                "learned_at": datetime.utcnow().isoformat(),
            }),
            confidence=1.0,
        ))
        # Also write to SSML lexicon file for TTS
        await ssml_lexicon.add(word=wrong, phoneme=phonetic)
```

---

## 6.5 Wake Word Personalization

Users can set custom wake words (subject to a minimum phoneme distinctiveness check):

**User:** "From now on, call yourself 'Hey Yeti' instead of 'Hey Baadar'."

```python
class WakeWordManager:
    MIN_PHONEME_COUNT = 4

    async def set_custom_wake_word(
        self, phrase: str, user_id: str
    ) -> WakeWordResult:
        phonemes = await phoneme_counter.count(phrase)
        if phonemes < self.MIN_PHONEME_COUNT:
            return WakeWordResult(
                success=False,
                reason=f"Wake word too short. Need at least {self.MIN_PHONEME_COUNT} phonemes.",
            )

        # Register with OpenWakeWord
        model_path = await open_wake_word.train_custom(
            phrase=phrase,
            user_id=user_id,
        )

        # Save preference
        await semantic_memory.upsert(SemanticPattern(
            pattern_key=f"wake_word_{user_id}",
            category="preference",
            scope=f"user:{user_id}",
            pattern_value=json.dumps({
                "phrase": phrase,
                "model_path": str(model_path),
            }),
            confidence=1.0,
        ))

        return WakeWordResult(success=True, phrase=phrase)
```

---

# Part 7 — Device Integration

---

## 7.1 Supported Environments

Voice OS is a platform service that runs in multiple deployment environments. Each environment has different audio I/O constraints, latency profiles, and capability availability.

```
app/voice/
├── __init__.py
├── pipeline.py          # Core pipeline (environment-agnostic)
├── state_machine.py     # Conversation State Machine
├── conversation.py      # ConversationWindow, TurnDetector
├── speaker_identity.py  # Enrollment, verification
├── prosody.py           # Personas, SSML, register selection
├── memory.py            # SessionPromoter, PronunciationMemory
├── adapters/
│   ├── browser.py       # WebAudio, WebRTC, WebSockets
│   ├── macos.py         # PyAudio, CoreAudio, SpeexDSP
│   ├── mobile_pwa.py    # MediaStream API, Service Workers
│   └── desktop.py       # PyAudio with GUI integration
└── backends/
    ├── stt/
    │   ├── whisper_local.py
    │   └── groq_whisper.py
    ├── tts/
    │   ├── omnivoice.py
    │   └── gemini_tts.py
    └── vad/
        └── silero.py
```

---

## 7.2 Environment Capability Matrix

| Capability | Browser | Mobile PWA | macOS | Desktop |
|-----------|---------|-----------|-------|---------|
| Microphone access | ✓ (HTTPS only) | ✓ (permission) | ✓ | ✓ |
| WebAudio API | ✓ | ✓ | N/A | N/A |
| Echo cancellation | WebRTC AEC3 | WebRTC AEC3 | SpeexDSP | SpeexDSP |
| Local Whisper | ✗ | ✗ | ✓ | ✓ |
| Groq Whisper | ✓ | ✓ | ✓ (fallback) | ✓ (fallback) |
| OmniVoice (local) | via localhost | ✗ | ✓ | ✓ |
| OmniVoice (remote) | ✓ | ✓ | ✓ | ✓ |
| Speaker verification | via API | via API | local | local |
| Biometric local storage | ✗ | ✗ | ✓ | ✓ |
| Wake word detection | ✓ (JS model) | ✗ | ✓ | ✓ |
| Background listening | ✗ | ✗ | ✓ | ✓ |
| Max audio latency | +50ms | +80ms | +10ms | +10ms |

---

## 7.3 Browser Adapter

```python
# app/voice/adapters/browser.py

class BrowserVoiceAdapter:
    """
    Bridges the Voice OS pipeline to WebRTC/WebSocket for browser clients.
    The browser handles audio capture; this adapter manages the server side.
    """

    async def handle_websocket(self, websocket: WebSocket):
        session_id = str(uuid4())
        window = ConversationWindow()
        csm = ConversationStateMachine(session_id=session_id)

        await csm.transition(VoiceState.WAKE_LISTENING)

        async for message in websocket.iter_bytes():
            audio_chunk = AudioChunk.from_bytes(message)

            match csm.state:
                case VoiceState.IDLE:
                    pass  # Ignore audio in idle

                case VoiceState.WAKE_LISTENING:
                    if await wake_word.detect(audio_chunk):
                        await csm.transition(VoiceState.ACTIVE_CONVERSATION)
                        await websocket.send_json({"event": "wake_word_detected"})

                case VoiceState.LISTENING:
                    transcript = await stt.process(audio_chunk)
                    if transcript.is_final:
                        await csm.transition(VoiceState.THINKING)
                        response = await self._process_utterance(
                            transcript, window, csm
                        )
                        async for tts_chunk in response:
                            await websocket.send_bytes(tts_chunk.data)
                        await csm.transition(VoiceState.LISTENING)

                case VoiceState.SPEAKING:
                    if await vad.detect_speech(audio_chunk):
                        await csm.transition(VoiceState.INTERRUPTED)
                        await websocket.send_json({"event": "barge_in"})
```

---

## 7.4 macOS Adapter

```python
# app/voice/adapters/macos.py

class MacOSVoiceAdapter:
    """
    Native macOS adapter. Uses CoreAudio via PyAudio.
    Supports background listening (always-on).
    """

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.aec = SpeexAEC(sample_rate=16000, frame_size=320)
        self.device_id = self._find_best_microphone()

    def _find_best_microphone(self) -> int:
        info = self.audio.get_host_api_info_by_index(0)
        for i in range(info.get('deviceCount')):
            dev = self.audio.get_device_info_by_index(i)
            if dev.get('maxInputChannels') > 0:
                if 'AirPods' in dev.get('name', '') or dev.get('defaultSampleRate') == 44100:
                    return i
        return self.audio.get_default_input_device_info()['index']
```

---

## 7.5 Future: Smart Speaker Integration

Smart speaker support (Phase 5+) requires:
- A network-accessible VAD+Wake Word service running on the speaker firmware
- WebSocket connection from speaker to Voice OS server
- Audio streaming over the local network (not internet, for privacy)
- No biometric data leaves the local network

The browser adapter's WebSocket protocol is already compatible with this requirement — smart speaker integration is a matter of implementing the client side.

## 7.6 Future: Telephone Integration

Phone call automation (Phase 6+) via Twilio or similar:
- Inbound calls routed to Voice OS via SIP/PSTN
- Audio quality constraints: G.711 codec, 8kHz sample rate (vs. 16kHz standard)
- Whisper model retrained/fine-tuned on 8kHz audio
- Different turn management (no VAD-based barge-in over phone; use DTMF confirmation)

---

# Part 8 — Real-Time Orchestration

---

## 8.1 Pipecat Integration

Pipecat is the open-source real-time voice AI framework that handles:
- Audio stream management
- Pipeline frame passing
- WebRTC transport
- Processor chain composition

Voice OS uses Pipecat as its orchestration layer. The pipeline defined in Part 2 maps directly to Pipecat's `Pipeline` → `Processor` chain:

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.services.silero import SileroVADAnalyzer
from pipecat.services.openai import OpenAIWhisperSTTService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.network.websocket_server import WebsocketServerTransport

class SaathiVoicePipeline:
    async def build(self, config: VoiceConfig) -> Pipeline:
        transport = WebsocketServerTransport(
            host="0.0.0.0",
            port=config.websocket_port,
            params=WebsocketServerParams(audio_out_enabled=True),
        )

        vad = SileroVADAnalyzer(params=VADParams(threshold=0.5))

        stt = (
            WhisperLocalSTT(model=config.stt_model)
            if config.use_local_stt
            else GroqWhisperSTT(api_key=config.groq_api_key)
        )

        tts = (
            OmniVoiceTTS(host="localhost", port=8920, voice_id=config.voice_persona)
            if config.use_local_tts
            else GeminiTTS(api_key=config.gemini_api_key)
        )

        context_processor = VoiceContextProcessor(
            assembly_engine=context_assembly_engine,
            window=ConversationWindow(),
        )

        agent_processor = VoiceAgentProcessor(
            registry=AGENT_REGISTRY,
            csm=self.csm,
        )

        response_shaper = ResponseShaper(persona=config.persona)

        pipeline = Pipeline([
            transport.input(),
            vad,
            stt,
            LanguageDetector(),
            context_processor,
            agent_processor,
            response_shaper,
            tts,
            transport.output(),
        ])

        return pipeline

    async def run(self, config: VoiceConfig):
        pipeline = await self.build(config)
        runner = PipelineRunner()
        await runner.run(pipeline)
```

---

## 8.2 WebRTC Transport

For browser clients, WebRTC provides:
- Low-latency, bidirectional audio
- Built-in echo cancellation (AEC3)
- Packet loss concealment
- STUN/TURN for NAT traversal

```python
class WebRTCTransportConfig:
    stun_servers: list[str] = ["stun:stun.l.google.com:19302"]
    turn_server: str | None = None    # Self-hosted if needed (Phase 3+)
    codec: str = "opus"               # Opus codec: 48kHz, 60ms frames
    bitrate_kbps: int = 32            # Low bandwidth; voice only
    dtls: bool = True                 # Encrypted media
    ice_transport_policy: str = "all" # "relay" for strict corporate NAT
```

---

## 8.3 Audio Buffering

The audio buffer manages the flow between pipeline stages:

```python
class AudioBuffer:
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_ms: int = 20,
        jitter_buffer_ms: int = 40,
    ):
        self.chunk_samples = int(sample_rate * chunk_ms / 1000)
        self.jitter_samples = int(sample_rate * jitter_buffer_ms / 1000)
        self._buffer: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=50)
        self._jitter: deque[AudioChunk] = deque(maxlen=2)

    async def write(self, chunk: AudioChunk) -> None:
        try:
            self._buffer.put_nowait(chunk)
        except asyncio.QueueFull:
            # Drop oldest chunk to prevent buffer overflow
            try:
                self._buffer.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self._buffer.put(chunk)

    async def read(self) -> AudioChunk:
        return await self._buffer.get()
```

---

## 8.4 Streaming API

The Voice OS API exposes two endpoints:

```
WebSocket: ws://localhost:8765/voice/stream
    Input:  binary frames (PCM audio, 16bit, 16kHz)
    Output: binary frames (PCM audio, 16bit, 22050Hz) interleaved with
            JSON control frames ({"type": "event", "event": "..."})

REST: POST /api/v1/voice/utterance
    Input:  {"audio_b64": "<base64-encoded PCM>", "session_id": "<id>"}
    Output: {"audio_b64": "<response audio>", "transcript": "...", "duration_ms": 1240}
    (Single-turn, no streaming — for low-latency-tolerant use cases)
```

Control events on the WebSocket:
```json
{"type": "event", "event": "wake_word_detected"}
{"type": "event", "event": "speaking_started"}
{"type": "event", "event": "speaking_ended"}
{"type": "event", "event": "barge_in"}
{"type": "event", "event": "confirmation_required", "action": "...", "details": "..."}
{"type": "event", "event": "session_ended"}
{"type": "event", "event": "error", "code": "...", "message": "..."}
```

---

## 8.5 Reconnection

Network interruptions are handled with exponential backoff reconnection:

```python
class VoiceSessionManager:
    MAX_RECONNECT_ATTEMPTS = 5
    BASE_BACKOFF_MS = 500

    async def maintain_session(self, session_id: str) -> None:
        attempts = 0
        while attempts < self.MAX_RECONNECT_ATTEMPTS:
            try:
                await self._connect_and_run(session_id)
                attempts = 0  # Reset on successful connection
            except (WebSocketDisconnect, ConnectionError) as e:
                attempts += 1
                backoff = self.BASE_BACKOFF_MS * (2 ** attempts)
                logger.warning(
                    f"Voice session {session_id} disconnected. "
                    f"Reconnect attempt {attempts} in {backoff}ms. Error: {e}"
                )
                await asyncio.sleep(backoff / 1000)

        # Max reconnects exceeded — save session state and notify
        await self._save_session_state(session_id)
        await telegram.send(
            f"Voice session {session_id} lost after "
            f"{self.MAX_RECONNECT_ATTEMPTS} reconnect attempts."
        )
```

---

## 8.6 Network Degradation Handling

| Condition | Detection | Response |
|-----------|----------|---------|
| Latency > 300ms | WebSocket RTT measurement | Switch from local STT to Groq (faster cloud inference) |
| Packet loss > 5% | RTCP statistics | Switch WebRTC codec from Opus to G.711 |
| Bandwidth < 16kbps | Buffer underruns | Reduce TTS audio quality (22kHz → 16kHz → 8kHz) |
| Complete disconnect | WebSocket close | Save conversation window; await reconnect |
| Server CPU > 85% | System metrics | Queue utterances; speak "Give me a moment" |

---

# Part 9 — Safety

---

## 9.1 Voice Safety Principles

The SafetyHarness (SES-002 Part 6) governs all agent tool calls. Voice OS adds voice-specific safety policies on top of that foundation.

**V-S1: Voice commands have the same safety levels as API commands.** A spoken "deploy to production" has exactly the same L5 CRITICAL classification as an API call to `deploy_to_production`. Speaker tier determines the maximum capability, not the invocation channel.

**V-S2: Safety level cannot be escalated by urgency.** "This is urgent, just deploy it" does not change the safety level. Urgency is not a bypass mechanism.

**V-S3: Confirmation must be verbal, not non-verbal.** A long pause after a confirmation request is not a yes. The user must speak a clear affirmative.

**V-S4: False confidence is worse than no action.** If speaker verification fails, Voice OS defaults to GUEST tier. It does not ask for a password verbally (passwords should not be spoken aloud). It informs the user that it cannot verify their identity and explains how to re-enroll.

---

## 9.2 Voice-Specific Sensitive Commands

In addition to the SafetyHarness L1–L5 classification, the following commands require voice-specific confirmation regardless of their SafetyHarness level:

| Command Pattern | Additional Requirement | Reason |
|-----------------|----------------------|--------|
| Any action involving money or payments | Repeat-back confirmation | Financial irreversibility |
| Sending messages to external recipients | Repeat-back with content preview | Accidental send risk |
| Deleting data | Repeat-back with item name | Irreversible |
| Changing platform configuration | Verbal "yes I'm sure" after a 3s pause | Deliberate action signal |
| Triggering scheduled automations | Confirmation of schedule time | Schedule confusion risk |
| Commands during high-background-noise sessions | Verification question | Mishear risk |

---

## 9.3 Emergency Stop

Voice OS implements a hardware-level emergency stop accessible at all times:

**Verbal:** Saying "Stop everything" or "Cancel all" at any time — including during a barge-in — immediately:
1. Stops all audio playback
2. Cancels all in-flight agent processing
3. Cancels all pending tool calls (even those already sent to external APIs where possible)
4. Transitions to IDLE state
5. Logs the emergency stop event with full context

**Keyboard:** Pressing the configured emergency stop hotkey (default: Cmd+Shift+. on macOS) triggers the same sequence.

```python
class EmergencyStop:
    STOP_PHRASES = [
        "stop everything", "cancel all", "abort", "stop",
        "रोक",  # Nepali: stop
        "बन्द गर",  # Nepali: close/stop
    ]

    async def check(self, transcript: str) -> bool:
        clean = transcript.lower().strip().rstrip(".")
        return any(phrase in clean for phrase in self.STOP_PHRASES)

    async def execute(self, pipeline: VoicePipeline) -> None:
        await pipeline.stop_all()
        await safety_audit_log.write(
            event_type="EMERGENCY_STOP",
            triggered_by="voice",
            context=pipeline.current_context,
        )
        await pipeline.speak("Everything stopped.")
```

---

## 9.4 Spoofing Detection

Voice spoofing — playing a recording of an authorized user's voice to gain access — is a meaningful threat if the system is used in a shared space.

**Detection approach (Phase 2):**

Replay attack detection uses liveness detection signals:
1. **Anti-spoofing embedding** — a secondary voice model trained to distinguish live speech from recordings (different spectral characteristics, no room acoustics matching)
2. **Randomized challenge** — during verification, the system asks the user to speak a random phrase that was not in the enrollment set. Recordings cannot respond to dynamic challenges.
3. **Ambient noise coherence** — a live speaker's voice has coherent noise from their environment. A recording played in a room has two layers of noise.

Phase 1 (before anti-spoofing model is available): inform users that speaker verification is probabilistic, not biometric-grade, and that CRITICAL actions require additional out-of-band confirmation.

---

## 9.5 Background Voice Filtering

In noisy environments (canteen, classroom), multiple voices may be present. Voice OS filters background speech using:

1. **Spatial audio filtering** (hardware-dependent): if the device has multiple microphones, beamforming focuses on the closest speaker
2. **Speaker diarization** (Phase 3): identify which voice segments belong to which speaker; process only the dominant speaker
3. **Wake word filter**: in WAKE_LISTENING state, only process audio that followed the wake word; discard ambient speech

---

# Part 10 — Future Voice

---

## 10.1 Real-Time Translation

Real-time translation enables a conversation in one language to be replied to in another, or translating a conversation in real-time for a third party.

**Use case:** A pielts student speaks in Nepali; the teacher hears an English translation simultaneously (via separate audio channel).

**Architecture:**
```
STT (source language)
     │
     ▼
Translation LLM (Groq / Kimi for long context)
     │
     ▼
TTS (target language, different voice persona)
```

**Phase:** Phase 4+. Requires accurate Nepali STT (currently ~85% WER) to improve to > 95% before translation is viable.

---

## 10.2 Multi-Speaker Conversations

Multiple speakers talking to the same Voice OS instance — a conversation with the AI as a participant, not just a servant.

**Technical requirements:**
- Speaker diarization (identify who is speaking at each moment)
- Turn management that handles overlapping speech
- Each speaker addressed by name if enrolled
- Conversation window tracks per-speaker history

**Use case:** A canteen team meeting where Baadar is taking notes and answering questions from multiple team members simultaneously.

**Phase:** Phase 4.

---

## 10.3 Avatar Synchronization

When Voice OS TTS is playing through an avatar (Mr. Yeti, for example), the avatar's lip and facial movements must sync with the audio. This requires:

1. **Phoneme timing export** from OmniVoice: timestamp for each phoneme
2. **Viseme mapping**: phoneme → mouth shape (based on Preston Blair phoneme chart)
3. **Facial expression sync**: emotion register → facial animation preset
4. **Sub-100ms synchronization** between audio playback and avatar render

**Integration point:** SES-007 Character System (future) defines the avatar's animation contract. Voice OS publishes phoneme events to a WebSocket that the avatar engine subscribes to.

---

## 10.4 Voice Cloning (Consent-Required)

Voice cloning allows creating a new OmniVoice speaker model from a target voice. Strict consent requirements apply.

**Use cases:**
- Operator creates a custom voice for their brand
- Mr. Yeti's voice is refined over time using feedback
- pielts creates a personalized coach voice for each student (Phase 5+)

**Consent requirements (non-negotiable):**
1. The voice owner must explicitly consent in writing before any recording is used
2. The cloned voice model cannot be used for any purpose outside the scope consented to
3. The voice owner can revoke consent at any time; the model must be deleted within 24 hours
4. The consent record is stored permanently and cannot be deleted

**Technical:** OmniVoice custom speaker training requires approximately 5 minutes of clean audio per speaker. Training runs locally — audio never leaves the device.

---

## 10.5 Meeting Participation

Voice OS joining calls (Zoom, Google Meet, Teams) as a participant or note-taker.

**Phase:** Phase 6+.

**Technical:** Virtual audio device that routes meeting audio through Voice OS pipeline; Pipecat has experimental meeting integrations.

---

## 10.6 Call Automation

Outbound phone calls where Voice OS handles a full scripted interaction — confirming canteen orders, checking in with students, scheduling appointments.

**Phase:** Phase 6.

**Technical:** Twilio integration (or equivalent), G.711/8kHz audio pipeline, DTMF handling for IVR navigation.

---

# Appendix A — Conversation State Machine

---

## A.1 State Definitions

The Conversation State Machine (CSM) defines every possible state Voice OS can be in. There are no implicit states — if the CSM is not in one of these states, something is wrong.

```python
class VoiceState(Enum):
    IDLE                = "idle"
    WAKE_LISTENING      = "wake_listening"
    ACTIVE_CONVERSATION = "active_conversation"
    LISTENING           = "listening"
    THINKING            = "thinking"
    SPEAKING            = "speaking"
    INTERRUPTED         = "interrupted"
    RECOVERING          = "recovering"
    CONFIRMING          = "confirming"
    PAUSED              = "paused"
    ERROR               = "error"
```

---

## A.2 State Descriptions

| State | What It Means | Audio Input | Audio Output |
|-------|--------------|-------------|--------------|
| `IDLE` | Voice OS is off. No listening. | None | None |
| `WAKE_LISTENING` | Listening only for wake word | VAD + Wake Word | None |
| `ACTIVE_CONVERSATION` | Conversation started; ready for next turn | VAD + STT | Optional: "Yes?" or beep |
| `LISTENING` | Actively capturing user's current utterance | VAD + STT streaming | None |
| `THINKING` | Utterance received; agent is processing | VAD (for barge-in) | None |
| `SPEAKING` | System is playing TTS response | VAD (for barge-in) | TTS audio |
| `INTERRUPTED` | User spoke during SPEAKING | STT | TTS stopped |
| `RECOVERING` | Processing interrupted utterance | VAD + STT | None |
| `CONFIRMING` | Awaiting user confirmation for a safety-gated action | VAD + STT | Confirmation prompt playing |
| `PAUSED` | Session temporarily suspended (user said "pause") | None | None |
| `ERROR` | Unrecoverable pipeline error | None | Error message |

---

## A.3 State Transition Table

| From State | Event | To State | Action |
|-----------|-------|---------|--------|
| IDLE | Wake word detected | WAKE_LISTENING | Log start time |
| IDLE | User calls `start_session()` | ACTIVE_CONVERSATION | Log start |
| WAKE_LISTENING | Wake phrase detected | ACTIVE_CONVERSATION | Play activation sound |
| WAKE_LISTENING | Silence > 60s | IDLE | No action |
| ACTIVE_CONVERSATION | Speech detected (VAD) | LISTENING | Begin STT |
| ACTIVE_CONVERSATION | Silence > 30s | IDLE | Promote session to L1 |
| ACTIVE_CONVERSATION | User says "pause" | PAUSED | Log pause time |
| LISTENING | End-of-turn detected | THINKING | Send to agent |
| LISTENING | Silence > 8s | ACTIVE_CONVERSATION | Prompt: "Was there something?" |
| THINKING | First agent token | SPEAKING | Start TTS |
| THINKING | Agent error / timeout | ACTIVE_CONVERSATION | Apologize verbally |
| THINKING | Speech detected (barge-in) | INTERRUPTED | Cancel agent; capture new utterance |
| SPEAKING | VAD detects speech > 150ms | INTERRUPTED | Stop TTS immediately |
| SPEAKING | TTS playback complete | ACTIVE_CONVERSATION | Wait for next turn |
| SPEAKING | Safety action detected | CONFIRMING | Play confirmation prompt |
| INTERRUPTED | — | RECOVERING | Capture and finalize interrupted utterance |
| RECOVERING | Utterance captured | THINKING | Process new utterance |
| CONFIRMING | User says yes/confirmed | THINKING | Execute confirmed action |
| CONFIRMING | User says no/cancel | ACTIVE_CONVERSATION | Cancel action; acknowledge |
| CONFIRMING | Silence > 10s | ACTIVE_CONVERSATION | Auto-cancel; inform user |
| PAUSED | User says "resume" | ACTIVE_CONVERSATION | Resume |
| PAUSED | Silence > 5 min | IDLE | End session |
| ERROR | — | IDLE | Log error; notify via Telegram |

---

## A.4 CSM Implementation

```python
class ConversationStateMachine:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = VoiceState.IDLE
        self.state_entered_at: datetime = datetime.utcnow()
        self._timeout_tasks: dict[VoiceState, asyncio.Task] = {}

    async def transition(
        self, new_state: VoiceState, reason: str = ""
    ) -> None:
        old_state = self.state

        # Validate transition
        if not self._is_valid_transition(old_state, new_state):
            raise InvalidStateTransition(
                f"Cannot transition from {old_state} to {new_state}"
            )

        # Cancel existing timeout for old state
        if old_state in self._timeout_tasks:
            self._timeout_tasks[old_state].cancel()

        self.state = new_state
        self.state_entered_at = datetime.utcnow()

        # Log the transition
        logger.info(
            f"[CSM] {self.session_id}: {old_state.value} → "
            f"{new_state.value} [{reason}]"
        )

        # Schedule timeouts for the new state
        timeout = STATE_TIMEOUTS.get(new_state)
        if timeout:
            self._timeout_tasks[new_state] = asyncio.create_task(
                self._handle_timeout(new_state, timeout)
            )

    def _is_valid_transition(
        self, from_state: VoiceState, to_state: VoiceState
    ) -> bool:
        return to_state in VALID_TRANSITIONS.get(from_state, set())

# Timeouts (seconds)
STATE_TIMEOUTS = {
    VoiceState.WAKE_LISTENING:      60,
    VoiceState.ACTIVE_CONVERSATION: 30,
    VoiceState.LISTENING:            8,
    VoiceState.THINKING:             5,
    VoiceState.CONFIRMING:          10,
    VoiceState.PAUSED:             300,
}
```

---

## A.5 CSM Visual Diagram

```
          ┌─────────────────────────────────────────────────────┐
          │                                                     │
          ▼                                                     │
       ┌──────┐    wake word     ┌────────────────┐            │
       │ IDLE │ ─────────────── ▶│ WAKE_LISTENING │            │
       └──────┘                  └───────┬────────┘            │
          ▲                              │ phrase detected       │
          │ silence >60s                 ▼                      │
          │                      ┌──────────────────┐          │
          │◀ ─ ─ ─ silence >30s─ │ ACTIVE_CONV      │◀─────────┤
          │                      └───────┬───────────┘          │
          │                              │ speech detected       │
          │                              ▼                      │
          │                      ┌─────────────┐               │
          │                      │  LISTENING  │               │
          │                      └──────┬──────┘               │
          │                             │ end-of-turn           │
          │                             ▼                      │
          │                      ┌─────────────┐               │
          │         barge-in     │  THINKING   │               │
          │              ┌───────└──────┬──────┘               │
          │              │              │ first token           │
          │              ▼              ▼                      │
          │       ┌──────────────┐ ┌─────────┐                 │
          │       │  INTERRUPTED │ │ SPEAKING │ ─── complete ──▶│
          │       └──────┬───────┘ └────┬────┘                 │
          │              │              │ safety action         │
          │              ▼              ▼                      │
          │       ┌──────────────┐ ┌──────────────┐            │
          │       │  RECOVERING  │ │  CONFIRMING  │            │
          │       └──────┬───────┘ └──────┬───────┘            │
          │              │                │ confirmed           │
          │              └────────────────┘                    │
          │                       │                            │
          └───────── error ───────┘                            │
                                                               │
          ┌─────────────────────────────────────────────────────┘
          │ (ACTIVE_CONV on confirmation)
```

---

# Appendix B — Voice Capability Matrix

---

## B.1 Matrix Definition

The Voice Capability Matrix defines what each speaker tier can do via voice commands. This matrix is enforced by the SafetyHarness (SES-002) combined with Voice OS speaker tier checking.

| Capability | Guest | Verified User | Admin |
|-----------|-------|--------------|-------|
| **General conversation / Q&A** | ✓ | ✓ | ✓ |
| **Ask about IELTS topics (pielts)** | ✓ | ✓ | ✓ |
| **Get HCG menu or canteen info** | ✓ | ✓ | ✓ |
| **Request a Mr. Yeti tip** | ✓ | ✓ | ✓ |
| **Query personal memory / history** | ✗ | ✓ | ✓ |
| **Update personal preferences** | ✗ | ✓ | ✓ |
| **Start an IELTS evaluation session** | ✗ | ✓ | ✓ |
| **Check today's content queue** | ✗ | ✓ | ✓ |
| **Control local machine (open apps, etc.)** | ✗ | ✓ | ✓ |
| **Trigger non-critical automations** | ✗ | ✓ | ✓ |
| **Send Telegram / email messages** | ✗ | ✓ (with verbal confirm) | ✓ |
| **Modify content queue** | ✗ | ✓ (with verbal confirm) | ✓ |
| **Publish content to social media** | ✗ | ✗ | ✓ (with repeat-back) |
| **Modify platform configuration** | ✗ | ✗ | ✓ (with code confirm) |
| **Enroll new speaker** | ✗ | ✗ | ✓ |
| **Deploy code** | ✗ | ✗ | ✓ (code confirm + 3s pause) |
| **Approve production actions** | ✗ | ✗ | ✓ (code confirm) |
| **Delete memory records** | ✗ | ✗ | ✓ (code confirm) |
| **Access security audit log** | ✗ | ✗ | ✓ |

---

## B.2 Capability Enforcement

```python
class VoiceCapabilityGate:
    GUEST_CAPABILITIES = {
        "general_conversation", "ielts_topic_query",
        "canteen_info", "mr_yeti_tip",
    }

    VERIFIED_CAPABILITIES = GUEST_CAPABILITIES | {
        "query_personal_memory", "update_preferences",
        "start_ielts_eval", "check_content_queue",
        "control_local_machine", "trigger_automation",
        "send_message",  # requires verbal confirmation
        "modify_content_queue",  # requires verbal confirmation
    }

    ADMIN_CAPABILITIES = VERIFIED_CAPABILITIES | {
        "publish_content", "modify_platform_config",
        "enroll_speaker", "deploy_code",
        "approve_production", "delete_memory",
        "access_audit_log",
    }

    async def check(
        self, capability: str, speaker_tier: SpeakerTier
    ) -> CapabilityResult:
        allowed_set = {
            SpeakerTier.GUEST: self.GUEST_CAPABILITIES,
            SpeakerTier.VERIFIED: self.VERIFIED_CAPABILITIES,
            SpeakerTier.ADMIN: self.ADMIN_CAPABILITIES,
        }[speaker_tier]

        if capability in allowed_set:
            return CapabilityResult(allowed=True)

        return CapabilityResult(
            allowed=False,
            reason=f"Your current voice tier ({speaker_tier.value}) "
                   f"doesn't permit '{capability}'. "
                   f"This requires re-verification.",
        )
```

---

## B.3 Integration with SafetyHarness

The Voice Capability Gate runs **before** the SafetyHarness. If the capability gate rejects a request, the SafetyHarness never sees it. If the capability gate approves, the SafetyHarness applies its L1–L5 safety classification as normal.

```
Voice Command
      │
      ▼
Voice Capability Gate (SES-004)
      │ approved
      ▼
SafetyHarness (SES-002)
      │ approved
      ▼
Agent Tool Execution
```

A VERIFIED USER who asks to "deploy to production" is blocked by the Voice Capability Gate (ADMIN only). An ADMIN who asks to "deploy to production" passes the Capability Gate but is then subject to the SafetyHarness L5 CRITICAL classification, which requires code confirmation via the Code Confirmation strategy.

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | End-to-end voice latency (first audio) < 900ms in local mode | Automated timing test with synthetic audio input | Must Have |
| AC-002 | Barge-in stops TTS within 200ms of VAD detection | Unit test with pre-recorded barge-in sequence | Must Have |
| AC-003 | Speaker verification correctly identifies enrolled users with confidence ≥ 0.85 | Test set of 10 enrollment samples vs. 20 verification samples | Must Have |
| AC-004 | Guest user cannot access verified-only capabilities | Integration test: unrecognized voice requests "check my memory" → denied | Must Have |
| AC-005 | Emergency stop cancels all in-flight actions within 500ms | Integration test with concurrent tool calls | Must Have |
| AC-006 | Conversation window correctly maintains last 20 turns | Unit test: 25-turn conversation, verify only last 20 are present | Must Have |
| AC-007 | Session promotion writes to L1 episodic memory at session end | Unit test: end session, verify episodic_memory record written | Must Have |
| AC-008 | Language detection correctly identifies English vs. Nepali at > 85% accuracy | Test set with 50 English + 50 Nepali utterances | Should Have |
| AC-009 | Speaking rate adapts correctly to "slower"/"faster" voice commands | Unit test: verify rate -= 0.05 / rate += 0.05 on command | Should Have |
| AC-010 | Pronunciation corrections persist to L2 semantic memory and affect future TTS | Integration test: correct pronunciation → verify next TTS uses SSML lexicon | Should Have |
| AC-011 | CSM state transitions match the valid transition table | State machine unit test: attempt invalid transitions, verify rejection | Must Have |
| AC-012 | CONFIRMING state auto-cancels action after 10s silence | Timer test: verify ACTIVE_CONVERSATION transition and action cancellation | Must Have |

---

# Implementation Checklist

**Phase 1 — Core Voice Pipeline (local)**
- [ ] Implement `app/voice/pipeline.py` — full pipeline with Pipecat
- [ ] Implement `app/voice/state_machine.py` — CSM with all 11 states and transition table
- [ ] Implement `app/voice/conversation.py` — ConversationWindow, TurnDetector
- [ ] Implement `app/voice/adapters/macos.py` — PyAudio + SpeexDSP
- [ ] Implement `app/voice/backends/stt/whisper_local.py`
- [ ] Implement `app/voice/backends/stt/groq_whisper.py` (fallback)
- [ ] Implement `app/voice/backends/tts/omnivoice.py`
- [ ] Implement `app/voice/backends/tts/gemini_tts.py` (fallback)
- [ ] Implement `app/voice/backends/vad/silero.py`
- [ ] Write unit tests for CSM, ConversationWindow, TurnDetector
- [ ] Implement emergency stop (`app/voice/safety.py`)

**Phase 2 — Speaker Identity**
- [ ] Implement `app/voice/speaker_identity.py` — enrollment, verification, biometric store
- [ ] Implement `VoiceCapabilityGate`
- [ ] Implement biometric local storage (encrypted SQLite)
- [ ] Write enrollment UI (not voice — setup only)
- [ ] Write verification tests with enrolled speaker samples

**Phase 3 — Browser + Prosody**
- [ ] Implement `app/voice/adapters/browser.py` — WebSocket adapter
- [ ] Implement WebRTC transport via Pipecat
- [ ] Implement `app/voice/prosody.py` — VoicePersona, SSMLAnnotator, RegisterSelector
- [ ] Implement `app/voice/memory.py` — SessionPromoter, PronunciationMemory
- [ ] Define and register all three initial voice personas

**Phase 4 — Multilingual + Anti-Spoofing**
- [ ] Integrate language detection (langdetect)
- [ ] Configure Nepali-optimized Whisper model
- [ ] Implement anti-spoofing challenge-response
- [ ] Implement replay detection signals

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Barge-in fails without echo cancellation hardware support | Medium | High | Test on target hardware early; document fallback behavior (no barge-in mode) |
| R-002 | Nepali STT accuracy (85% WER) is too low for practical use | High | Medium | Document limitation clearly; offer text fallback for Nepali; improve model iteratively |
| R-003 | Local Whisper inference is too slow on low-end hardware (> 500ms) | Medium | High | Always route to Groq if local STT > 200ms; maintain Groq as primary if hardware is limited |
| R-004 | OmniVoice TTS quality degrades below expectations | Low | Medium | Maintain Gemini TTS as production fallback; OmniVoice becomes optional enhancement |
| R-005 | Speaker verification false positives allow unauthorized access | Low | Critical | Default to GUEST tier; require code confirmation for ADMIN; anti-spoofing in Phase 2 |
| R-006 | WebRTC NAT traversal fails in some network environments | Medium | Medium | STUN configuration covers most cases; TURN relay for Phase 3 if needed |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-002 | Agent System | SafetyHarness governs all voice-triggered tool calls |
| SES-003 | Memory | Context Assembly and Session Promotion integrate directly |
| SES-005 | AI Studio | Shares OmniVoice TTS via Multimodal Interaction Layer |
| SES-006 | Video Pipeline | Narration audio uses Voice OS TTS pipeline |
| SES-007 | Character System | Mr. Yeti avatar sync requires Voice OS phoneme events |
| SES-009 | Mission Control | Voice sessions visible in CEO Morning Dashboard |

---

*End of SES-004 Voice OS — Real-Time Conversational Operating System — Version 1.0.0*

*Status: Approved (L3)*

*Next: [`SES-005_AI_STUDIO.md`](SES-005_AI_STUDIO.md)*
