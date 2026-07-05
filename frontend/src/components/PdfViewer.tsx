import { useEffect, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { pdfUrl } from '../api';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

type Props = {
  documentId: string | null;
  page: number;
  onPageChange?: (page: number) => void;
};

export default function PdfViewer({ documentId, page, onPageChange }: Props) {
  const [numPages, setNumPages] = useState(0);
  const [inputPage, setInputPage] = useState(String(page));

  useEffect(() => {
    setInputPage(String(page));
  }, [page]);

  if (!documentId) {
    return <p className="empty">Select a textbook to preview.</p>;
  }

  const goTo = (p: number) => {
    const clamped = Math.max(1, numPages ? Math.min(p, numPages) : p);
    onPageChange?.(clamped);
    setInputPage(String(clamped));
  };

  return (
    <div className="pdf-panel">
      <div className="pdf-toolbar">
        <button type="button" className="btn btn-ghost" onClick={() => goTo(page - 1)} disabled={page <= 1}>
          ‹
        </button>
        <span>
          Page{' '}
          <input
            type="number"
            min={1}
            max={numPages || undefined}
            value={inputPage}
            onChange={(e) => setInputPage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') goTo(parseInt(inputPage, 10) || 1);
            }}
          />{' '}
          {numPages ? `/ ${numPages}` : ''}
        </span>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => goTo(page + 1)}
          disabled={numPages > 0 && page >= numPages}
        >
          ›
        </button>
      </div>
      <div className="pdf-viewport">
        <Document
          key={documentId}
          file={pdfUrl(documentId)}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          loading={<p className="loading">Loading PDF…</p>}
          error={<p className="empty">Could not load PDF. Try logging in again.</p>}
          options={{ withCredentials: true }}
        >
          <Page pageNumber={page} width={480} renderTextLayer renderAnnotationLayer />
        </Document>
      </div>
    </div>
  );
}
