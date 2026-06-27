import React, { useState, useRef } from "react";
// import "./PDFUploader.css";

function PDFUploader({ setPdfUrl, onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = (selectedFile) => {
    if (!selectedFile) return;

    if (selectedFile.type !== "application/pdf") {
      setError("Please select a valid PDF file.");
      setFile(null);
      setFileName("");
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError("File size must be less than 10MB.");
      setFile(null);
      setFileName("");
      return;
    }

    setError("");
    setFile(selectedFile);
    setFileName(selectedFile.name);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    handleFileSelect(selectedFile);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const droppedFile = e.dataTransfer.files[0];
    handleFileSelect(droppedFile);
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a PDF before uploading.");
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
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const removeFile = (e) => {
    e.stopPropagation();
    setFile(null);
    setFileName("");
    setError("");
  };

  return (
    <div className="pdf-uploader">
      {/* Upload Zone */}
      <div
        className={`upload-zone ${isDragOver ? "drag-active" : ""} ${file ? "has-file" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") handleClick();
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
          className="file-input-hidden"
          aria-label="Upload PDF file"
        />

        {!file ? (
          /* Empty State */
          <div className="upload-empty">
            <div className="upload-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div className="upload-text">
              <span className="upload-primary">Drop your PDF here</span>
              <span className="upload-secondary">or click to browse</span>
            </div>
            <div className="upload-hint">PDF only • Max 10MB</div>
          </div>
        ) : (
          /* File Selected State */
          <div className="upload-selected">
            <div className="selected-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/>
                <path d="M14 2v6h6"/>
                <path d="M16 13H8"/>
                <path d="M16 17H8"/>
                <path d="M10 9H8"/>
              </svg>
            </div>
            <div className="selected-info">
              <div className="selected-name">{fileName}</div>
              <div className="selected-size">
                {file.size < 1024 * 1024
                  ? `${(file.size / 1024).toFixed(0)} KB`
                  : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}
              </div>
            </div>
            <button
              className="remove-file-btn"
              onClick={removeFile}
              title="Remove file"
              type="button"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="upload-error" role="alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Upload Button */}
      <button
        className={`upload-btn ${isUploading ? "uploading" : ""} ${file ? "ready" : ""}`}
        onClick={handleUpload}
        disabled={isUploading || !file}
        type="button"
      >
        {isUploading ? (
          <>
            <span className="btn-spinner"></span>
            Uploading...
          </>
        ) : (
          <>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Upload PDF
          </>
        )}
      </button>

      {/* Trust Message */}
      <p className="upload-trust">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
        Your PDF is processed securely. Files are not stored permanently.
      </p>
    </div>
  );
}

export default PDFUploader;