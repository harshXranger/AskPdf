import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
// import "./PDFViewer.css";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

const PDFViewer = forwardRef(function PDFViewer({ fileUrl }, ref) {
  const scrollRef = useRef(null);
  const canvasRefs = useRef([]);

  const [pdfDoc, setPdfDoc] = useState(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1.25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load PDF
  useEffect(() => {
    if (!fileUrl) return;
    let mounted = true;
    setLoading(true);
    setError("");

    getDocument(fileUrl).promise
      .then((pdf) => {
        if (!mounted) return;
        setPdfDoc(pdf);
        setNumPages(pdf.numPages);
        setCurrentPage(1);
        canvasRefs.current = [];
      })
      .catch((err) => {
        console.error(err);
        if (mounted) setError("Failed to load PDF");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [fileUrl]);

  // Render pages at high resolution (devicePixelRatio)
  useEffect(() => {
    if (!pdfDoc || numPages === 0) return;

    const renderPages = async () => {
      const pixelRatio = window.devicePixelRatio || 1;
      const renderScale = zoom * pixelRatio;       // actual rendering resolution

      for (let i = 0; i < numPages; i++) {
        const canvas = canvasRefs.current[i];
        if (!canvas) continue;

        try {
          const page = await pdfDoc.getPage(i + 1);
          const viewport = page.getViewport({ scale: renderScale });
          const ctx = canvas.getContext("2d");

          // Internal canvas size (high resolution)
          canvas.width = viewport.width;
          canvas.height = viewport.height;

          // CSS display size (normal zoom)
          canvas.style.width = `${viewport.width / pixelRatio}px`;
          canvas.style.height = `${viewport.height / pixelRatio}px`;

          await page.render({ canvasContext: ctx, viewport }).promise;
        } catch (err) {
          console.error("Render error page:", i + 1, err);
        }
      }
    };

    renderPages();
  }, [pdfDoc, numPages, zoom]);

  // Track current page on scroll
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !numPages) return;

    const onScroll = () => {
      const pages = el.querySelectorAll("[data-page]");
      let active = 1;
      for (const p of pages) {
        if (p.offsetTop <= el.scrollTop + 60) {
          active = Number(p.getAttribute("data-page"));
        }
      }
      setCurrentPage(active);
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [numPages]);

  // Imperative API
  useImperativeHandle(ref, () => ({
    scrollToPage(pageNumber) {
      const el = scrollRef.current;
      if (!el) return;
      const page = el.querySelector(`[data-page="${pageNumber}"]`);
      if (page) page.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  }));

  const zoomIn = () => setZoom((z) => Math.min(z + 0.25, 3));
  const zoomOut = () => setZoom((z) => Math.max(z - 0.25, 0.5));

  return (
    <div className="pdf-viewer">
      {loading && (
        <div className="pdf-loader">
          <div className="loader-spinner" />
          <p>Loading PDF...</p>
        </div>
      )}

      {error && (
        <div className="pdf-error">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && numPages > 0 && (
        <div className="pdf-controls">
          <div className="controls-left">
            <div className="page-indicator">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span>{currentPage} / {numPages}</span>
            </div>
          </div>
          <div className="controls-right">
            <button className="zoom-btn" onClick={zoomOut} disabled={zoom <= 0.5} title="Zoom out">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <span className="zoom-value">{Math.round(zoom * 100)}%</span>
            <button className="zoom-btn" onClick={zoomIn} disabled={zoom >= 3} title="Zoom in">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      <div className="pdf-scroll" ref={scrollRef}>
        {numPages === 0 && !loading && !error && (
          <div className="pdf-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
              <path d="M14 2v6h6" />
            </svg>
            <p>No PDF loaded</p>
          </div>
        )}

        {Array.from({ length: numPages }, (_, i) => (
          <div className="pdf-page" key={i} data-page={i + 1}>
            <canvas ref={(el) => (canvasRefs.current[i] = el)} />
            <div className="pdf-page-number">{i + 1}</div>
          </div>
        ))}
      </div>
    </div>
  );
});

export default PDFViewer;