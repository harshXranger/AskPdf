from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import json
import time
import threading
import logging
from werkzeug.utils import secure_filename
import traceback
import fitz
import numpy as np
import faiss
import requests
from dotenv import load_dotenv

import unicodedata
import re

import hashlib
import ssl

# SSL fixes for Windows (before any HuggingFace downloads)
os.environ.setdefault("CURL_CA_BUNDLE", "")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFICATION", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
ssl._create_default_https_context = ssl._create_unverified_context

_old_request = requests.Session.request


def _patched_request(self, method, url, **kwargs):
    kwargs.setdefault("verify", False)
    return _old_request(self, method, url, **kwargs)


requests.Session.request = _patched_request

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# ------------------------------------------------------------
# Environment & Paths
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBED_DIM = 384
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VECTOR_STORE_FOLDER = os.path.join(BASE_DIR, "vector_stores")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VECTOR_STORE_FOLDER, exist_ok=True)


class EmbeddingModel:
    """Local embeddings with hash fallback — upload never needs Gemini API."""

    def __init__(self):
        self.model = None
        self.model_type = "hash-fallback"
        self.dim = EMBED_DIM
        self._load()

    def _load(self):
        try:
            from sentence_transformers import SentenceTransformer
            cache_dir = os.path.join(BASE_DIR, "model_cache")
            os.makedirs(cache_dir, exist_ok=True)
            for name in ("all-MiniLM-L6-v2", "paraphrase-MiniLM-L3-v2"):
                try:
                    self.model = SentenceTransformer(name, cache_folder=cache_dir, device="cpu")
                    dim_fn = getattr(self.model, "get_embedding_dimension", None) or getattr(
                        self.model, "get_sentence_embedding_dimension", None
                    )
                    if dim_fn:
                        self.dim = int(dim_fn())
                    self.model_type = f"huggingface:{name}"
                    logger.info("Loaded embedding model: %s", name)
                    return
                except Exception as exc:
                    logger.warning("Could not load %s: %s", name, exc)
        except Exception as exc:
            logger.warning("sentence-transformers could not be loaded (%s)", exc)
        logger.warning("Using hash embeddings (upload will still work)")

    def encode(self, texts, normalize_embeddings=True):
        if isinstance(texts, str):
            texts = [texts]
        if self.model is not None:
            vectors = self.model.encode(
                texts, normalize_embeddings=normalize_embeddings, show_progress_bar=False
            )
            return np.asarray(vectors, dtype="float32")
        vectors = np.vstack([self._hash_vec(t) for t in texts]).astype("float32")
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / (norms + 1e-8)
        return vectors

    def _hash_vec(self, text):
        vec = np.zeros(self.dim, dtype="float32")
        for word in (text or "").lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        if not np.any(vec):
            vec[0] = 1.0
        return vec


# ------------------------------------------------------------
# Gemini Authentication & Model Discovery Configuration
# ------------------------------------------------------------

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEPRECATED_MODELS = {
    "gemini-1.0-pro",
    "gemini-1.5-pro-latest",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
}

_MODEL_CACHE_LOCK = threading.Lock()
_DISCOVERED_MODELS: list[str] = []
_DISCOVERED_TIMESTAMP: float = 0.0
_MODEL_CACHE_TTL: float = 600.0  # 10 minutes cache
_ACTIVE_WORKING_MODEL: str | None = None
_LAST_CONFIGURED_MODEL: str | None = None
SERVER_START_TIME = time.strftime("%Y-%m-%d %H:%M:%S")


def get_gemini_api_key() -> str:
    """
    Retrieve Gemini API key with clean precedence:
    1. GEMINI_API_KEY
    2. GOOGLE_API_KEY (fallback for standard Google SDK convention)
    """
    return (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )


def get_configured_model() -> str:
    """Returns the model configured in environment variables or default, intercepting deprecated models."""
    raw = os.environ.get("GEMINI_MODEL", "").strip()
    if raw.startswith("models/"):
        raw = raw[len("models/"):]
    if not raw or raw in DEPRECATED_MODELS:
        if raw in DEPRECATED_MODELS:
            logger.warning("Configured model '%s' is deprecated/unsupported. Intercepting and defaulting to '%s'.", raw, DEFAULT_GEMINI_MODEL)
        return DEFAULT_GEMINI_MODEL
    return raw


