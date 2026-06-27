import React, { useRef, useState } from "react";
// import "./FloatingPDFUpload.css";

function FloatingPDFUpload({ setPdfUrl, onUploadSuccess }) {
  const inputRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [showTooltip, setShowTooltip] = useState(false);

  const handlePick = () => {
    setError("");
    inputRef.current?.click();
  };

  const uploadFile = async (file) => {
    if (!file) return;
    if (file.type !== "application/pdf") {
      setError("Please select a valid PDF file.");
      return;
    }

    setIsUploading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("pdf", file);

      const res = await fetch("http://127.0.0.1:5000/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        let details = "";
        try {
          const errData = await res.json();
          details = errData?.error || errData?.message || "";
        } catch {
          // ignore
        }
        throw new Error(
          details ? `Upload failed: ${details}` : "Upload failed. Please try again."
        );
      }

      const data = await res.json();
      const objectUrl = URL.createObjectURL(file);
      setPdfUrl(objectUrl);
      onUploadSuccess?.(data);
    } catch (err) {
      setError(err.message || "Something went wrong while uploading.");
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <>
      {/* Hidden File Input */}
      <input
        ref={inputRef}
        className="floating-input-hidden"
        type="file"
        accept="application/pdf"
        onChange={(e) => uploadFile(e.target.files?.[0])}
        aria-label="Upload new PDF"
      />

      {/* Floating Button */}
      <div 
        className="floating-upload"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <button
          className={`floating-btn ${isUploading ? "uploading" : ""}`}
          onClick={handlePick}
          disabled={isUploading}
          type="button"
          title="Upload new PDF"
          aria-label="Upload new PDF"
        >
          {isUploading ? (
            <span className="floating-spinner"></span>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          )}
        </button>

        {/* Tooltip */}
        {showTooltip && !isUploading && (
          <div className="floating-tooltip">
            Upload new PDF
          </div>
        )}
      </div>

      {/* Error Toast */}
      {error && (
        <div className="floating-error" role="alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{error}</span>
          <button 
            className="error-close" 
            onClick={() => setError("")}
            aria-label="Dismiss error"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      )}
    </>
  );
}

export default FloatingPDFUpload;