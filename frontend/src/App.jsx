import React, { useEffect, useRef, useState } from "react";
import PDFUploader from "./components/PDFUploader";
import PDFViewer from "./components/PDFViewer";
import FloatingPDFUpload from "./components/FloatingPDFUpload";
import UploadResult from "./components/UploadResult";
import ChatUI from "./components/ChatUI";

function App() {
  const [pdfUrl, setPdfUrl] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const viewerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pdfUrl && typeof pdfUrl === "string" && pdfUrl.startsWith("blob:")) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [pdfUrl]);

  const reset = () => {
    setPdfUrl((prev) => {
      if (prev && typeof prev === "string" && prev.startsWith("blob:")) {
        URL.revokeObjectURL(prev);
      }
      return "";
    });
    setUploadResult(null);
  };

  return (
    <div className={`container${pdfUrl ? " container--workspace" : ""}`}>
      <header className={pdfUrl ? "appHeader appHeader--workspace" : "appHeader"}>
        <h1 className="title">AskPDF</h1>
        <p className="subtitle">
          Ask questions about complex PDFs with an AI-powered reader.
        </p>
      </header>

      {!pdfUrl && (
        <PDFUploader
          setPdfUrl={setPdfUrl}
          onUploadSuccess={(result) => setUploadResult(result)}
        />
      )}

      {pdfUrl && (
        <>
          <div className="workspaceGrid">
            <aside className="workspaceAside">
              <div className="panelEnter panelEnter--1">
                <UploadResult result={uploadResult} onNewUpload={reset} />
              </div>
              {!!uploadResult && (
                <div className="panelEnter panelEnter--2">
                  <ChatUI
                    scrollToPage={(page) => viewerRef.current?.scrollToPage(page)}
                  />
                </div>
              )}
            </aside>
            <div className="workspaceMain panelEnter panelEnter--3">
              <div className="viewerShell">
                <div className="viewerTopBar">
                  <button type="button" className="viewerBackButton" onClick={reset}>
                    <span aria-hidden>←</span>
                    <span>Back to upload</span>
                  </button>
                  <div className="viewerLabel">Viewing uploaded PDF</div>
                </div>
                <PDFViewer ref={viewerRef} fileUrl={pdfUrl} />
              </div>
            </div>
          </div>
          <FloatingPDFUpload
            setPdfUrl={setPdfUrl}
            onUploadSuccess={(result) => setUploadResult(result)}
          />
        </>
      )}
    </div>
  );
}

export default App;