def get_gemini_model() -> str:
    """Returns the currently active working model, or the configured model."""
    global _ACTIVE_WORKING_MODEL
    return _ACTIVE_WORKING_MODEL or get_configured_model()


def set_active_working_model(model: str) -> None:
    """Sets the confirmed working Gemini model."""
    global _ACTIVE_WORKING_MODEL
    if model.startswith("models/"):
        model = model[len("models/"):]
    _ACTIVE_WORKING_MODEL = model


def mask_credential(val: str) -> str:
    """Safely mask API keys or tokens for logging purposes."""
    if not val:
        return "(empty)"
    if len(val) <= 8:
        return "***"
    return f"{val[:4]}...{val[-4:]}"


def validate_gemini_key(key: str | None = None) -> tuple[bool, str]:
    """
    Validates Gemini API credentials safely without exposing key values.
    Supports both classic 'AIza...' keys and modern 'AQ...' authorization keys.
    Accurately detects mistakenly provided OAuth tokens ('ya29...', '1//...', or Bearer strings).
    """
    if key is None:
        key = get_gemini_api_key()
    key = (key or "").strip()

    if not key:
        return False, "GEMINI_API_KEY is not set. Add it to backend/.env or configure it in Render environment variables."

    # OAuth access token or refresh token mistakenly supplied
    if key.startswith(("ya29.", "1//")) or key.lower().startswith("bearer "):
        return (
            False,
            "Invalid credential format: An OAuth access or refresh token was supplied instead of an API key. "
            "Gemini API requires an API key. Create a key at https://aistudio.google.com/apikey."
        )

    # Sanity checks
    if any(c.isspace() for c in key):
        return False, "Invalid Gemini API key: The key contains whitespace. Please check your configuration."

    if len(key) < 15:
        return False, "Invalid Gemini API key: The key is too short to be a valid Google API key."

    return True, "ok"


