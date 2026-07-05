import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { chat, emailFlashcards, extractPages } from '../api';
import AnswerBlock from '../components/AnswerBlock';
import PdfViewer from '../components/PdfViewer';
import type { ChatMessage, Document, Source, StudyMode } from '../types';

type FlashcardItem = { front: string; back: string; citations?: string[] };
type QuizItem = { question: string; answer: string; citations?: string[] };

export default function StudyPage() {
  const [searchParams] = useSearchParams();
  const initialDoc = searchParams.get('document') || '';

  const [docs, setDocs] = useState<Document[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState<StudyMode>('chat');
  const [scopeType, setScopeType] = useState<'library' | 'course' | 'document'>(
    initialDoc ? 'document' : 'library',
  );
  const [docId, setDocId] = useState(initialDoc);
  const [course, setCourse] = useState('');
  const [emailFlashcardsFlag, setEmailFlashcardsFlag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [lastFlashcards, setLastFlashcards] = useState<FlashcardItem[] | null>(null);
  const [lastTopic, setLastTopic] = useState('');
  const [pdfDocId, setPdfDocId] = useState<string | null>(initialDoc || null);
  const [pdfPage, setPdfPage] = useState(1);
  const [structured, setStructured] = useState<Record<string, unknown> | null>(null);
  const [citationErrors, setCitationErrors] = useState<string[]>([]);
  const threadRef = useRef<HTMLDivElement>(null);

  const readyDocs = useMemo(() => docs.filter((d) => d.status === 'ready'), [docs]);
  const courses = useMemo(
    () => [...new Set(readyDocs.map((d) => d.course).filter(Boolean))] as string[],
    [readyDocs],
  );

  useEffect(() => {
    import('../api').then(({ listDocuments }) => listDocuments().then(setDocs));
  }, []);

  useEffect(() => {
    if (scopeType === 'document' && docId) {
      setPdfDocId(docId);
      setPdfPage(1);
    }
  }, [scopeType, docId]);

  const openPdf = useCallback((documentId: string, page: number) => {
    setPdfDocId(documentId);
    setPdfPage(page);
  }, []);

  const scrollThread = () => {
    requestAnimationFrame(() => {
      if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
    });
  };

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    const question = prompt.trim();
    if (!question || busy) return;

    setError('');
    setBusy(true);
    setPrompt('');
    setStructured(null);

    const userMsg: ChatMessage = { role: 'user', content: question };
    if (mode === 'chat') {
      setMessages((m) => [...m, userMsg]);
    }
    scrollThread();

    const scope =
      scopeType === 'document'
        ? { type: 'document' as const, document_id: docId }
        : scopeType === 'course'
          ? { type: 'course' as const, course }
          : { type: 'library' as const };

    const payload =
      mode === 'chat' ? [...messages, userMsg] : [userMsg];

    try {
      const result = await chat(payload, mode, scope, emailFlashcardsFlag && mode === 'flashcards');
      setSources(result.sources);
      setCitationErrors(result.eval?.citation_errors || []);

      if (result.sources[0]) {
        openPdf(
          result.sources[0].document_id,
          result.sources[0].page_number || 1,
        );
      }

      if (mode === 'chat') {
        setMessages((m) => [...m, { role: 'assistant', content: result.brief }]);
      } else {
        setStructured(result.structured || null);
        if (mode === 'flashcards') {
          const items = (result.structured?.items as FlashcardItem[]) || [];
          setLastFlashcards(items);
          setLastTopic(question);
        }
      }
      scrollThread();
    } catch (err) {
      if (mode === 'chat') {
        setMessages((m) => m.slice(0, -1));
      }
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const handleEmailFlashcards = async () => {
    if (!lastFlashcards?.length) return;
    try {
      await emailFlashcards(lastTopic, lastFlashcards, sources);
      setError('');
      alert('Flashcards sent to your Gmail.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Email failed');
    }
  };

  const renderAssistantContent = () => {
    if (mode === 'chat' && messages.length) {
      const last = [...messages].reverse().find((m) => m.role === 'assistant');
      if (!last) return null;
      return (
        <AnswerBlock
          text={last.content}
          sources={sources}
          onOpenPage={openPdf}
          citationErrors={citationErrors}
        />
      );
    }

    if (mode === 'quiz' && structured?.items) {
      return (structured.items as QuizItem[]).map((item, i) => (
        <div key={i} className="flashcard">
          <div className="flashcard-front">{item.question}</div>
          <div className="flashcard-back">{item.answer}</div>
          {extractPages((item.citations || []).join(' ')).map((p) => (
            <button key={p} type="button" className="cite-chip" onClick={() => sources[0] && openPdf(sources[0].document_id, p)}>
              p{p}
            </button>
          ))}
        </div>
      ));
    }

    if (mode === 'flashcards' && structured?.items) {
      return (structured.items as FlashcardItem[]).map((item, i) => (
        <div key={i} className="flashcard">
          <div className="flashcard-front">{item.front}</div>
          <div className="flashcard-back">{item.back}</div>
        </div>
      ));
    }

    if (mode === 'summary' && structured) {
      const outline = (structured.outline as { heading: string; bullets: string[] }[]) || [];
      return (
        <div>
          <h3>{String(structured.title || 'Summary')}</h3>
          {outline.map((sec, i) => (
            <div key={i}>
              <h4>{sec.heading}</h4>
              <ul>
                {sec.bullets?.map((b, j) => (
                  <li key={j}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      );
    }

    return null;
  };

  return (
    <div>
      <h1 className="page-title">Study</h1>
      <p className="page-sub">
        {readyDocs.length
          ? `${readyDocs.length} textbook(s) ready`
          : 'Upload a textbook on the Library page first.'}
      </p>

      <div className="scope-row">
        <select value={scopeType} onChange={(e) => setScopeType(e.target.value as typeof scopeType)}>
          <option value="library">All textbooks</option>
          <option value="course">One course</option>
          <option value="document">One textbook</option>
        </select>
        {scopeType === 'course' && (
          <select value={course} onChange={(e) => setCourse(e.target.value)}>
            <option value="">Select course</option>
            {courses.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
        {scopeType === 'document' && (
          <select value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">Select textbook</option>
            {readyDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
        )}
        <select value={mode} onChange={(e) => setMode(e.target.value as StudyMode)}>
          <option value="chat">Tutor chat</option>
          <option value="quiz">Quiz</option>
          <option value="flashcards">Flashcards</option>
          <option value="summary">Summary</option>
        </select>
        {mode === 'flashcards' && (
          <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <input type="checkbox" checked={emailFlashcardsFlag} onChange={(e) => setEmailFlashcardsFlag(e.target.checked)} />
            Email flashcards
          </label>
        )}
      </div>

      <div className="study-grid">
        <div className="study-col">
          <p className="section-label">Conversation</p>
          <div className="panel thread" ref={threadRef}>
            {messages.length === 0 && mode === 'chat' && (
              <p className="empty">Ask a question about your textbook.</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
                <div className="bubble-label">{m.role === 'user' ? 'You' : 'Argus'}</div>
                {m.role === 'user' ? (
                  m.content
                ) : (
                  <AnswerBlock text={m.content} sources={sources} onOpenPage={openPdf} citationErrors={citationErrors} />
                )}
              </div>
            ))}
            {busy && (
              <div className="bubble bubble-assistant">
                <div className="bubble-label">Argus</div>
                <p className="loading">Reading your textbook…</p>
              </div>
            )}
            {mode !== 'chat' && structured && (
              <div className="bubble bubble-assistant">
                <div className="bubble-label">Argus</div>
                {renderAssistantContent()}
              </div>
            )}
          </div>

          <form className="composer panel" onSubmit={submit}>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask your tutor… (Enter to send)"
              rows={3}
              disabled={busy || !readyDocs.length}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="composer-actions">
              <button type="submit" className="btn btn-primary" disabled={busy || !readyDocs.length}>
                Send
              </button>
              {mode === 'flashcards' && lastFlashcards?.length ? (
                <button type="button" className="btn btn-ghost" onClick={handleEmailFlashcards}>
                  Email last flashcards
                </button>
              ) : null}
            </div>
            {error && <p className="login-error">{error}</p>}
          </form>
        </div>

        <div className="study-col">
          <div className="panel">
            <p className="section-label">Sources</p>
            <div className="sources-list">
              {sources.length === 0 && <p className="empty">Retrieved excerpts appear here.</p>}
              {sources.map((s, i) => (
                <div
                  key={i}
                  className="source-item"
                  onClick={() => openPdf(s.document_id, s.page_number)}
                  onKeyDown={(e) => e.key === 'Enter' && openPdf(s.document_id, s.page_number)}
                  role="button"
                  tabIndex={0}
                >
                  <div className="source-item-title">
                    {s.document_title || 'Textbook'} · p{s.page_number}
                  </div>
                  <div className="source-excerpt">{s.text}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel pdf-panel">
            <p className="section-label">Textbook PDF</p>
            {scopeType === 'document' && (
              <select
                value={pdfDocId || ''}
                onChange={(e) => {
                  setPdfDocId(e.target.value);
                  setPdfPage(1);
                }}
                style={{ marginBottom: '0.5rem', width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.4rem' }}
              >
                {readyDocs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
            )}
            <PdfViewer documentId={pdfDocId} page={pdfPage} onPageChange={setPdfPage} />
          </div>
        </div>
      </div>
    </div>
  );
}
