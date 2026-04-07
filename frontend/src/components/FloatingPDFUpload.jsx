import React, { useRef, useState } from "react";

function FloatingPDFUpload({ setPdfUrl, onUploadSuccess }) {
  const inputRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");

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
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="floatingUpload">
      {error && <div className="floatingUploadError">{error}</div>}

      <input
        ref={inputRef}
        className="floatingUploadInput"
        type="file"
        accept="application/pdf"
        onChange={(e) => uploadFile(e.target.files?.[0])}
      />

      <button
        className="floatingUploadButton"
        onClick={handlePick}
        disabled={isUploading}
        type="button"
        title="Replace PDF"
        aria-label="Replace PDF"
      >
        {isUploading ? "Uploading…" : "Replace PDF"}
      </button>
    </div>
  );
}

export default FloatingPDFUpload;