def list_available_gemini_models(api_key: str | None = None, force_refresh: bool = False) -> list[str]:
    """
    Dynamically queries Google's Gemini API to list all models available to the credential
    that support text generation (generateContent).
    Caches results for 10 minutes to minimize network overhead.
    """
    global _DISCOVERED_MODELS, _DISCOVERED_TIMESTAMP
    now = time.time()

    with _MODEL_CACHE_LOCK:
        if not force_refresh and _DISCOVERED_MODELS and (now - _DISCOVERED_TIMESTAMP < _MODEL_CACHE_TTL):
            return list(_DISCOVERED_MODELS)

    key = api_key or get_gemini_api_key()
    if not key:
        return []

    try:
        resp = requests.get(
            GEMINI_BASE_URL,
            headers={"x-goog-api-key": key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("models", [])
            valid_models = []
            for item in data:
                methods = item.get("supportedGenerationMethods", [])
                name = item.get("name", "").replace("models/", "")
                # Filter for text-generation LLMs excluding deprecated and specialized non-chat models
                if "generateContent" in methods and name and name not in DEPRECATED_MODELS:
                    if any(term in name.lower() for term in ("-tts", "-preview-tts", "-transcribe", "robotics")):
                        continue
                    valid_models.append(name)

            if valid_models:
                with _MODEL_CACHE_LOCK:
                    _DISCOVERED_MODELS = valid_models
                    _DISCOVERED_TIMESTAMP = now
                logger.info("Discovered %d Gemini models supporting generateContent: %s", len(valid_models), valid_models[:5])
                return list(valid_models)
        else:
            logger.warning("Failed to query Gemini models (HTTP %d)", resp.status_code)
    except Exception as exc:
        logger.warning("Error discovering Gemini models: %s", exc)

    with _MODEL_CACHE_LOCK:
        if _DISCOVERED_MODELS:
            return list(_DISCOVERED_MODELS)
    return ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-flash-lite-latest"]


def get_candidate_models(configured: str | None = None) -> list[str]:
    """
    Builds an ordered, deduplicated sequence of candidate models to attempt:
    1. Active working model if already verified and healthy
    2. Configured model (e.g. gemini-3.8-flash)
    3. Verified reliable fallbacks (gemini-3.5-flash, gemini-3.6-flash, gemini-flash-lite-latest)
    4. Other dynamically discovered models from Google's API
    """
    global _ACTIVE_WORKING_MODEL, _LAST_CONFIGURED_MODEL
    current_cfg = (configured or get_configured_model()).strip()
    if current_cfg.startswith("models/"):
        current_cfg = current_cfg[len("models/"):]
    if current_cfg in DEPRECATED_MODELS:
        current_cfg = DEFAULT_GEMINI_MODEL

    if _LAST_CONFIGURED_MODEL != current_cfg:
        _LAST_CONFIGURED_MODEL = current_cfg
        _ACTIVE_WORKING_MODEL = None

    candidates: list[str] = []
    if _ACTIVE_WORKING_MODEL and _ACTIVE_WORKING_MODEL not in DEPRECATED_MODELS:
        candidates.append(_ACTIVE_WORKING_MODEL)

    if current_cfg not in candidates:
        candidates.append(current_cfg)

    priority_defaults = [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
    ]
    for pf in priority_defaults:
        if pf not in candidates and pf not in DEPRECATED_MODELS:
            candidates.append(pf)

    discovered = list_available_gemini_models()
    for m in discovered:
        if m not in candidates and m not in DEPRECATED_MODELS:
            candidates.append(m)

    return candidates


MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", 6000))
GEMINI_RETRY_ATTEMPTS = 3
GEMINI_RETRY_DELAY = 2.0

# Ollama fallback config
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1").strip()
ENABLE_OLLAMA_FALLBACK = os.environ.get("ENABLE_OLLAMA_FALLBACK", "false").lower() in ("true", "1", "yes")

# ------------------------------------------------------------
# Safe Runtime Diagnostics
# ------------------------------------------------------------
def get_runtime_diagnostics() -> dict:
    key = get_gemini_api_key()
    key_ok, key_msg = validate_gemini_key(key)
    discovered = list_available_gemini_models(key)
    return {
        "status": "ok",
        "process_id": os.getpid(),
        "server_start_time": SERVER_START_TIME,
        "cwd": os.getcwd(),
        "dotenv_path": DOTENV_PATH,
        "dotenv_exists": os.path.exists(DOTENV_PATH),
        "configured_gemini_model": get_configured_model(),
        "active_gemini_model": get_gemini_model(),
        "gemini_configured": bool(key),
        "gemini_api_key_configured": bool(key),
        "gemini_key_valid": key_ok,
        "gemini_key_message": key_msg if not key_ok else "ok",
        "gemini_model_configured": get_configured_model(),
        "gemini_model_active": get_gemini_model(),
        "model_discovery_succeeded": len(discovered) > 0,
        "discovered_models_count": len(discovered),
        "candidate_models": get_candidate_models()[:6],
        "ollama_fallback_enabled": ENABLE_OLLAMA_FALLBACK,
    }


def log_startup_diagnostics():
    diag = get_runtime_diagnostics()
    logger.info("================ AskPDF Safe Runtime Diagnostics ================")
    logger.info("Process ID: %s | Server Start: %s", diag["process_id"], diag["server_start_time"])
    logger.info("Current Working Directory: %s", diag["cwd"])
    logger.info("Loaded .env path: %s (exists: %s)", diag["dotenv_path"], diag["dotenv_exists"])
    logger.info("Configured Gemini model: %s", diag["configured_gemini_model"])
    logger.info("Active Gemini model: %s", diag["active_gemini_model"])
    logger.info("Gemini API key configured: %s (valid: %s)", diag["gemini_api_key_configured"], diag["gemini_key_valid"])
    logger.info("Model discovery succeeded: %s (%d models available)", diag["model_discovery_succeeded"], diag["discovered_models_count"])
    logger.info("Initial candidate order: %s", diag["candidate_models"])
    logger.info("==================================================================")


log_startup_diagnostics()

# Chunking & retrieval
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 700))
MIN_CHUNK_SIZE = int(os.environ.get("MIN_CHUNK_SIZE", 200))
TOP_K = int(os.environ.get("TOP_K", 5))

MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
CLEANUP_AFTER_SECONDS = 24 * 60 * 60

# App setup
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGIN}})

embedding_model = EmbeddingModel()


# Text cleaning utilities
def clean_text(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "Ɵ": "ti", "ﬁ": "fi", "fl": "fl", "ﬂ": "fl",
        "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("\r", "\n")
    text = re.sub(r"[\u200b\u00ad]", "", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# PDF text extraction
def extract_pages_text(pdf_path: str) -> tuple[list[tuple[int, str]], int]:
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


# Chunking
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, min_chunk_size: int = MIN_CHUNK_SIZE) -> list[str]:
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
        start = max(end - 100, start + 1) if end < n else n
    return chunks


def chunk_pdf_by_page(pages: list[tuple[int, str]], chunk_size: int = CHUNK_SIZE, min_chunk_size: int = MIN_CHUNK_SIZE) -> list[dict]:
    items: list[dict] = []
    for page_num, raw in pages:
        cleaned = " ".join((raw or "").split())
        if not cleaned:
            continue
        for part in chunk_text(cleaned, chunk_size=chunk_size, min_chunk_size=min_chunk_size):
            items.append({"text": part, "page": page_num})
    return items


# ------------------------------------------------------------
# Vector store
# ------------------------------------------------------------
def get_embeddings(texts):
    return embedding_model.encode(texts, normalize_embeddings=True)


def create_vector_store(text_chunks: list[str]):
    embeddings = get_embeddings(text_chunks)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index, embeddings


def load_latest_vector_store():
    files = [f for f in os.listdir(VECTOR_STORE_FOLDER) if f.endswith(".faiss")]
    if not files:
        raise FileNotFoundError("No vector store found. Upload a PDF first.")
    files.sort(key=lambda name: os.path.getmtime(os.path.join(VECTOR_STORE_FOLDER, name)), reverse=True)
    base_name = os.path.splitext(files[0])[0]
    index_path = os.path.join(VECTOR_STORE_FOLDER, files[0])
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
def embed_question(question):
    return embedding_model.encode([question], normalize_embeddings=True)


def search_faiss(index, question_vector, chunks, top_k=TOP_K, *, chunk_pages=None):
    top_k = max(1, min(top_k, len(chunks)))
    scores, indices = index.search(question_vector, top_k)
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        i = int(idx)
        page = chunk_pages[i] if chunk_pages and i < len(chunk_pages) else None
        results.append({"chunk": chunks[i], "page": page, "score": float(score)})
    return results


def format_page_range(pages: list[int]) -> str:
    if not pages:
        return ""
    pages = sorted(set(pages))
    return f"Page {pages[0]}" if len(pages) == 1 else f"Page {pages[0]}-{pages[-1]}"


# ------------------------------------------------------------
# LLM Integration (Gemini with Dynamic Discovery & Ollama fallback)
# ------------------------------------------------------------
def _build_prompt(question: str, context: str) -> str:
    safe_context = (context or "No context available.")[:MAX_CONTEXT_CHARS]
    return (
        "You are an intelligent PDF assistant. Answer ONLY using the document context.\n"
        "Format with Markdown (headings, lists). Be concise.\n"
        "If the answer is not in the document, say: I cannot find the answer in the document.\n\n"
        f"Document Context:\n{safe_context}\n\n"
        f"Question: {question}\n\nAnswer:"
    )


def _extract_gemini_text(obj: dict) -> str:
    parts = []
    for candidate in obj.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("text"):
                parts.append(part["text"])
    return "".join(parts)


def _parse_sse_stream(resp):
    pending = ""
    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        payload = line[5:].strip() if line.startswith("data:") else line
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
            pending = ""
        except json.JSONDecodeError:
            pending += payload
            try:
                obj = json.loads(pending)
                pending = ""
            except json.JSONDecodeError:
                continue
        text = _extract_gemini_text(obj)
        if text:
            yield text


def _parse_gemini_error(resp: requests.Response, model_name: str | None = None) -> str:
    """Parses Google Gemini API error responses into clear, safe user-facing error messages."""
    status_code = resp.status_code
    error_data = {}
    try:
        error_data = resp.json().get("error", {})
    except Exception:
        pass

    message = error_data.get("message", "")
    status = error_data.get("status", "")
    details = error_data.get("details", [])
    reason = ""
    for d in details:
        if isinstance(d, dict) and "reason" in d:
            reason = d["reason"]
            break

    target_model = model_name or get_gemini_model()

    # 1. OAuth token mistakenly supplied or unsupported token
    if reason == "ACCESS_TOKEN_TYPE_UNSUPPORTED" or "access token" in message.lower() or "oauth" in message.lower():
        return (
            "Authentication error: OAuth token passed where an API key is required, or credential type is unsupported. "
            "Please create a standard API key at https://aistudio.google.com/apikey."
        )

    # 2. Invalid or expired key
    if status_code == 401 or status == "UNAUTHENTICATED" or reason in ("API_KEY_INVALID", "API_KEY_EXPIRED"):
        return (
            "Invalid or expired Gemini API key. Please check your GEMINI_API_KEY in backend/.env "
            "or create a new key at https://aistudio.google.com/apikey."
        )

    # 3. Permission denied / Generative Language API disabled
    if status_code == 403 or status == "PERMISSION_DENIED":
        return (
            "Gemini API permission denied (403): Ensure the Generative Language API is enabled in your Google Cloud / AI Studio "
            "project and your API key has permission to access it."
        )

    # 4. Model not found or deprecated
    if status_code == 404 or status == "NOT_FOUND":
        detail_msg = f" ({message})" if message else ""
        return (
            f"The Gemini model '{target_model}' is not available or has been deprecated{detail_msg}. "
            "Automatic fallback to alternate models is in progress, or check GET /models for available models."
        )

    # 5. Service temporarily unavailable / high demand
    if status_code == 503 or status == "UNAVAILABLE":
        return (
            f"The Gemini model '{target_model}' is temporarily unavailable due to high demand (503). "
            "Automatic fallback to alternate models is in progress."
        )

    # 6. Quota exceeded / rate limit
    if status_code == 429 or status == "RESOURCE_EXHAUSTED":
        return (
            "Gemini API quota exceeded (429). Please wait a moment and try again, "
            "or check your usage limits at https://aistudio.google.com."
        )

    # 7. General API error
    clean_msg = message or f"HTTP status {status_code}"
    return f"Gemini API error ({target_model}): {clean_msg}"


def _generate_with_ollama(question: str, context: str) -> tuple[str, str | None]:
    """Generates an answer using a local Ollama instance (e.g. Llama 3.1)."""
    url = f"{OLLAMA_API_URL}/api/generate"
    safe_context = (context or "No context available.")[:2000]
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"Context: {safe_context}\n\nQuestion: {question}\n\nAnswer concisely:",
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.2,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 500:
            return "", f"Ollama Server Error: Try restarting the Ollama app or using a smaller model like {OLLAMA_MODEL}."
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return text or "I cannot find the answer in the document.", None
    except requests.exceptions.RequestException as e:
        return "", f"Ollama connection error: {e}"


def _gemini_generate_once(question: str, context: str) -> tuple[str, str | None]:
    """Non-streaming generation with dynamic model discovery and fallback."""
    key = get_gemini_api_key()
    key_ok, key_msg = validate_gemini_key(key)
    if not key_ok:
        if ENABLE_OLLAMA_FALLBACK:
            return _generate_with_ollama(question, context)
        return "", key_msg

    candidates = get_candidate_models()
    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(question, context)}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }

    last_error = ""
    for model in candidates:
        url = f"{GEMINI_BASE_URL}/{model}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=(8, 30))
            if resp.status_code == 200:
                set_active_working_model(model)
                text = _extract_gemini_text(resp.json()).strip()
                return text or "I cannot find the answer in the document.", None

            # Terminal auth / quota errors: do not loop across models
            if resp.status_code in (401, 403, 429):
                err_msg = _parse_gemini_error(resp, model)
                if ENABLE_OLLAMA_FALLBACK:
                    logger.warning("Gemini failed (%d), falling back to Ollama: %s", resp.status_code, err_msg)
                    return _generate_with_ollama(question, context)
                return "", err_msg

            # Model unavailable (404 or 503) -> try next candidate model
            err_msg = _parse_gemini_error(resp, model)
            last_error = err_msg
            logger.warning("Model '%s' failed (HTTP %d). Trying fallback... (%s)", model, resp.status_code, err_msg)
            continue

        except requests.exceptions.Timeout:
            last_error = f"Model '{model}' timed out."
            logger.warning("Model '%s' timed out. Trying fallback...", model)
            continue
        except requests.exceptions.RequestException as exc:
            last_error = f"Connection error with model '{model}': {exc}"
            logger.warning("Request failed for model '%s': %s", model, exc)
            continue

    if ENABLE_OLLAMA_FALLBACK:
        logger.warning("All Gemini candidate models failed, falling back to Ollama.")
        return _generate_with_ollama(question, context)

    return "", last_error or "All available Gemini models failed to generate content."


