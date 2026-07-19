import { useCallback, useEffect, useState } from 'react';
import { getFeed } from '../api';
import PdfViewer from '../components/PdfViewer';
import type { FeedPost } from '../types';

function timeAgo(iso?: string): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function FeedPage() {
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [pdfDocId, setPdfDocId] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);

  const load = useCallback(async () => {
    try {
      const res = await getFeed(50);
      setPosts(res.posts);
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load feed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="feed-page">
      <header className="feed-header">
        <h1>Home</h1>
        <p className="feed-sub">Doomscroll the textbook. Chapter accounts post. LeetCode drops in too.</p>
      </header>

      {loading && <p className="muted pad">Loading feed…</p>}
      {error && <p className="error-banner">{error}</p>}

      {!loading && !posts.length && (
        <div className="empty-feed">
          <p className="empty-title">Silence on the wire</p>
          <p className="muted">Upload a textbook in Library — chapter personas will start posting.</p>
        </div>
      )}

      <div className="feed-stream">
        {posts.map((post) => {
          const acc = post.account || { handle: 'unknown', display_name: 'Unknown', kind: 'textbook', avatar_key: '?' };
          return (
            <article key={post.id} className="post">
              <div className="post-avatar" aria-hidden>
                {(acc.avatar_key || acc.handle || '?').slice(0, 2).toUpperCase()}
              </div>
              <div className="post-body">
                <div className="post-meta">
                  <span className="post-name">{acc.display_name}</span>
                  <span className="post-handle">@{acc.handle}</span>
                  <span className="post-kind">{acc.kind}</span>
                  {post.created_at && <span className="post-time">{timeAgo(String(post.created_at))}</span>}
                </div>
                <p className="post-text">{post.body}</p>
                <div className="post-actions">
                  {post.document_id && post.page_number != null && (
                    <button
                      type="button"
                      className="post-chip"
                      onClick={() => {
                        setPdfDocId(post.document_id!);
                        setPdfPage(Number(post.page_number));
                      }}
                    >
                      Open p{post.page_number}
                    </button>
                  )}
                  {post.leetcode_url && (
                    <a className="post-chip leetcode" href={post.leetcode_url} target="_blank" rel="noreferrer">
                      LeetCode →
                    </a>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {pdfDocId && (
        <div className="pdf-modal" role="dialog" aria-modal="true">
          <div className="pdf-modal-bar">
            <span>
              PDF · page {pdfPage}
            </span>
            <button type="button" className="btn-ghost" onClick={() => setPdfDocId(null)}>
              Close
            </button>
          </div>
          <PdfViewer documentId={pdfDocId} page={pdfPage} />
        </div>
      )}
    </div>
  );
}
