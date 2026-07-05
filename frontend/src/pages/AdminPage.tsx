import { Fragment, useEffect, useState } from 'react';
import { getAdminChunks, getAdminConfig, getAdminStats, type AdminConfig, type AdminStats } from '../api';

export default function AdminPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [samples, setSamples] = useState<Record<string, { text: string; page_number: number }[]>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([getAdminConfig(), getAdminStats()])
      .then(([cfg, st]) => {
        setConfig(cfg);
        setStats(st);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  const toggleSamples = async (docId: string) => {
    if (expanded === docId) {
      setExpanded(null);
      return;
    }
    setExpanded(docId);
    if (!samples[docId]) {
      try {
        const res = await getAdminChunks(docId, 3);
        setSamples((prev) => ({
          ...prev,
          [docId]: res.chunks.map((c) => ({ text: c.text, page_number: c.page_number })),
        }));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load chunks');
      }
    }
  };

  return (
    <div>
      <h1 className="page-title">Database</h1>
      <p className="page-sub">Vector store stats and Supabase links</p>

      {config && (config.supabaseTableUrl || config.storageUrl) && (
        <div className="panel" style={{ marginBottom: '1rem' }}>
          <p className="section-label">Supabase dashboard</p>
          <div className="toolbar">
            {config.supabaseTableUrl && (
              <a href={config.supabaseTableUrl} target="_blank" rel="noreferrer" className="btn btn-ghost">
                Table editor
              </a>
            )}
            {config.storageUrl && (
              <a href={config.storageUrl} target="_blank" rel="noreferrer" className="btn btn-ghost">
                Storage bucket
              </a>
            )}
          </div>
        </div>
      )}

      {error && <p className="login-error">{error}</p>}

      {stats && (
        <>
          <div className="admin-stats-row">
            <div>
              <div className="admin-stat">{stats.document_count}</div>
              <div className="admin-stat-label">Textbooks</div>
            </div>
            <div>
              <div className="admin-stat">{stats.total_vectors}</div>
              <div className="admin-stat-label">Vector chunks</div>
            </div>
          </div>

          <div className="panel">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Pages</th>
                  <th>Chunks</th>
                  <th>Storage</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {stats.documents.map((doc) => (
                  <Fragment key={doc.id}>
                    <tr>
                      <td>{doc.title}</td>
                      <td>{doc.status}</td>
                      <td>{doc.total_pages ?? '—'}</td>
                      <td>{doc.chunk_count}</td>
                      <td className="doc-meta" style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {doc.storage_path || '—'}
                      </td>
                      <td>
                        <button type="button" className="btn btn-ghost" onClick={() => toggleSamples(doc.id)}>
                          {expanded === doc.id ? 'Hide' : 'Sample'}
                        </button>
                      </td>
                    </tr>
                    {expanded === doc.id && samples[doc.id] && (
                      <tr>
                        <td colSpan={6}>
                          {samples[doc.id].map((c, i) => (
                            <div key={i} className="source-item" style={{ marginBottom: '0.5rem' }}>
                              <div className="source-item-title">p{c.page_number}</div>
                              <div className="source-excerpt">{c.text}</div>
                            </div>
                          ))}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!stats && !error && <p className="loading">Loading…</p>}
    </div>
  );
}
