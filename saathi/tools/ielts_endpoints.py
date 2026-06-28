"""
IELTS FastAPI router — Mr. Yeti speaking, writing, reading, and daily missions.
Mounted at /api/v1/ielts in server.py.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, List
from collections import Counter
import json
import os
from datetime import datetime

router = APIRouter(prefix="/api/v1/ielts", tags=["IELTS"])

# Lazy Groq client — instantiated on first call so missing key doesn't crash startup
_groq_client = None

def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client

# In-memory session store (replace with Redis/DB in production)
sessions: Dict[str, dict] = {}


# ── Models ─────────────────────────────────────────────────────────────────────

class WritingCheckRequest(BaseModel):
    text: str
    cursor_position: int
    student_id: str
    task_type: str = "task2"  # task1 or task2

class SpeakingResponse(BaseModel):
    transcript: str
    student_id: str
    part: int = 1
    question_number: int = 0

class ReadingExplainRequest(BaseModel):
    question_id: str
    student_answer: str
    correct_answer: str
    passage_text: str
    student_id: str

class DailyMissionRequest(BaseModel):
    student_id: str
    current_band: float
    target_band: float


# ── Helpers ────────────────────────────────────────────────────────────────────

def _session(student_id: str) -> dict:
    if student_id not in sessions:
        sessions[student_id] = {"mistakes": [], "conversations": []}
    return sessions[student_id]

def _groq(messages: list, temperature: float = 0.5, max_tokens: int = 300, stream: bool = False):
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return _get_groq().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/writing-check")
async def check_writing_realtime(request: WritingCheckRequest):
    """Real-time writing correction — call on keystroke or every few seconds."""
    student = _session(request.student_id)
    weaknesses = student.get("weaknesses", [])

    prompt = f"""
You are Mr. Yeti watching a student write an IELTS {request.task_type} essay.
Current text: "{request.text}"
Cursor at position: {request.cursor_position}
Student's known weaknesses: {weaknesses}

RULES:
1. Only flag CLEAR errors, not stylistic preferences
2. If no error near cursor, return empty
3. If error found, respond in this EXACT JSON format:
{{
    "has_error": true,
    "error_text": "the wrong text",
    "suggestion": "the correct text",
    "explanation": "brief rule explanation",
    "yeti_message": "friendly correction message"
}}

