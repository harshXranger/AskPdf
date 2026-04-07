import React from "react";

function UploadResult({ result, onNewUpload }) {
  if (!result) return null;

  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard?.writeText;
  const previewText = result.text_preview || "";

  const copyPreview = async () => {
    if (!canCopy || !previewText) return;
    try {
      await navigator.clipboard.writeText(previewText);
    } catch {
      // ignore
    }
  };

  return (
    <div className="resultCard" role="status" aria-live="polite">
      <div className="resultHeader">
        <div className="resultTitleRow">
          <span className="resultStatusIcon" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </span>
          <div className="resultTitle">{result.message || "Upload complete"}</div>
        </div>
        <div className="resultActions">
          <button
            className="resultButton secondary"
            type="button"
            onClick={copyPreview}
            disabled={!canCopy || !previewText}
            title={!previewText ? "No preview text to copy" : "Copy preview text"}
          >
            Copy preview
          </button>
          <button className="resultButton" type="button" onClick={onNewUpload}>
            Upload another
          </button>
        </div>
      </div>

      <div className="resultGrid">
        <div className="resultLabel">Filename</div>
        <div className="resultValue">{result.filename || "-"}</div>

        <div className="resultLabel">Pages</div>
        <div className="resultValue">
          {typeof result.pages === "number" ? result.pages : "-"}
        </div>
      </div>

      <div className="resultSectionTitle">Preview Text</div>
      <pre className="resultPreview prose">
        {previewText ? `"${previewText}"` : "No text extracted."}
      </pre>
    </div>
  );
}

export default UploadResult;

