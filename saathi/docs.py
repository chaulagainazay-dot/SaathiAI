"""Document Q&A — read an uploaded file (PDF/text/docx) and answer questions about it."""
import glob
import os

from . import config

FILES = config.ROOT / "data" / "files"


def _extract(path: str) -> str:
    p = path.lower()
    if p.endswith((".txt", ".md", ".csv")):
        return open(path, encoding="utf-8", errors="ignore").read()
    if p.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except Exception:
            return ""
    if p.endswith(".docx"):
        try:
            import docx
            return "\n".join(par.text for par in docx.Document(path).paragraphs)
        except Exception:
            return ""
    return ""


def ask_document(question: str, filename: str = "") -> dict:
    if not FILES.exists():
        return {"error": "no files uploaded yet (drag a file into Baadar or use +)"}
    files = sorted(glob.glob(str(FILES / "*")), key=os.path.getmtime, reverse=True)
    if filename:
        files = [f for f in files if filename.lower() in os.path.basename(f).lower()]
    if not files:
        return {"error": "no matching uploaded file found"}
    path = files[0]
    text = _extract(path)
    if not text.strip():
        return {"error": f"couldn't read text from {os.path.basename(path)}"}
    from .agent import SaathiAgent
    ans = SaathiAgent().complete(
        "Answer Ajay's question using ONLY the document below. Be concise and accurate; "
        "if the answer isn't in it, say so.",
        f"DOCUMENT ({os.path.basename(path)}):\n{text[:12000]}\n\nQUESTION: {question}",
        max_tokens=600)
    return {"file": os.path.basename(path), "answer": ans}