def stream_gemini_answer(question: str, context: str):
    """Streams response from Gemini API using SSE with dynamic model fallback."""
    key = get_gemini_api_key()
    key_ok, key_msg = validate_gemini_key(key)
    if not key_ok:
        if ENABLE_OLLAMA_FALLBACK:
            ans, err = _generate_with_ollama(question, context)
            yield err or ans
            return
        yield key_msg
        return

    candidates = get_candidate_models()
    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(question, context)}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }

    last_error = ""
    for model in candidates:
        url = f"{GEMINI_BASE_URL}/{model}:streamGenerateContent"

        for attempt in range(1, GEMINI_RETRY_ATTEMPTS + 1):
            try:
                resp = requests.post(
                    url,
                    params={"alt": "sse"},
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=(8, 60),
                )
                if resp.status_code == 429:
                    if attempt < GEMINI_RETRY_ATTEMPTS:
                        time.sleep(GEMINI_RETRY_DELAY * attempt)
                        continue
                    yield _parse_gemini_error(resp, model)
                    return

                if resp.status_code == 200:
                    set_active_working_model(model)
                    got_text = False
                    for chunk in _parse_sse_stream(resp):
                        got_text = True
                        yield chunk
                    if got_text:
                        return
                    text, err = _gemini_generate_once(question, context)
                    yield err or text
                    return

                if resp.status_code in (401, 403):
                    err_msg = _parse_gemini_error(resp, model)
                    if ENABLE_OLLAMA_FALLBACK:
                        ans, o_err = _generate_with_ollama(question, context)
                        yield o_err or ans
                        return
                    yield err_msg
                    return

                # Model 404 or 503 -> try next candidate model
                last_error = _parse_gemini_error(resp, model)
                logger.warning("Stream with model '%s' returned HTTP %d. Trying next candidate model...", model, resp.status_code)
                break

            except requests.exceptions.Timeout:
                if attempt < GEMINI_RETRY_ATTEMPTS:
                    time.sleep(GEMINI_RETRY_DELAY)
                    continue
                last_error = f"Gemini request with model '{model}' timed out."
                break
            except requests.exceptions.RequestException as exc:
                last_error = f"Connection error with model '{model}': {exc}"
                break

    if ENABLE_OLLAMA_FALLBACK:
        logger.warning("All Gemini candidate models failed to stream, falling back to Ollama.")
        ans, err = _generate_with_ollama(question, context)
        yield err or ans
        return

    yield last_error or "Unable to generate an answer from any available Gemini model."


