"""Internet reach tools via Agent-Reach backends.

Non-privileged: Baadar can call these freely without voice verification.
Covers: web pages (Jina), YouTube subtitles (yt-dlp), web search (Exa/mcporter),
GitHub repos (gh CLI), RSS feeds (feedparser), Bilibili search.
"""
import subprocess
import shutil
from pathlib import Path

# Ensure ~/.local/bin is in PATH for yt-dlp symlink
import os
_home = Path.home()
_local_bin = str(_home / ".local" / "bin")
if _local_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _local_bin + ":" + os.environ.get("PATH", "")

# Also add venv bin to PATH for yt-dlp
_venv_bin = str(Path(__file__).resolve().parent.parent.parent / ".venv" / "bin")
if _venv_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _venv_bin + ":" + os.environ.get("PATH", "")


def _run(cmd: list[str], timeout: int = 30) -> dict:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=os.environ)
        out = (p.stdout or "").strip()[-6000:]
        err = (p.stderr or "").strip()[-1000:]
        if p.returncode != 0 and not out:
            return {"ok": False, "error": err or f"exit code {p.returncode}"}
        return {"ok": True, "output": out, "stderr": err if err else None}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"Tool not installed: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_webpage(url: str) -> dict:
    """Read any webpage as clean text via Jina Reader (r.jina.ai)."""
    jina_url = f"https://r.jina.ai/{url}"
    return _run(["curl", "-sL", "--max-time", "20", jina_url], timeout=25)


def youtube_info(url: str) -> dict:
    """Get YouTube video title, description, and subtitles using yt-dlp."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return {"ok": False, "error": "yt-dlp not found in PATH"}
    result = _run([ytdlp, "--no-warnings", "--dump-json",
                   "--write-subs", "--write-auto-subs",
                   "--skip-download", url], timeout=60)
    if not result["ok"]:
        # Try subtitle extraction only
        sub = _run([ytdlp, "--no-warnings", "--skip-download",
                    "--write-auto-subs", "--sub-langs", "en,ne",
                    "--print", "title", url], timeout=45)
        return sub
    return result


def youtube_subtitles(url: str, lang: str = "en") -> dict:
    """Extract subtitles/transcript from a YouTube video."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return {"ok": False, "error": "yt-dlp not found in PATH"}
    # Get subtitle as SRT printed to stdout
    result = _run([ytdlp, "--no-warnings", "--skip-download",
                   "--write-auto-subs", "--sub-langs", lang,
                   "--convert-subs", "srt",
                   "--print-to-file", "subtitles", "-",
                   url], timeout=60)
    if result["ok"] and result["output"]:
        return result
    # Fallback: get video info as text summary
    return _run([ytdlp, "--no-warnings", "--skip-download",
                 "--print", "%(title)s\n%(description)s", url], timeout=45)


def web_search(query: str, num_results: int = 5) -> dict:
    """Search the web using Exa semantic search (free, no API key needed).
    Falls back to a DuckDuckGo instant-answer API search."""
    # Try Exa via mcporter if available
    mcporter = shutil.which("mcporter")
    if mcporter:
        result = _run([mcporter, "exa", "search", query, "--num-results", str(num_results)],
                      timeout=20)
        if result["ok"]:
            return result

    # Fallback: DuckDuckGo instant answers
    import urllib.parse
    encoded = urllib.parse.quote(query)
    ddg_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        import urllib.request, json
        with urllib.request.urlopen(ddg_url, timeout=10) as r:
            data = json.loads(r.read().decode())
        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for item in (data.get("RelatedTopics") or [])[:num_results]:
            if isinstance(item, dict) and item.get("Text"):
                results.append(item["Text"])
        return {"ok": True, "output": "\n\n".join(results) or "No results found", "source": "duckduckgo"}
    except Exception as e:
        return {"ok": False, "error": f"Search failed: {e}"}


def github_repo(repo: str) -> dict:
    """Read a GitHub repository overview, README, and recent issues.
    repo can be 'owner/name' or a full GitHub URL."""
    gh = shutil.which("gh")
    if not gh:
        # Fallback via Jina Reader
        if not repo.startswith("http"):
            repo = f"https://github.com/{repo}"
        return read_webpage(repo)
    # Normalise 'owner/repo' format
    if repo.startswith("https://github.com/"):
        repo = repo.replace("https://github.com/", "").rstrip("/")
    result = _run([gh, "repo", "view", repo, "--json",
                   "name,description,stargazerCount,forkCount,url,defaultBranchRef"], timeout=20)
    if result["ok"]:
        # Also grab the README via Jina for context
        readme = read_webpage(f"https://github.com/{repo}/blob/main/README.md")
        if readme.get("ok"):
            result["readme_snippet"] = readme["output"][:2000]
    return result


def rss_feed(url: str, limit: int = 10) -> dict:
    """Read an RSS or Atom feed and return the latest entries."""
    try:
        import feedparser
        feed = feedparser.parse(url)
        if feed.get("bozo") and not feed.get("entries"):
            return {"ok": False, "error": f"Could not parse feed: {feed.get('bozo_exception', 'unknown')}"}
        entries = []
        for e in (feed.entries or [])[:limit]:
            entries.append({
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "summary": (e.get("summary") or e.get("description") or "")[:500],
                "published": e.get("published", ""),
            })
        feed_title = (feed.feed or {}).get("title", url)
        return {"ok": True, "feed": feed_title, "entries": entries, "count": len(entries)}
    except ImportError:
        return {"ok": False, "error": "feedparser not installed — run: pip install feedparser"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def bilibili_search(query: str) -> dict:
    """Search Bilibili videos (no login required)."""
    import urllib.parse, urllib.request, json
    encoded = urllib.parse.quote(query)
    url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={encoded}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        results = []
        for item in (data.get("data", {}).get("result") or [])[:8]:
            results.append({
                "title": item.get("title", "").replace("<em class=\"keyword\">","").replace("</em>",""),
                "author": item.get("author", ""),
                "play": item.get("play", 0),
                "desc": (item.get("description") or "")[:200],
                "url": "https://www.bilibili.com/video/" + item.get("bvid", ""),
            })
        return {"ok": True, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def reach_doctor() -> dict:
    """Run agent-reach doctor to see which internet channels are active."""
    ar = shutil.which("agent-reach")
    if not ar:
        ar = str(Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "agent-reach")
    return _run([ar, "doctor", "--json"] if ar else ["agent-reach", "doctor"], timeout=30)


# Dispatcher
def call(tool_name: str, inputs: dict) -> str:
    import json
    fn_map = {
        "read_webpage": read_webpage,
        "youtube_info": youtube_info,
        "youtube_subtitles": youtube_subtitles,
        "web_search": web_search,
        "github_repo": github_repo,
        "rss_feed": rss_feed,
        "bilibili_search": bilibili_search,
        "reach_doctor": reach_doctor,
    }
    fn = fn_map.get(tool_name)
    if not fn:
        return json.dumps({"error": f"unknown internet tool: {tool_name}"})
    try:
        result = fn(**inputs)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
