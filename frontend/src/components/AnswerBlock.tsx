import ReactMarkdown from 'react-markdown';
import { extractPages } from '../api';
import type { Source } from '../types';

type Props = {
  text: string;
  sources: Source[];
  onOpenPage?: (documentId: string, page: number) => void;
  citationErrors?: string[];
};

export default function AnswerBlock({ text, sources, onOpenPage, citationErrors }: Props) {
  const pages = extractPages(text);

  const resolveDoc = (page: number): string | null => {
    const match = sources.find((s) => s.page_number === page);
    return match?.document_id ?? sources[0]?.document_id ?? null;
  };

  return (
    <div>
      <div className="answer-md">
        <ReactMarkdown>{text}</ReactMarkdown>
      </div>
      {pages.length > 0 && onOpenPage && (
        <div style={{ marginTop: '0.5rem' }}>
          {pages.map((p) => {
            const docId = resolveDoc(p);
            if (!docId) return null;
            return (
              <button
                key={p}
                type="button"
                className="cite-chip"
                onClick={() => onOpenPage(docId, p)}
              >
                p{p}
              </button>
            );
          })}
        </div>
      )}
      {citationErrors && citationErrors.length > 0 && (
        <div className="warn-banner">{citationErrors.join(' ')}</div>
      )}
    </div>
  );
}
