"""
ChatGPT Browser Tool — talks to ChatGPT open in Brave via AppleScript.
No API key needed. Uses the logged-in ChatGPT session.

Usage:
  from saathi.tools.chatgpt_browser import ask_chatgpt
  result = ask_chatgpt("Write a Mr. Yeti script about speaking mistakes")
"""

import subprocess
import time
import json


def _applescript(script: str) -> str:
    """Run AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()


def _js_in_brave(js: str) -> str:
    """Execute JavaScript in Brave's front tab via AppleScript."""
    # Escape double quotes and backslashes for AppleScript embedding
    js_escaped = js.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "Brave Browser" to execute front window\'s active tab javascript "{js_escaped}"'
    return _applescript(script)


def _find_chatgpt_tab() -> int | None:
    """Return index of the ChatGPT tab in Brave (1-based), or None."""
    script = """
tell application "Brave Browser"
    set tabIndex to -1
    set winCount to count of windows
    repeat with w from 1 to winCount
        set tabCount to count of tabs of window w
        repeat with t from 1 to tabCount
            set tabURL to URL of tab t of window w
            if tabURL contains "chat.openai.com" or tabURL contains "chatgpt.com" then
                set tabIndex to t
                set index of window w to 1
                set active tab index of window w to t
                return tabIndex
            end if
        end repeat
    end repeat
    return tabIndex
end tell
"""
    result = _applescript(script)
    try:
        idx = int(result)
        return idx if idx > 0 else None
    except (ValueError, TypeError):
        return None


def ask_chatgpt(prompt: str, timeout: int = 90) -> dict:
    """
    Send a prompt to ChatGPT in Brave and return the response.
    Returns {"ok": True, "response": "..."} or {"ok": False, "error": "..."}
    """
    # ── 1. Find / focus ChatGPT tab ──────────────────────────────────────────
    tab = _find_chatgpt_tab()
    if tab is None:
        return {"ok": False, "error": "ChatGPT tab not found in Brave. Open chatgpt.com first."}

    time.sleep(0.5)

    # ── 2. Clear existing input and type the prompt ───────────────────────────
    # Inject prompt text into the textarea via JS
    inject_js = """
(function() {
    // Find the prompt textarea
    var ta = document.querySelector('#prompt-textarea') ||
             document.querySelector('div[contenteditable="true"]') ||
             document.querySelector('textarea[placeholder]');
    if (!ta) return 'NO_INPUT';

    // Clear and set value
    ta.focus();
    if (ta.tagName === 'TEXTAREA') {
        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(ta, arguments[0]);
        ta.dispatchEvent(new Event('input', {bubbles: true}));
    } else {
        // contenteditable div
        ta.innerHTML = '';
        document.execCommand('insertText', false, arguments[0]);
    }
    return 'TYPED';
})()
""".strip()

    # AppleScript can't pass arguments to JS easily, so embed prompt directly
    prompt_json = json.dumps(prompt)
    inject = f"""
(function() {{
    var prompt = {prompt_json};
    var ta = document.querySelector('#prompt-textarea') ||
             document.querySelector('div[contenteditable="true"][data-lexical-editor]') ||
             document.querySelector('textarea');
    if (!ta) return 'NO_INPUT';
    ta.focus();
    if (ta.tagName === 'TEXTAREA') {{
        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(ta, prompt);
        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
    }} else {{
        ta.innerHTML = '';
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, prompt);
    }}
    return 'TYPED';
}})()
"""
    typed = _js_in_brave(inject.replace("\n", " "))
    if "NO_INPUT" in typed or not typed:
        return {"ok": False, "error": "Could not find ChatGPT input box. Is ChatGPT loaded?"}

    time.sleep(0.5)

    # ── 3. Click the Send button ──────────────────────────────────────────────
    send_js = """
(function() {
    var btn = document.querySelector('button[data-testid="send-button"]') ||
              document.querySelector('button[aria-label="Send prompt"]') ||
              document.querySelector('button[aria-label*="Send"]') ||
              Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === '' && b.querySelector('svg'));
    if (btn && !btn.disabled) { btn.click(); return 'SENT'; }
    // Fallback: Enter key
    var ta = document.querySelector('#prompt-textarea') || document.querySelector('div[contenteditable="true"]');
    if (ta) {
        ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true}));
        return 'ENTER_SENT';
    }
    return 'NO_BUTTON';
})()
""".replace("\n", " ")
    sent = _js_in_brave(send_js)
    if "NO_BUTTON" in (sent or ""):
        return {"ok": False, "error": "Could not find Send button in ChatGPT."}

    # ── 4. Poll for response completion ──────────────────────────────────────
    # ChatGPT shows a stop button while generating; when it disappears, response is done
    poll_js = """
(function() {
    // Check if still generating (stop button present)
    var stopBtn = document.querySelector('button[aria-label*="Stop"]') ||
                  document.querySelector('button[data-testid="stop-button"]');
    if (stopBtn) return 'GENERATING';

    // Get last assistant message
    var messages = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (messages.length === 0) return 'WAITING';
    var last = messages[messages.length - 1];
    var text = last.innerText || last.textContent || '';
    return text.trim().length > 10 ? 'DONE:' + text.trim() : 'WAITING';
})()
""".replace("\n", " ")

    start = time.time()
    time.sleep(3)  # Give ChatGPT time to start

    while time.time() - start < timeout:
        status = _js_in_brave(poll_js)
        if status and status.startswith("DONE:"):
            response_text = status[5:]
            return {"ok": True, "response": response_text}
        if status == "GENERATING":
            time.sleep(3)
            continue
        if status == "WAITING":
            time.sleep(2)
            continue
        time.sleep(2)

    return {"ok": False, "error": f"Timeout after {timeout}s waiting for ChatGPT response."}