# ------------------------------------------------------------
# File cleanup
# ------------------------------------------------------------
def cleanup_old_files():
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
    def loop():
        while True:
            time.sleep(3600)
            cleanup_old_files()
    threading.Thread(target=loop, daemon=True).start()


schedule_cleanup()

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.route("/health")
def health():
    diag = get_runtime_diagnostics()
    diag["embedding_model"] = embedding_model.model_type
    return jsonify(diag)


@app.route("/diagnostics")
def diagnostics():
    diag = get_runtime_diagnostics()
    diag["embedding_model"] = embedding_model.model_type
    return jsonify(diag)


@app.route("/models", methods=["GET"])
def get_models():
    key = get_gemini_api_key()
    if not key:
        return jsonify({"ok": False, "error": "GEMINI_API_KEY is not set"}), 400
    key_ok, key_msg = validate_gemini_key(key)
    if not key_ok:
        return jsonify({"ok": False, "error": key_msg}), 400

    refresh = request.args.get("refresh", "false").lower() == "true"
    models = list_available_gemini_models(key, force_refresh=refresh)
    return jsonify({
        "ok": True,
        "configured_model": get_configured_model(),
        "active_model": get_gemini_model(),
        "candidate_order": get_candidate_models(),
        "available_models": models,
        "total_available": len(models),
    })


