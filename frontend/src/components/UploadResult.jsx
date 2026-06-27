import React from "react";
// import "./UploadResult.css";

function UploadResult({ result, onNewUpload }) {
  if (!result) return null;

  return (
    <div className="ur" role="status" aria-live="polite">
      <div className="ur__row">
        {/* Checkmark */}
        <span className="ur__check">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </span>

        {/* File Info */}
        <div className="ur__info">
          <span className="ur__name" title={result.filename}>
            {result.filename || "document.pdf"}
          </span>
          {typeof result.pages === "number" && (
            <span className="ur__pages">{result.pages} pages</span>
          )}
        </div>

        {/* Upload New Button */}
        <button
          className="ur__btn"
          type="button"
          onClick={onNewUpload}
          title="Upload new document"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default UploadResult;