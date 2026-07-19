import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { pdfUrl } from '../api';

// Worker must match react-pdf's bundled pdfjs-dist version (see package.json).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

type Props = {
  documentId?: string | null;
  file?: string | File | null;
  page: number;
  onPageChange?: (page: number) => void;
};

type PdfSource = string | File | ArrayBuffer;

export default function PdfViewer({ documentId, file, page, onPageChange }: Props) {
  const [numPages, setNumPages] = useState(0);
  const [inputPage, setInputPage] = useState(String(page));
  const [visiblePage, setVisiblePage] = useState(page);
  const [pdfSource, setPdfSource] = useState<PdfSource | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [pageWidth, setPageWidth] = useState(480);

  const viewportRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const skipScrollSync = useRef(false);
  const scrollRaf = useRef<number | null>(null);
  const visiblePageRef = useRef(page);

  const scrollToPage = useCallback((target: number, behavior: ScrollBehavior = 'smooth') => {
    const clamped = Math.max(1, numPages ? Math.min(target, numPages) : target);
    const el = pageRefs.current.get(clamped);
    const viewport = viewportRef.current;
    if (!el || !viewport) return;

    skipScrollSync.current = true;
    viewport.scrollTo({ top: el.offsetTop - 8, behavior });
    visiblePageRef.current = clamped;
    setVisiblePage(clamped);
    setInputPage(String(clamped));
    onPageChange?.(clamped);
    window.setTimeout(() => {
      skipScrollSync.current = false;
    }, behavior === 'smooth' ? 400 : 50);
  }, [numPages, onPageChange]);

  const updateVisibleFromScroll = useCallback(() => {
    if (skipScrollSync.current) return;
    const viewport = viewportRef.current;
    if (!viewport) return;

    const anchor = viewport.scrollTop + 16;
    let current = 1;
    pageRefs.current.forEach((el, pageNum) => {
      if (el.offsetTop <= anchor) current = pageNum;
    });

    if (current !== visiblePageRef.current) {
      visiblePageRef.current = current;
      setVisiblePage(current);
      setInputPage(String(current));
      onPageChange?.(current);
    }
  }, [onPageChange]);

  useEffect(() => {
    visiblePageRef.current = page;
    setInputPage(String(page));
    if (numPages > 0 && page !== visiblePage) {
      scrollToPage(page, 'auto');
    }
  }, [page, numPages]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setNumPages(0);
    setLoadError('');
    setVisiblePage(1);
    setInputPage('1');

    if (file) {
      setPdfSource(file);
      setLoading(false);
      return;
    }

    if (!documentId) {
      setPdfSource(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setPdfSource(null);
    setLoading(true);

    fetch(pdfUrl(documentId), { credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) {
          let detail = `Server returned ${res.status}`;
          try {
            const body = await res.json();
            if (typeof body.detail === 'string') detail = body.detail;
          } catch {
            /* not JSON */
          }
          if (res.status === 401) {
            throw new Error('Session expired — log in again.');
          }
          if (res.status === 404) {
            throw new Error('PDF not found. It may not have been saved — check storage settings.');
          }
          throw new Error(detail);
        }
        return res.arrayBuffer();
      })
      .then((data) => {
        if (!cancelled) {
          setPdfSource(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : 'Could not load PDF.');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [documentId, file]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const ro = new ResizeObserver(() => {
      setPageWidth(Math.max(240, Math.min(viewport.clientWidth - 24, 640)));
    });
    ro.observe(viewport);
    return () => ro.disconnect();
  }, [pdfSource]);

  const onViewportScroll = () => {
    if (scrollRaf.current !== null) return;
    scrollRaf.current = window.requestAnimationFrame(() => {
      scrollRaf.current = null;
      updateVisibleFromScroll();
    });
  };

  const goToInputPage = () => {
    const parsed = parseInt(inputPage, 10);
    if (!parsed || parsed < 1) {
      setInputPage(String(visiblePage));
      return;
    }
    scrollToPage(parsed);
  };

  if (!file && !documentId) {
    return <p className="empty">Choose a PDF to preview.</p>;
  }

  if (loading) {
    return <p className="loading">Loading PDF…</p>;
  }

  if (loadError) {
    return <p className="empty">{loadError}</p>;
  }

  if (!pdfSource) {
    return <p className="empty">Choose a PDF to preview.</p>;
  }

  const docKey =
    typeof pdfSource === 'string'
      ? pdfSource
      : pdfSource instanceof File
        ? pdfSource.name
        : documentId ?? 'buffer';

  return (
    <div className="pdf-panel">
      <div className="pdf-toolbar">
        <span>
          Page{' '}
          <input
            type="number"
            min={1}
            max={numPages || undefined}
            value={inputPage}
            onChange={(e) => setInputPage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') goToInputPage();
            }}
            onBlur={() => {
              if (inputPage !== String(visiblePageRef.current)) goToInputPage();
            }}
          />{' '}
          {numPages ? `/ ${numPages}` : ''}
        </span>
      </div>
      <div className="pdf-viewport" ref={viewportRef} onScroll={onViewportScroll}>
        <Document
          key={docKey}
          file={pdfSource}
          onLoadSuccess={({ numPages: n }) => {
            setNumPages(n);
            if (page > 1 && page <= n) {
              window.requestAnimationFrame(() => scrollToPage(page, 'auto'));
            }
          }}
          loading={<p className="loading">Loading PDF…</p>}
          error={<p className="empty">Could not render PDF. The file may be corrupt or password-protected.</p>}
        >
          <div className="pdf-pages">
            {numPages > 0 &&
              Array.from({ length: numPages }, (_, index) => {
                const pageNumber = index + 1;
                return (
                  <div
                    key={`page_${pageNumber}`}
                    className="pdf-page-wrap"
                    data-page={pageNumber}
                    ref={(el) => {
                      if (el) pageRefs.current.set(pageNumber, el);
                      else pageRefs.current.delete(pageNumber);
                    }}
                  >
                    <Page
                      pageNumber={pageNumber}
                      width={pageWidth}
                      renderTextLayer
                      renderAnnotationLayer
                    />
                  </div>
                );
              })}
          </div>
        </Document>
      </div>
    </div>
  );
}
