from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import json
import time
import threading
from werkzeug.utils import secure_filename

import fitz
import numpy as np
import faiss
import requests
from sentence_transformers import SentenceTransformer
import unicodedata
import re

# ------------------------------------------------------------
# Configuration (environment variables with sensible defaults)
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VECTOR_STORE_FOLDER = os.path.join(BASE_DIR, "vector_stores")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VECTOR_STORE_FOLDER, exist_ok=True)

# Model / API settings
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
# 💡 For much better accuracy, switch to a larger model:
#    ollama pull llama3.2:3b   (or phi3:mini, mistral:7b, etc.)
#    then set OLLAMA_MODEL="llama3.2:3b" (or your choice)

# Chunking & retrieval
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 700))
MIN_CHUNK_SIZE = int(os.environ.get("MIN_CHUNK_SIZE", 200))
TOP_K = int(os.environ.get("TOP_K", 5))                # increased from 3

# File limits
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

# How long to keep uploaded files / vector stores (seconds)
CLEANUP_AFTER_SECONDS = 24 * 60 * 60  # 24 hours

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# CORS: restrict in production via environment variable
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGIN}})

# Load embedding model once
_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# ------------------------------------------------------------
# Text cleaning utilities
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    """Normalize PDF-extracted text."""
    if not text:
        return ""

    replacements = {
        "Ɵ": "ti",
        "ﬁ": "fi",
        "fl": "fl",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    text = unicodedata.normalize("NFKD", text)
    text = text.replace("\r", "\n")
    text = re.sub(r"[\u200b\u00ad]", "", text)  # zero-width space, soft hyphen
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ------------------------------------------------------------
# PDF text extraction
# ------------------------------------------------------------
def extract_pages_text(pdf_path: str) -> tuple[list[tuple[int, str]], int]:
    """Return (page_number, text) for each page, plus total page count."""
    doc = fitz.open(pdf_path)
    try:
        n = doc.page_count
        out: list[tuple[int, str]] = []
        for i in range(n):
            t = doc.load_page(i).get_text() or ""
            out.append((i + 1, clean_text(t)))
        return out, n
    finally:
        doc.close()

# ------------------------------------------------------------
# Chunking
# ------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, min_chunk_size: int = MIN_CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    n = len(cleaned)

    while start < n:
        end = min(start + chunk_size, n)
        window = cleaned[start:end]

        if end < n:
            # Try to break at sentence end
            cut = window.rfind(". ")
            if cut == -1:
                cut = window.rfind("? ")
            if cut == -1:
                cut = window.rfind("! ")
            if cut == -1:
                cut = window.rfind(" ")
            if cut != -1 and cut >= min_chunk_size:
                end = start + cut + 1

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Overlap to preserve context at boundaries
        start = max(end - 100, start + 1) if end < n else n

    return chunks

def chunk_pdf_by_page(
    pages: list[tuple[int, str]], chunk_size: int = CHUNK_SIZE, min_chunk_size: int = MIN_CHUNK_SIZE
) -> list[dict]:
    """Create chunks with page number metadata."""
    items: list[dict] = []
    for page_num, raw in pages:
        cleaned = " ".join((raw or "").split())
        if not cleaned:
            continue
        for part in chunk_text(cleaned, chunk_size=chunk_size, min_chunk_size=min_chunk_size):
            items.append({"text": part, "page": page_num})
    return items

# ------------------------------------------------------------
# Vector store creation & loading
# ------------------------------------------------------------
def create_vector_store(text_chunks: list[str]):
    if not text_chunks:
        raise ValueError("No text chunks to embed.")

    embeddings = _embedding_model.encode(
        text_chunks,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    embeddings = np.asarray(embeddings, dtype="float32")
    if embeddings.ndim != 2 or embeddings.shape[0] != len(text_chunks):
        raise ValueError("Embedding shape mismatch.")

    dim = int(embeddings.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return index, embeddings

def load_latest_vector_store():
    """Load most recent vector store (demo‑only; not suitable for concurrent users)."""
    files = [
        f for f in os.listdir(VECTOR_STORE_FOLDER)
        if f.endswith(".faiss")
    ]
    if not files:
        raise FileNotFoundError("No vector store found. Upload a PDF first.")

    files.sort(
        key=lambda name: os.path.getmtime(os.path.join(VECTOR_STORE_FOLDER, name)),
        reverse=True,
    )
    index_file = files[0]
    base_name = os.path.splitext(index_file)[0]

    index_path = os.path.join(VECTOR_STORE_FOLDER, index_file)
    chunks_path = os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.chunks.json")

    if not os.path.exists(chunks_path):
        raise FileNotFoundError("Chunks file missing for latest vector store.")

    index = faiss.read_index(index_path)
    with open(chunks_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    chunks = payload.get("chunks") or []
    if not chunks:
        raise ValueError("Loaded vector store has no chunks.")

    return index, chunks, payload

# ------------------------------------------------------------
# Search
# ------------------------------------------------------------
def embed_question(question: str) -> np.ndarray:
    vector = _embedding_model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vector, dtype="float32")

def search_faiss(
    index: faiss.Index,
    question_vector: np.ndarray,
    chunks: list[str],
    top_k: int = TOP_K,
    *,
    chunk_pages=None,
):
    top_k = max(1, min(top_k, len(chunks)))
    scores, indices = index.search(question_vector, top_k)

    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        i = int(idx)
        page = None
        if chunk_pages is not None and i < len(chunk_pages):
            page = chunk_pages[i]
        results.append({
            "chunk": chunks[i],
            "page": page,
            "score": float(score),
        })
    return results

def format_page_range(pages: list[int]) -> str:
    if not pages:
        return ""
    pages = sorted(set(pages))
    if len(pages) == 1:
        return f"Page {pages[0]}"
    return f"Page {pages[0]}-{pages[-1]}"

# ------------------------------------------------------------
# Ollama streaming – FIXED for accuracy
# ------------------------------------------------------------
def stream_ollama_answer(question: str, context: str):
    url = f"{OLLAMA_API_URL}/api/generate"

    # ❗ Keep the FIRST part of context (most relevant chunks appear first)
    max_chars = 3000   # well within 2048 tokens, leaves room for prompt
    safe_context = context[:max_chars] if context else "No context available."

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": (
            "You are a precise document assistant. Answer the question **only** using the provided context.\n"
            "If the answer cannot be determined from the context, say exactly 'I cannot find the answer in the document.'\n\n"
            f"Context:\n{safe_context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        ),
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 512,        # slightly longer answers allowed
            "temperature": 0.1,        # factual, deterministic
        },
    }

    try:
        resp = requests.post(url, json=payload, stream=True, timeout=300)
        if resp.status_code >= 400:
            detail = (resp.text or "")[:800]
            yield f"Ollama error ({resp.status_code}): {detail or 'request failed'}"
            return

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("error"):
                yield f"\n[Error] {obj['error']}"
                return

            piece = obj.get("response")
            if piece:
                yield piece

            if obj.get("done") is True:
                break
    except requests.exceptions.ConnectionError:
        yield "Cannot reach Ollama. Is `ollama serve` running?"
    except requests.exceptions.Timeout:
        yield "Ollama timed out. Try a smaller model or restart Ollama."
    except requests.exceptions.RequestException as e:
        yield f"Request failed: {e}"

# ------------------------------------------------------------
# File cleanup (runs periodically)
# ------------------------------------------------------------
def cleanup_old_files():
    """Delete uploads and vector stores older than CLEANUP_AFTER_SECONDS."""
    now = time.time()
    for folder in (UPLOAD_FOLDER, VECTOR_STORE_FOLDER):
        try:
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > CLEANUP_AFTER_SECONDS:
                    os.remove(fpath)
        except OSError:
            pass

def schedule_cleanup():
    """Run cleanup in a background thread every hour."""
    def loop():
        while True:
            time.sleep(3600)
            cleanup_old_files()
    t = threading.Thread(target=loop, daemon=True)
    t.start()

# Start cleanup scheduler
schedule_cleanup()

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/upload", methods=["POST"])
def upload_file():
    if "pdf" not in request.files:
        return jsonify({"error": "Missing file field 'pdf'"}), 400

    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400

    filepath = os.path.join(UPLOAD_FOLDER, filename)

    # Save first
    try:
        file.save(filepath)
    except OSError as e:
        return jsonify({"error": "Failed to save file", "details": str(e)}), 500

    # Validate magic bytes (PDF header)
    try:
        with open(filepath, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                os.remove(filepath)
                return jsonify({"error": "Invalid PDF file"}), 400
    except OSError:
        os.remove(filepath)
        return jsonify({"error": "Could not verify file"}), 500

    # Extract text
    try:
        page_pairs, pages = extract_pages_text(filepath)
    except (fitz.FileDataError, fitz.FileNotFoundError, fitz.EmptyFileError) as e:
        try:
            os.remove(filepath)
        except OSError:
            pass
        return jsonify({"error": "Invalid or unreadable PDF", "details": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Failed to extract text from PDF", "details": str(e)}), 500

    # Build vector store
    try:
        chunk_items = chunk_pdf_by_page(page_pairs)
        chunk_texts = [x["text"] for x in chunk_items]
        chunk_pages = [x["page"] for x in chunk_items]
        index, _embeddings = create_vector_store(chunk_texts)

        base_name = os.path.splitext(filename)[0]
        index_path = os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.faiss")
        chunks_path = os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.chunks.json")

        faiss.write_index(index, index_path)
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump({
                "source_pdf": filename,
                "pages": pages,
                "chunk_size": CHUNK_SIZE,
                "chunks": chunk_texts,
                "chunk_pages": chunk_pages,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": "Failed to build vector store", "details": str(e)}), 500

    return jsonify({
        "message": "PDF processed successfully",
        "filename": filename,
        "pages": pages,
        "chunks_created": len(chunk_texts),
        "text_preview": (chunk_texts[0][:500] if chunk_texts else ""),
    })

# Stream headers to disable buffering
_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    try:
        index, chunks, payload = load_latest_vector_store()
    except Exception as e:
        return jsonify({"error": "No vector store available", "details": str(e)}), 400

    try:
        chunk_pages = payload.get("chunk_pages")
        if not isinstance(chunk_pages, list):
            chunk_pages = None

        question_vector = embed_question(question)
        top_matches = search_faiss(index, question_vector, chunks, top_k=TOP_K, chunk_pages=chunk_pages)

        if not top_matches:
            def no_context_stream():
                yield json.dumps({"source": ""}, ensure_ascii=False) + "\n"
                yield "I could not find relevant information in the document."
            return Response(stream_with_context(no_context_stream()), mimetype="text/plain; charset=utf-8", headers=_STREAM_HEADERS)

        context = "\n\n---\n\n".join(m["chunk"] for m in top_matches)
        pages = [m.get("page") for m in top_matches if isinstance(m.get("page"), int)]
        source_text = format_page_range(pages)
        meta_line = json.dumps({"source": source_text}, ensure_ascii=False)

        def token_stream():
            yield meta_line + "\n"
            yield from stream_ollama_answer(question, context)

        return Response(stream_with_context(token_stream()), mimetype="text/plain; charset=utf-8", headers=_STREAM_HEADERS)
    except Exception as e:
        return jsonify({"error": "Failed to answer question", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)