import React, { useState } from "react";

function PDFUploader({ setPdfUrl, onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFileSelect = (selectedFile) => {
    if (!selectedFile) return;

    if (selectedFile.type !== "application/pdf") {
      setError("Please select a valid PDF file.");
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
        body: formData
      });

      if (!res.ok) {
        let details = "";
        try {
          const errData = await res.json();
          details = errData?.error || errData?.message || "";
        } catch {
          // ignore
        }
        throw new Error(details ? `Upload failed: ${details}` : "Upload failed. Please try again.");
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

  return (
    <div
      className={`uploadBox ${isDragOver ? "dragOver" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="uploadLabel">Upload or drag &amp; drop a PDF</div>

      <input
        type="file"
        accept="application/pdf"
        onChange={handleFileChange}
      />

      <div className="fileInfo">
        {fileName ? `Selected: ${fileName}` : "No file selected yet"}
      </div>

      {error && <div className="errorText">{error}</div>}

      <p className="uploadTrust">
        Your PDF is uploaded for text extraction and Q&amp;A in this session. Start over anytime by
        refreshing the page or uploading a new file.
      </p>

      <button onClick={handleUpload} disabled={isUploading}>
        {isUploading ? "Uploading..." : "Upload PDF"}
      </button>
    </div>
  );
}

export default PDFUploader;