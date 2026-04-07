import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

const PDFViewer = forwardRef(function PDFViewer({ fileUrl }, ref) {
  const scrollRootRef = useRef(null);
  const canvasRefs = useRef([]);

  const [pdfDoc, setPdfDoc] = useState(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [canvasesReadyTick, setCanvasesReadyTick] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const scrollToPage = useCallback((pageNumber) => {
    const root = scrollRootRef.current;
    if (!root || pageNumber == null) return;
    const n = Number(pageNumber);
    if (!Number.isFinite(n) || n < 1) return;

    const el = root.querySelector(`[data-page="${Math.floor(n)}"]`);
    if (el) {
      const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
    }
  }, []);

  useImperativeHandle(ref, () => ({ scrollToPage }), [scrollToPage]);

  useEffect(() => {
    if (!fileUrl) return;

    let mounted = true;
    setLoading(true);
    setError("");

    const loadingTask = getDocument(fileUrl);

    loadingTask.promise
      .then((pdf) => {
        if (!mounted) return;
        setPdfDoc(pdf);
        setNumPages(pdf.numPages);
        setCurrentPage(1);
        canvasRefs.current = [];
        setCanvasesReadyTick((t) => t + 1);
      })
      .catch((err) => {
        console.error(err);
        if (!mounted) return;
        setError("Failed to load PDF");
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => {
      mounted = false;
      loadingTask.destroy();
    };
  }, [fileUrl]);

  useEffect(() => {
    if (!pdfDoc) return;

    const renderPages = async () => {
      for (let pageNum = 1; pageNum <= numPages; pageNum++) {
        const canvas = canvasRefs.current[pageNum - 1];
        if (!canvas) continue;

        try {
          const page = await pdfDoc.getPage(pageNum);
          const viewport = page.getViewport({ scale: zoom });
          const context = canvas.getContext("2d");

          canvas.width = viewport.width;
          canvas.height = viewport.height;
          context.clearRect(0, 0, canvas.width, canvas.height);

          await page.render({
            canvasContext: context,
            viewport,
          }).promise;
        } catch (err) {
          console.error("Render error page:", pageNum, err);
        }
      }
    };

    renderPages();
  }, [pdfDoc, numPages, zoom, canvasesReadyTick]);

  useEffect(() => {
    const container = scrollRootRef.current;
    if (!container || !numPages) return;

    let raf = 0;

    const computeCurrentPage = () => {
      raf = 0;
      const scrollTop = container.scrollTop;
      const pages = container.querySelectorAll("[data-page]");
      if (!pages.length) return;

      const threshold = 40;
      let active = 1;
      for (const el of pages) {
        const pageNum = Number(el.getAttribute("data-page"));
        if (!pageNum) continue;
        if (el.offsetTop <= scrollTop + threshold) active = pageNum;
        else break;
      }
      setCurrentPage(active);
    };

    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(computeCurrentPage);
    };

    container.addEventListener("scroll", onScroll, { passive: true });
    requestAnimationFrame(computeCurrentPage);

    return () => {
      container.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [numPages, zoom]);

  const ZOOM_STEP = 0.2;
  const MAX_ZOOM = 3;
  const MIN_ZOOM = 0.5;

  const zoomIn = () => setZoom((prev) => Math.min(prev + ZOOM_STEP, MAX_ZOOM));
  const zoomOut = () => setZoom((prev) => Math.max(prev - ZOOM_STEP, MIN_ZOOM));

  return (
    <div className="pdfContainer">
      {loading && <div className="fileInfo">Loading PDF...</div>}
      {error && <div className="errorText">{error}</div>}

      <div className="controls">
        <span className="fileInfo">
          Page {currentPage} / {numPages || "?"}
        </span>

        <div className="controlsGroup">
          <button type="button" onClick={zoomOut}>
            -
          </button>
          <span className="zoompercent">{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={zoomIn}>
            +
          </button>
        </div>
      </div>

      <div className="pdfViewer pdfScroll" ref={scrollRootRef}>
        {Array.from({ length: numPages }, (_, index) => {
          const pageNum = index + 1;
          return (
            <div className="pdfPage" data-page={pageNum} key={pageNum}>
              <canvas
                ref={(el) => {
                  canvasRefs.current[index] = el;
                  if (el && numPages) {
                    const ready = canvasRefs.current.filter(Boolean).length;
                    if (ready === numPages) setCanvasesReadyTick((t) => t + 1);
                  }
                }}
                className="pdfCanvas"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
});

PDFViewer.displayName = "PDFViewer";

export default PDFViewer;
