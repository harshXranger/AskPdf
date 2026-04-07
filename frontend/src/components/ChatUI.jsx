import React, { useState, useRef, useEffect, useCallback } from "react";
import "./ChatUI.css";

const API_URL = "http://127.0.0.1:5000/ask";

function newId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Stream format:
 * - First line: JSON {"source":"Page 1-5"} (single formatted string)
 * - Then: plain answer text
 *
 * Legacy fallback: if we can't parse that first JSON line, treat the whole body as answer.
 */
function formatPageRange(pages) {
  const nums = pages
    .filter((p) => typeof p === "number" && Number.isFinite(p))
    .sort((a, b) => a - b);
  const uniq = [...new Set(nums)];
  if (uniq.length === 0) return "";
  if (uniq.length === 1) return `Page ${uniq[0]}`;
  return `Page ${uniq[0]}-${uniq[uniq.length - 1]}`;
}

async function readAskStream(reader, decoder, onUpdate) {
  let carry = "";
  let metaParsed = false;
  let answerText = "";
  let sourceText = "";

  const flush = (text, src) => {
    onUpdate({ text, source: src });
  };

  while (true) {
    const { done, value } = await reader.read();
    carry += decoder.decode(value || new Uint8Array(), { stream: !done });

    if (!metaParsed) {
      const nl = carry.indexOf("\n");
      if (nl === -1) {
        if (done) {
          answerText = carry;
          sourceText = "";
          flush(answerText, sourceText);
        }
        if (done) break;
        continue;
      }

      const line = carry.slice(0, nl);
      carry = carry.slice(nl + 1);
      metaParsed = true;

      try {
        const meta = JSON.parse(line);
        if (typeof meta?.source === "string") {
          sourceText = meta.source;
        } else if (Array.isArray(meta?.sources)) {
          // Legacy support: derive from page numbers if we get the old format
          const pages = meta.sources.map((s) => (typeof s === "number" ? s : s?.page));
          sourceText = formatPageRange(pages);
        } else {
          sourceText = "";
        }
      } catch {
        sourceText = "";
        carry = `${line}\n${carry}`;
      }

      answerText = carry;
      carry = "";
      flush(answerText, sourceText);
      if (done) break;
      continue;
    }

    answerText += carry;
    carry = "";
    flush(answerText, sourceText);
    if (done) break;
  }

  const tail = decoder.decode();
  if (tail || carry) {
    answerText += tail + carry;
    carry = "";
    flush(answerText, sourceText);
  }
}

export default function ChatUI({ scrollToPage }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const scrollRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isBusy, scrollToBottom]);

  const showConnecting =
    isBusy && messages.length > 0 && messages[messages.length - 1]?.role === "user";

  const send = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isBusy) return;

    setInput("");
    setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
    setIsBusy(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      if (!res.ok) {
        let details = "";
        try {
          const errData = await res.json();
          details = errData?.error || errData?.message || "";
        } catch {
          // ignore
        }
        const reply = details || "Request failed. Please try again.";
        setMessages((prev) => [...prev, { id: newId(), role: "ai", text: reply, source: "" }]);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setMessages((prev) => [
          ...prev,
            {
              id: newId(),
              role: "ai",
              text: "Streaming is not supported in this browser.",
              source: "",
            },
        ]);
        return;
      }

      const aiId = newId();
      setMessages((prev) => [
        ...prev,
        { id: aiId, role: "ai", text: "", source: "" },
      ]);

      const decoder = new TextDecoder();
      await readAskStream(reader, decoder, ({ text: t, source: s }) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === aiId ? { ...m, text: t, source: s } : m))
        );
      });

      setMessages((prev) => {
        const m = prev.find((x) => x.id === aiId);
        if (m && !String(m.text || "").trim()) {
          return prev.map((x) =>
            x.id === aiId ? { ...x, text: "(No response received.)" } : x
          );
        }
        return prev;
      });
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "ai",
          text: err.message || "Something went wrong while getting an answer.",
          source: "",
        },
      ]);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="chat-ui">
      <div className="chat-ui__title">Chat about this PDF</div>

      <div
        ref={scrollRef}
        className="chat-ui__messages"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {messages.length === 0 && !isBusy && (
          <p className="chat-ui__empty">Ask a question about the document.</p>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`chat-ui__row chat-ui__row--${m.role}`}>
            <div className={`chat-ui__bubble chat-ui__bubble--${m.role}`}>
              {m.role === "ai" ? (
                <>
                  <div className="chat-ui__answer-block">
                    <div className="chat-ui__block-label">Answer:</div>
                    <div className="chat-ui__answer-text">
                      {m.text}
                      {isBusy && m.text === "" && (
                        <span className="chat-ui__stream-caret" aria-hidden>
                          ▍
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="chat-ui__sourceBox" aria-label="Source">
                    <b>Source:</b> {m.source || "—"}
                  </div>
                </>
              ) : (
                m.text
              )}
            </div>
          </div>
        ))}

        {showConnecting && (
          <div className="chat-ui__row chat-ui__row--ai" aria-busy="true">
            <div className="chat-ui__bubble chat-ui__bubble--ai chat-ui__bubble--typing">
              <span className="chat-ui__typing-label">AI is typing</span>
              <span className="chat-ui__dots" aria-hidden>
                <span className="chat-ui__dot" />
                <span className="chat-ui__dot" />
                <span className="chat-ui__dot" />
              </span>
            </div>
          </div>
        )}
      </div>

      <form className="chat-ui__form" onSubmit={send}>
        <input
          className="chat-ui__input"
          type="text"
          placeholder="Message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isBusy}
          autoComplete="off"
          aria-label="Message"
          aria-busy={isBusy}
        />
        <button
          className="chat-ui__send"
          type="submit"
          disabled={isBusy || !input.trim()}
        >
          {isBusy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
