from flask import Flask, request, send_from_directory, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import json
from werkzeug.utils import secure_filename

import fitz  
import numpy as np
import faiss
import requests
from sentence_transformers import SentenceTransformer    

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VECTOR_STORE_FOLDER = os.path.join(BASE_DIR, "vector_stores")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VECTOR_STORE_FOLDER, exist_ok=True)

_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


def extract_text_from_pdf(pdf_path: str) -> tuple[str, int]:
    doc = fitz.open(pdf_path)
    try:
        pages = doc.page_count
        full_text = "".join(page.get_text() for page in doc)
        return full_text, pages
    finally:
        doc.close()


def extract_pages_text(pdf_path: str) -> tuple[list[tuple[int, str]], int]:
    """1-based page numbers with raw text per page."""
    doc = fitz.open(pdf_path)
    try:
        n = doc.page_count
        out: list[tuple[int, str]] = []
        for i in range(n):
            t = doc.load_page(i).get_text() or ""
            out.append((i + 1, t))
        return out, n
    finally:
        doc.close()


def chunk_text(text: str, *, chunk_size: int = 700, min_chunk_size: int = 200) -> list[str]:
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

        start = end

    return chunks


def chunk_pdf_by_page(
    pages: list[tuple[int, str]], *, chunk_size: int = 700, min_chunk_size: int = 200
) -> list[dict]:
    """Each chunk knows its PDF page (1-based)."""
    items: list[dict] = []
    for page_num, raw in pages:
        cleaned = " ".join((raw or "").split())
        if not cleaned:
            continue
        for part in chunk_text(cleaned, chunk_size=chunk_size, min_chunk_size=min_chunk_size):
            items.append({"text": part, "page": page_num})
    return items


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
        raise FileNotFoundError("Chunks file for latest vector store is missing.")

    index = faiss.read_index(index_path)
    with open(chunks_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    chunks = payload.get("chunks") or []
    if not chunks:
        raise ValueError("Loaded vector store has no chunks.")

    return index, chunks, payload


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
    top_k: int = 3,
    *,
    chunk_pages=None,
):
    top_k = max(1, min(top_k, len(chunks)))
    scores, indices = index.search(question_vector, top_k)

    top_indices = indices[0]
    top_scores = scores[0]

    results = []
    for idx, score in zip(top_indices, top_scores):
        if idx < 0 or idx >= len(chunks):
            continue
        i = int(idx)
        page = None
        if chunk_pages is not None and i < len(chunk_pages):
            page = chunk_pages[i]
        results.append(
            {
                "chunk": chunks[i],
                "page": page,
                "score": float(score),
            }
        )

    return results


def source_entries_from_matches(matches: list[dict], *, excerpt_max: int = 220) -> list[dict]:
    """Deduped sources for UI: page + short excerpt."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for m in matches:
        chunk = m.get("chunk") or ""
        page = m.get("page")
        excerpt = chunk.strip().replace("\n", " ")
        if len(excerpt) > excerpt_max:
            excerpt = excerpt[: excerpt_max - 1].rstrip() + "…"
        key = (page, excerpt)
        if key in seen or not excerpt:
            continue
        seen.add(key)
        out.append({"page": page, "excerpt": excerpt})
    return out

def stream_ollama_answer(question: str, context: str):
    """Yield plain-text fragments from Ollama /api/generate (stream: true)."""
    url = f"{OLLAMA_API_URL}/api/generate"
    safe_context = context[-1200:] if context else "No context available."
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"Context: {safe_context}\n\nQuestion: {question}\n\nAnswer concisely:",
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 384,
            "temperature": 0.2,
        },
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as resp:
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

                err = obj.get("error")
                if err:
                    yield f"\n[Error] {err}"
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

    try:
        file.save(filepath)
    except OSError as e:
        return jsonify({"error": "Failed to save file", "details": str(e)}), 500

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

    try:
        chunk_items = chunk_pdf_by_page(page_pairs, chunk_size=700)
        chunk_texts = [x["text"] for x in chunk_items]
        chunk_pages = [x["page"] for x in chunk_items]
        index, _embeddings = create_vector_store(chunk_texts)

        base_name = os.path.splitext(filename)[0]
        index_path = os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.faiss")
        chunks_path = os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.chunks.json")

        faiss.write_index(index, index_path)
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_pdf": filename,
                    "pages": pages,
                    "chunk_size": 700,
                    "chunks": chunk_texts,
                    "chunk_pages": chunk_pages,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        return jsonify({"error": "Failed to build vector store", "details": str(e)}), 500

    return jsonify(
        {
            "message": "PDF processed successfully",
            "filename": filename,
            "pages": pages,
            "chunks_created": len(chunk_texts),
            "text_preview": (chunk_texts[0][:500] if chunk_texts else ""),
        }
    )


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
        top_matches = search_faiss(
            index, question_vector, chunks, top_k=3, chunk_pages=chunk_pages
        )

        if not top_matches:

            def no_context_stream():
                yield json.dumps({"sources": []}, ensure_ascii=False) + "\n"
                yield "I could not find relevant information in the document."

            return Response(
                stream_with_context(no_context_stream()),
                mimetype="text/plain; charset=utf-8",
                headers=dict(_STREAM_HEADERS),
            )

        context = "\n\n---\n\n".join(m["chunk"] for m in top_matches)
        meta_line = json.dumps(
            {"sources": source_entries_from_matches(top_matches)},
            ensure_ascii=False,
        )

        def token_stream():
            yield meta_line + "\n"
            yield from stream_ollama_answer(question, context)

        return Response(
            stream_with_context(token_stream()),
            mimetype="text/plain; charset=utf-8",
            headers=dict(_STREAM_HEADERS),
        )
    except Exception as e:
        return jsonify({"error": "Failed to answer question", "details": str(e)}), 500

@app.route("/uploads/<filename>")
def get_pdf(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    app.run(port=5000, debug=True)