If no error: {{"has_error": false}}
"""

    try:
        resp = _groq(
            messages=[
                {"role": "system", "content": "You are Mr. Yeti, a friendly IELTS tutor. Respond ONLY in valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        result = json.loads(resp.choices[0].message.content)

        if result.get("has_error"):
            student["mistakes"].append({
                "type": "grammar",
                "error": result["error_text"],
                "correction": result["suggestion"],
                "timestamp": datetime.now().isoformat(),
            })

        return result

    except Exception as e:
        return {"has_error": False, "error": str(e)}


@router.post("/speaking-practice")
async def speaking_practice(request: SpeakingResponse):
    """Process a spoken response and return Mr. Yeti's structured reply."""
    student = _session(request.student_id)

    prompt = f"""
You are Mr. Yeti, an IELTS Speaking examiner.
Student said: "{request.transcript}"
Part: {request.part} | Question number: {request.question_number}
Student weaknesses: {student.get("weaknesses", [])}
Recent mistakes: {student.get("mistakes", [])[-5:]}

Respond in this JSON format:
{{
    "yeti_reply": "your natural response",
    "correction": "if student made a mistake, the correction",
    "praise": "one specific thing they did well",
    "next_question": "the next question to ask",
    "estimated_band": "current speaking band estimate"
}}
"""

    try:
        resp = _groq(
            messages=[
                {"role": "system", "content": "You are Mr. Yeti. Respond ONLY in valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        result = json.loads(resp.choices[0].message.content)

        student["conversations"].append({
            "student": request.transcript,
            "yeti": result["yeti_reply"],
            "timestamp": datetime.now().isoformat(),
        })

        return result

    except Exception:
        return {
            "yeti_reply": "Let me think about that… Could you say it again?",
            "correction": "",
            "praise": "",
            "next_question": "Can you tell me more about that?",
            "estimated_band": "6.0",
        }


@router.post("/reading-explain")
async def explain_reading(request: ReadingExplainRequest):
    """Explain why a reading answer is correct or wrong with Socratic reasoning."""
    prompt = f"""
Passage: "{request.passage_text}"
Student chose: {request.student_answer}
Correct answer: {request.correct_answer}

You are Mr. Yeti. Guide the student to understand WHY, don't just say right/wrong.

Respond in JSON:
{{
    "yeti_question": "question to make them think",
    "explanation": "clear reasoning with passage evidence",
    "tip": "strategy for similar questions",
    "encouragement": "motivating message"
}}
"""
    resp = _groq(
        messages=[
            {"role": "system", "content": "You are Mr. Yeti, a patient IELTS tutor."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=300,
    )
    return json.loads(resp.choices[0].message.content)


@router.post("/daily-mission")
async def generate_daily_mission(request: DailyMissionRequest):
    """Generate 3 personalised daily missions based on the student's weakness history."""
    student = _session(request.student_id)
    mistakes = student.get("mistakes", [])
    top_weaknesses = Counter(m.get("type", "grammar") for m in mistakes).most_common(3)

    prompt = f"""
Student: {request.student_id}
Current band: {request.current_band}
Target band: {request.target_band}
Top weaknesses: {top_weaknesses}

Generate 3 daily missions, each 10-15 minutes, specific and actionable.

Respond in JSON:
{{
    "missions": [
        {{
            "title": "mission name",
            "skill": "speaking/writing/reading/listening",
            "description": "what to do",
            "estimated_time": "10 min",
            "xp_reward": 100,
            "focus_area": "specific weakness"
        }}
    ],
    "yeti_message": "motivating daily greeting",
    "predicted_band_after": "estimated band if all 3 completed"
}}
"""
    resp = _groq(
        messages=[
            {"role": "system", "content": "You are Mr. Yeti generating daily missions."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=400,
    )
    return json.loads(resp.choices[0].message.content)


@router.get("/progress/{student_id}")
async def get_progress(student_id: str):
    """Return student progress and top weakness analysis."""
    student = sessions.get(student_id, {})
    mistakes = student.get("mistakes", [])

    if not mistakes:
        return {
            "total_mistakes": 0,
            "weaknesses": [],
            "improvement_areas": ["Start practicing to see your progress!"],
            "yeti_message": "Welcome! I'm excited to train with you. 🏔️",
        }

    error_types = Counter(m.get("type", "unknown") for m in mistakes)
    return {
        "total_mistakes": len(mistakes),
        "weaknesses": error_types.most_common(5),
        "improvement_areas": [f"Focus on: {e}" for e, _ in error_types.most_common(3)],
        "recent_corrections": mistakes[-5:],
        "yeti_message": f"Great progress! You've corrected {len(mistakes)} things together. Keep climbing! 🏔️",
    }


# ── WebSocket: real-time speaking with streaming ───────────────────────────────

@router.websocket("/ws/speaking/{student_id}")
async def speaking_websocket(websocket: WebSocket, student_id: str):
    """Stream Mr. Yeti's spoken responses token-by-token during live practice."""
    await websocket.accept()
    student = _session(student_id)
    student.setdefault("current_part", 1)
    student.setdefault("question_number", 0)

    await websocket.send_json({
        "type": "yeti_welcome",
        "message": "Hello! I'm Mr. Yeti, your IELTS coach. Let's practice Speaking Part 1. Ready?",
        "avatar_state": "waving",
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "speech_transcript":
                transcript = data.get("text", "")
                prompt = (
                    f'Student said: "{transcript}"\n'
                    f"Part: {student['current_part']}\n\n"
                    "You are Mr. Yeti. Respond naturally, correct gently, ask the next question.\n"
                    "Keep it conversational — max 2 sentences + 1 question."
                )

                stream = _groq(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    stream=True,
                )

                full_response = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full_response += delta
                        await websocket.send_json({
                            "type": "yeti_stream",
                            "content": delta,
                            "avatar_state": "talking",
                        })

                await websocket.send_json({
                    "type": "yeti_complete",
                    "full_message": full_response,
                    "avatar_state": "idle",
                })

                student["conversations"].append({
                    "student": transcript,
                    "yeti": full_response,
                    "timestamp": datetime.now().isoformat(),
                })

            elif data.get("type") == "disconnect":
                break

    except WebSocketDisconnect:
        pass
