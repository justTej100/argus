import { useEffect, useMemo, useState } from 'react';
import { extractPages, listDocuments, listSections, study } from '../api';
import PdfViewer from '../components/PdfViewer';
import { useMe } from '../me';
import type { Document, DocumentSection, Source, StudyMode } from '../types';

type FlashcardItem = { front: string; back: string; citations?: string[] };
type QuizItem = { question: string; answer: string; citations?: string[] };

export default function StudyPage() {
  const me = useMe();
  const [docs, setDocs] = useState<Document[]>([]);
  const [docId, setDocId] = useState('');
  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [sectionId, setSectionId] = useState('');
  const [mode, setMode] = useState<StudyMode>('quiz');
  const [emailMe, setEmailMe] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [structured, setStructured] = useState<Record<string, unknown> | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [citationErrors, setCitationErrors] = useState<string[]>([]);
  const [pdfDocId, setPdfDocId] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);

  const readyDocs = useMemo(() => docs.filter((d) => d.status === 'ready'), [docs]);

  useEffect(() => {
    listDocuments().then(setDocs).catch(() => setDocs([]));
  }, []);

  useEffect(() => {
    if (!docId) {
      setSections([]);
      setSectionId('');
      return;
    }
    listSections(docId)
      .then((secs) => {
        setSections(secs);
        setSectionId(secs[0]?.id || '');
      })
      .catch(() => {
        setSections([]);
        setSectionId('');
      });
  }, [docId]);

  const generate = async () => {
    if (!docId || busy) return;
    if (sections.length && !sectionId) {
      setError('Pick a chapter/section.');
      return;
    }
    setBusy(true);
    setError('');
    setStructured(null);
    try {
      const result = await study(docId, mode, sectionId || null, emailMe);
      setStructured(result.structured || null);
      setSources(result.sources);
      setCitationErrors(result.eval?.citation_errors || []);
      if (result.sources[0]) {
        setPdfDocId(result.sources[0].document_id);
        setPdfPage(result.sources[0].page_number || 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
    } finally {
      setBusy(false);
    }
  };

  const openPage = (page: number) => {
    if (sources[0]) {
      setPdfDocId(sources[0].document_id);
      setPdfPage(page);
    }
  };

  return (
    <div className="study-page">
      <header className="feed-header">
        <h1>Study</h1>
        <p className="feed-sub">
          Pick a textbook chapter. Generate quiz, flashcards, or a summary — view here or email the pack.
          {me && !me.is_admin && me.study.remaining_today != null
            ? ` · Guest: ${me.study.remaining_today}/${me.study.daily_limit} left today`
            : ''}
        </p>
      </header>

      <div className="study-controls">
        <label className="field-inline">
          <span>Textbook</span>
          <select value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">Select textbook</option>
            {readyDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          <span>Chapter / section</span>
          <select
            value={sectionId}
            onChange={(e) => setSectionId(e.target.value)}
            disabled={!sections.length}
          >
            {!sections.length && <option value="">Whole book (no sections yet)</option>}
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} (p{s.start_page}–{s.end_page})
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          <span>Material</span>
          <select value={mode} onChange={(e) => setMode(e.target.value as StudyMode)}>
            <option value="quiz">Quiz</option>
            <option value="flashcards">Flashcards</option>
            <option value="summary">Summary</option>
          </select>
        </label>
        <label className="check-inline">
          <input type="checkbox" checked={emailMe} onChange={(e) => setEmailMe(e.target.checked)} />
          Email me
        </label>
        <button type="button" className="btn btn-accent" disabled={!docId || busy} onClick={generate}>
          {busy ? 'Generating…' : 'Generate'}
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}
      {citationErrors.length > 0 && (
        <p className="warn-banner">Citation warnings: {citationErrors.join('; ')}</p>
      )}

      <div className="study-results">
        {mode === 'quiz' && Array.isArray(structured?.items) ? (
          <div className="material-list">
            {(structured!.items as QuizItem[]).map((item, i) => (
              <div key={i} className="material-card">
                <p className="material-q">{item.question}</p>
                <p className="material-a">{item.answer}</p>
                <div className="cite-row">
                  {extractPages((item.citations || []).join(' ')).map((p) => (
                    <button key={p} type="button" className="post-chip" onClick={() => openPage(p)}>
                      p{p}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {mode === 'flashcards' && Array.isArray(structured?.items) ? (
          <div className="material-list">
            {(structured!.items as FlashcardItem[]).map((item, i) => (
              <div key={i} className="material-card">
                <p className="material-q">{item.front}</p>
                <p className="material-a">{item.back}</p>
                <div className="cite-row">
                  {extractPages((item.citations || []).join(' ')).map((p) => (
                    <button key={p} type="button" className="post-chip" onClick={() => openPage(p)}>
                      p{p}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {mode === 'summary' && structured ? (
          <div className="material-card summary-card">
            <h2>{String(structured.title || 'Summary')}</h2>
            {((structured.outline as { heading: string; bullets: string[] }[]) || []).map((sec, i) => (
              <div key={i} className="summary-sec">
                <h3>{sec.heading}</h3>
                <ul>
                  {sec.bullets?.map((b, j) => (
                    <li key={j}>{b}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : null}

        {!structured && !busy ? (
          <p className="muted pad">Choose a chapter and hit Generate.</p>
        ) : null}
      </div>

      {pdfDocId && (
        <div className="pdf-dock">
          <div className="pdf-modal-bar">
            <span>Source PDF · p{pdfPage}</span>
            <button type="button" className="btn-ghost" onClick={() => setPdfDocId(null)}>
              Hide
            </button>
          </div>
          <PdfViewer documentId={pdfDocId} page={pdfPage} />
        </div>
      )}
    </div>
  );
}