@app.route("/test-key", methods=["GET"])
def test_key():
    key = get_gemini_api_key()
    if not key:
        return jsonify({"ok": False, "error": "GEMINI_API_KEY is not set"}), 400
    key_ok, key_msg = validate_gemini_key(key)
    if not key_ok:
        return jsonify({"ok": False, "error": key_msg}), 400

    text, err = _gemini_generate_once("Reply with exactly: Hello World", "Test.")
    if err:
        return jsonify({"ok": False, "error": err}), 401
    return jsonify({
        "ok": True,
        "model_configured": get_configured_model(),
        "model_used": get_gemini_model(),
        "response": text[:200]
    })


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("pdf") or request.files.get("file")
    if file is None:
        return jsonify({"error": "Missing file field 'pdf' or 'file'."}), 400
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF."}), 400
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        file.save(filepath)
    except OSError as e:
        return jsonify({"error": "Failed to save file", "details": str(e)}), 500

    try:
        with open(filepath, "rb") as f:
            if f.read(5) != b"%PDF-":
                return jsonify({"error": "Invalid PDF file"}), 400

        page_pairs, pages = extract_pages_text(filepath)
        chunk_items = chunk_pdf_by_page(page_pairs)
        if not chunk_items:
            return jsonify({"error": "No searchable text found in PDF."}), 400

        chunk_texts = [x["text"] for x in chunk_items]
        chunk_pages = [x["page"] for x in chunk_items]
        index, _ = create_vector_store(chunk_texts)
        base_name = os.path.splitext(filename)[0]
        faiss.write_index(index, os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.faiss"))
        with open(os.path.join(VECTOR_STORE_FOLDER, f"{base_name}.chunks.json"), "w", encoding="utf-8") as f:
            json.dump({
                "source_pdf": filename,
                "pages": pages,
                "chunk_size": CHUNK_SIZE,
                "chunks": chunk_texts,
                "chunk_pages": chunk_pages,
            }, f, ensure_ascii=False, indent=2)

        logger.info("Uploaded %s (%d pages, %d chunks)", filename, pages, len(chunk_texts))
        return jsonify({
            "success": True,
            "message": "PDF processed successfully",
            "filename": filename,
            "pages": pages,
            "chunks": len(chunk_texts),
            "chunks_created": len(chunk_texts),
            "preview": chunk_texts[0][:200] + "..." if chunk_texts else "",
            "text_preview": chunk_texts[0][:500] if chunk_texts else "",
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Failed to build vector store", "details": str(e)}), 500
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    key_ok, key_msg = validate_gemini_key()
    if not key_ok and not ENABLE_OLLAMA_FALLBACK:
        return jsonify({"error": key_msg}), 400

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
                yield json.dumps({"source": ""}) + "\n"
                yield "I could not find relevant information in the document."
            return Response(stream_with_context(no_context_stream()), mimetype="text/plain; charset=utf-8", headers=_STREAM_HEADERS)

        context = "\n\n---\n\n".join(m["chunk"] for m in top_matches)
        pages = [m.get("page") for m in top_matches if isinstance(m.get("page"), int)]
        meta_line = json.dumps({"source": format_page_range(pages)})

        def token_stream():
            yield meta_line + "\n"
            yield from stream_gemini_answer(question, context)

        return Response(stream_with_context(token_stream()), mimetype="text/plain; charset=utf-8", headers=_STREAM_HEADERS)
    except Exception as e:
        return jsonify({"error": "Failed to answer question", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
