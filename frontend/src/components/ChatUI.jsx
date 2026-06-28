import React, { useState, useRef, useEffect, useCallback } from "react";
import "./ChatUI.css";
import ReactMarkdown from "react-markdown";

const API_URL = "http://127.0.0.1:5000/ask";

function newId() {
  return (
    crypto.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

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

  const flush = (text, src) => onUpdate({ text, source: src });

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
          const pages = meta.sources.map((s) =>
            typeof s === "number" ? s : s?.page,
          );
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
    flush(answerText, sourceText);
  }
}

export default function ChatUI() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

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

  useEffect(() => {
    if (!isBusy) inputRef.current?.focus();
  }, [isBusy]);

  const showConnecting =
    isBusy &&
    messages.length > 0 &&
    messages[messages.length - 1]?.role === "user";

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
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: "ai", text: reply, source: "" },
        ]);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "ai",
            text: "Streaming not supported.",
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
          prev.map((m) => (m.id === aiId ? { ...m, text: t, source: s } : m)),
        );
      });

      setMessages((prev) => {
        const m = prev.find((x) => x.id === aiId);
        if (m && !String(m.text || "").trim()) {
          return prev.map((x) =>
            x.id === aiId ? { ...x, text: "(No response received.)" } : x,
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
          text: err.message || "Something went wrong.",
          source: "",
        },
      ]);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="chat">
      {/* Header */}
      <div className="chat__header">
        <span className="chat__header-icon">💬</span>
        <span className="chat__header-title">Chat</span>
        {messages.length > 0 && (
          <span className="chat__header-badge">{messages.length}</span>
        )}
      </div>

      {/* Messages */}
      <div className="chat__messages" ref={scrollRef}>
        {messages.length === 0 && !isBusy && (
          <div className="chat__empty">
            <div className="chat__empty-illustration">📄✨</div>
            <p className="chat__empty-text">Ask anything about your PDF</p>
            <div className="chat__suggestions">
              <button
                className="chat__suggestion"
                onClick={() => setInput("Summarize this document")}
                disabled={isBusy}
              >
                Summarize
              </button>
              <button
                className="chat__suggestion"
                onClick={() => setInput("What are the key takeaways?")}
                disabled={isBusy}
              >
                Key takeaways
              </button>
              <button
                className="chat__suggestion"
                onClick={() => setInput("Explain in simple terms")}
                disabled={isBusy}
              >
                Simplify
              </button>
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`msg msg--${m.role}`}>
            <div className={`msg__bubble msg__bubble--${m.role}`}>
              <div className="msg__text">
                {m.text ? (
                  <ReactMarkdown>{m.text}</ReactMarkdown>
                ) : (
                  <span className="msg__cursor" />
                )}
              </div>
            </div>
          </div>
        ))}

        {showConnecting && (
          <div className="msg msg--ai">
            <div className="msg__bubble msg__bubble--ai msg__bubble--typing">
              <span className="msg__dot" />
              <span className="msg__dot" />
              <span className="msg__dot" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form className="chat__form" onSubmit={send}>
        <div className="chat__input-row">
          <input
            ref={inputRef}
            className="chat__input"
            type="text"
            placeholder="Type your question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isBusy}
            autoComplete="off"
          />
          <button
            className="chat__send"
            type="submit"
            disabled={isBusy || !input.trim()}
          >
            {isBusy ? "⋯" : "↑"}
          </button>
        </div>
      </form>
    </div>
  );
}