def ask_chatgpt_for_script(topic: str, pillar: str = "horror_story",
                            content_type: str = "mistake", format: str = "short") -> dict:
    """
    Ask ChatGPT in Brave to generate a Mr. Yeti video script.
    pillar: horror_story | before_after | dont_say | quiz | interview
    """
    pillar_instructions = {
        "horror_story": "Mr. Yeti REACTS DRAMATICALLY to a student mistake. Include the wrong student phrase, Mr. Yeti's shocked reaction with sound effects, then the correct answer.",
        "before_after": "SPLIT SCREEN format. Show Band 5 student on left, Band 8 student on right. Mr. Yeti explains the difference in 20 seconds.",
        "dont_say": "Show 3 WRONG words/phrases with ❌. Mr. Yeti reacts to each one. Then reveal the Band 8 alternatives. Viewers will SAVE this video.",
        "quiz": "Mr. Yeti asks: which sentence is correct? A or B? Show 3-second countdown. Reveal answer with explanation. Huge retention format.",
        "interview": "Mr. Yeti interviews an unusual character (zombie/alien/dragon/robot) taking the IELTS exam. Funny and shareable.",
    }

    duration = "60 seconds / ~150 words" if format == "short" else "4-5 minutes / ~700 words"

    prompt = f"""You are writing a viral YouTube Shorts script for Mr. Yeti — a funny, smart, brutally honest Pixar-style 3D animated Yeti IELTS teacher.

TOPIC: {topic}
FORMAT: {duration}
CONTENT PILLAR: {pillar_instructions.get(pillar, pillar_instructions['horror_story'])}

CHANNEL RULES:
- First 3 seconds MUST hook immediately: shocking stat, bold claim, or question
- People click: "Why You Keep Getting Band 5", "The Mistake That Destroyed My Score"
- People do NOT click: "IELTS Reading Tips", "IELTS Lesson 12"
- Mr. Yeti is FUNNY and BRUTALLY HONEST — he reacts dramatically
- Write [stage directions] and [sound effects] for the 3D animator
- Always end with: "Practice free at pielts.web.app"

OUTPUT FORMAT (JSON only, no extra text):
{{
  "title": "Viral YouTube title",
  "hook": "First 3 seconds of narration",
  "narration": "Full word-for-word script with [Mr. Yeti reactions] and [sound effects]",
  "scene_directions": "Full animation directions for each scene",
  "cta": "Last 3 seconds CTA",
  "thumbnail_text": "Bold 4-word thumbnail text",
  "overlay_text": ["line1", "line2", "line3"],
  "tags": ["ielts", "ieltsspeaking", "band7", "englishlearning", "ieltsprep", "mryeti", "ieltsshortsyoutube", "pielts"],
  "hashtags": "#IELTS #IELTSTips #Shorts #MrYeti #Band7",
  "duration_sec": 45
}}"""

    result = ask_chatgpt(prompt, timeout=120)

    if not result["ok"]:
        return result

    # Try to parse JSON from response
    import re
    text = result["response"]
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        import json as _json
        try:
            script = _json.loads(match.group(0))
            script["topic"] = topic
            script["pillar"] = pillar
            script["source"] = "chatgpt_browser"

            # Save to scripts cache
            from datetime import datetime
            from pathlib import Path
            cache_dir = Path.home() / "SaathiAI" / "scripts_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            slug = topic.lower().replace(" ", "_")[:40]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = cache_dir / f"script_{ts}_{slug}.json"
            out.write_text(_json.dumps(script, indent=2, ensure_ascii=False))
            (cache_dir / "latest.json").write_text(_json.dumps(script, indent=2, ensure_ascii=False))

            return {"ok": True, **script, "cache_path": str(out)}
        except Exception as e:
            pass

    # Return raw if JSON parse fails
    return {"ok": True, "response": text, "source": "chatgpt_browser", "topic": topic}
