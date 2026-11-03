import React, { useEffect, useRef, useState } from "react";
import PDFUploader from "./components/PDFUploader";
import PDFViewer from "./components/PDFViewer";
import FloatingPDFUpload from "./components/FloatingPDFUpload";
import UploadResult from "./components/UploadResult";
import SignIn from "./components/SignIn";
import ChatUI from "./components/ChatUI";
import "./App.css";
import { GoogleOAuthProvider } from "@react-oauth/google";

function App() {
  const [pdfUrl, setPdfUrl] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);
  const viewerRef = useRef(null);
  const [showSignIn, setShowSignIn] = useState(false);

  // Load user from localStorage (persistent session)
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem("askpdf_user");
    return saved ? JSON.parse(saved) : null;
  });

  // Responsive detection
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      if (!mobile) setSidebarOpen(true);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Cleanup blob URL
  useEffect(() => {
    return () => {
      if (pdfUrl && pdfUrl.startsWith("blob:")) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  const reset = () => {
    setPdfUrl((prev) => {
      if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
      return "";
    });
    setUploadResult(null);
  };

  return (
    <GoogleOAuthProvider clientId="745884212137-5fjhqvvrcm6mheppc0j918jo1h4pk3kg.apps.googleusercontent.com">
      <div className="app-shell">
        {!pdfUrl ? (
          /* ========== LANDING PAGE ========== */
          <div className="landing-page">
            <nav className="landing-nav">
              <div className="nav-brand">
                <svg className="brand-icon" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M14 2v6h6M16 13H8M16 17H8M10 9H8"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="brand-name">
                  Ask<span className="accent">PDF</span>
                </span>
              </div>
              <div className="nav-actions">
                {user ? (
                  <div className="user-menu">
                    <span className="user-avatar">
                      {user.avatar?.startsWith("http") ? (
                        <img src={user.avatar} alt="" className="avatar-img" />
                      ) : (
                        user.avatar || user.name?.[0]
                      )}
                    </span>
                    <span className="user-name">{user.name}</span>
                    <button
                      className="btn-ghost"
                      onClick={() => {
                        setUser(null);
                        localStorage.removeItem("askpdf_user");
                      }}
                    >
                      Sign out
                    </button>
                  </div>
                ) : (
                  <button
                    className="btn-ghost"
                    onClick={() => setShowSignIn(true)}
                  >
                    Sign In
                  </button>
                )}
              </div>
            </nav>

            <main className="landing-main">
              <div className="landing-content">
                <h1 className="landing-headline">
                  Chat with your{" "}
                  <span className="accent-gradient">documents</span>
                </h1>
                <p className="landing-subheadline">
                  Upload any PDF and get instant answers with AI. Summarize,
                  extract, and understand complex information in seconds.
                </p>
                <div className="landing-upload">
                  <PDFUploader
                    setPdfUrl={setPdfUrl}
                    onUploadSuccess={setUploadResult}
                  />
                </div>
                <p className="landing-trust">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="3" y="11" width="18" height="11" rx="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  Secure & private · Your documents are never stored
                </p>
              </div>
              <div className="landing-visual">
                <div className="preview-card">
                  <div className="preview-header">
                    <div className="preview-dots">
                      <span />
                      <span />
                      <span />
                    </div>
                    <span className="preview-title">document.pdf</span>
                  </div>
                  <div className="preview-chat">
                    <div className="preview-msg user">
                      What are the key takeaways?
                    </div>
                    <div className="preview-msg ai">
                      This document outlines three main strategies for growth…
                    </div>
                  </div>
                </div>
              </div>
            </main>

            <footer className="landing-footer">
              <p>© 2024 AskPDF</p>
            </footer>
          </div>
        ) : (
          /* ========== WORKSPACE ========== */
          <div className="workspace-page">
            <header className="workspace-topbar">
              <div className="topbar-left">
                <button
                  className={`sidebar-toggle ${sidebarOpen ? "active" : ""}`}
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  aria-label="Toggle sidebar"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M9 3v18" />
                  </svg>
                </button>
                <div className="topbar-brand">
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#7c3aed"
                    strokeWidth="2"
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                    <path d="M14 2v6h6" />
                  </svg>
                  <span className="brand-text">
                    Ask<span className="accent">PDF</span>
                  </span>
                </div>
              </div>
              <div className="topbar-center">
                {uploadResult && (
                  <span className="doc-name">{uploadResult.filename}</span>
                )}
              </div>
              <div className="topbar-right">
                <button className="btn-new" onClick={reset}>
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  New
                </button>
              </div>
            </header>

            <div className="workspace-body">
              {isMobile && sidebarOpen && (
                <div
                  className="sidebar-backdrop"
                  onClick={() => setSidebarOpen(false)}
                />
              )}
              <aside className={`chat-sidebar ${sidebarOpen ? "open" : ""}`}>
                <div className="sidebar-inner">
                  <div className="sidebar-header">
                    <UploadResult result={uploadResult} onNewUpload={reset} />
                  </div>
                  <div className="sidebar-chat">
                    {uploadResult && (
                      <ChatUI
                        scrollToPage={(p) =>
                          viewerRef.current?.scrollToPage?.(p)
                        }
                      />
                    )}
                  </div>
                </div>
              </aside>
              <main className="viewer-panel">
                <div className="viewer-toolbar">
                  <button className="btn-back" onClick={reset}>
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M19 12H5M12 19l-7-7 7-7" />
                    </svg>
                    Back
                  </button>
                  <span className="viewer-label">PDF Preview</span>
                </div>
                <div className="viewer-content">
                  <PDFViewer ref={viewerRef} fileUrl={pdfUrl} />
                </div>
              </main>
            </div>

            <FloatingPDFUpload
              setPdfUrl={setPdfUrl}
              onUploadSuccess={setUploadResult}
            />
          </div>
        )}

        {/* Sign-In Modal */}
        <SignIn
          isOpen={showSignIn}
          onClose={() => setShowSignIn(false)}
          user={user}
          setUser={setUser}
        />
      </div>
    </GoogleOAuthProvider>
  );
}

export default App;