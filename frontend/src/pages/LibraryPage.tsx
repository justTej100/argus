import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  bulkDeleteDocuments,
  deleteDocument,
  getDocumentStatus,
  listDocuments,
  uploadDocument,
} from '../api';
import ConfirmDeleteModal from '../components/ConfirmDeleteModal';
import PdfViewer from '../components/PdfViewer';
import type { Document } from '../types';

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'ready' ? 'status-ready' : status === 'error' ? 'status-error' : 'status-processing';
  return <span className={`status ${cls}`}>{status}</span>;
}

type DeleteTarget = { ids: string[]; titles: string[]; label: string };

export default function LibraryPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewDocId, setPreviewDocId] = useState<string | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listDocuments();
      setDocs(list);
      setSelected((prev) => {
        const ids = new Set(list.map((d) => d.id));
        return new Set([...prev].filter((id) => ids.has(id)));
      });
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  const filteredDocs = useMemo(() => {
    const q = searchFilter.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        (d.description || '').toLowerCase().includes(q),
    );
  }, [docs, searchFilter]);

  const pollUntilReady = async (id: string) => {
    for (let i = 0; i < 120; i++) {
      const st = await getDocumentStatus(id);
      if (st.status === 'ready' || st.status === 'error') {
        return st;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    return null;
  };

  const handleFileChange = () => {
    const file = fileRef.current?.files?.[0] ?? null;
    if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    if (file) {
      setPreviewFile(file);
      setPreviewBlobUrl(URL.createObjectURL(file));
      setPreviewDocId(null);
      setPreviewPage(1);
    } else {
      setPreviewFile(null);
      setPreviewBlobUrl(null);
    }
  };

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setUploadMsg('Choose a PDF first.');
      return;
    }
    setUploading(true);
    setUploadMsg('Uploading…');
    try {
      const docTitle = title.trim() || file.name;
      const { id } = await uploadDocument(file, docTitle, description.trim() || undefined);
      setPreviewDocId(id);
      setPreviewFile(null);
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
        setPreviewBlobUrl(null);
      }
      setPreviewPage(1);
      setUploadMsg('Processing PDF…');
      const result = await pollUntilReady(id);
      if (result?.status === 'ready') {
        setUploadMsg('Ready to study.');
        setTitle('');
        setDescription('');
        if (fileRef.current) fileRef.current.value = '';
      } else {
        setUploadMsg(result?.error_message || 'Processing failed.');
      }
      await refresh();
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openBulkDelete = () => {
    if (!selected.size) return;
    const titles = docs.filter((d) => selected.has(d.id)).map((d) => d.title);
    setDeleteError('');
    setDeleteTarget({
      ids: [...selected],
      titles,
      label: `Delete ${titles.length} textbook(s)?`,
    });
  };

  const openSingleDelete = (doc: Document) => {
    setDeleteError('');
    setDeleteTarget({
      ids: [doc.id],
      titles: [doc.title],
      label: `Delete «${doc.title}»?`,
    });
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError('');
    try {
      if (deleteTarget.ids.length === 1) {
        await deleteDocument(deleteTarget.ids[0]);
      } else {
        await bulkDeleteDocuments(deleteTarget.ids);
      }
      setSelected(new Set());
      setDeleteTarget(null);
      await refresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <ConfirmDeleteModal
        open={deleteTarget !== null}
        title={deleteTarget?.label ?? ''}
        items={deleteTarget?.titles ?? []}
        busy={deleting}
        error={deleteError}
        onCancel={() => !deleting && setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />

      <h1 className="page-title">Library</h1>
      <p className="page-sub">Upload PDFs · embeddings build automatically</p>

      <div className="upload-compact panel">
        <p className="section-label">Upload</p>
        <div className="upload-row">
          <input
            id="title"
            className="upload-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (defaults to filename)"
          />
          <label className="btn btn-ghost upload-file-btn">
            {previewFile ? previewFile.name : 'Choose PDF'}
            <input
              id="pdf"
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              hidden
              onChange={handleFileChange}
            />
          </label>
          <button type="button" className="btn btn-primary" disabled={uploading} onClick={handleUpload}>
            {uploading ? 'Working…' : 'Upload'}
          </button>
        </div>
        <textarea
          id="description"
          className="upload-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          rows={2}
        />
        {uploadMsg && <p className={uploadMsg.includes('Ready') ? 'doc-meta upload-msg' : 'login-error upload-msg'}>{uploadMsg}</p>}
        <div className="upload-preview">
          <PdfViewer
            file={previewBlobUrl ?? previewFile ?? undefined}
            documentId={previewBlobUrl || previewFile ? null : previewDocId}
            page={previewPage}
            onPageChange={setPreviewPage}
          />
        </div>
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <p className="section-label">Your textbooks</p>
        <div className="toolbar">
          <input
            placeholder="Search by title or description"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            style={{ padding: '0.4rem 0.6rem', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6 }}
          />
          <button type="button" className="btn btn-ghost" onClick={refresh}>
            Refresh
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setSelected(new Set(docs.map((d) => d.id)))}>
            Select all
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setSelected(new Set())}>
            Clear
          </button>
          <button type="button" className="btn btn-danger" disabled={!selected.size || deleting} onClick={openBulkDelete}>
            Delete ({selected.size})
          </button>
          <Link to="/study" className="btn btn-primary">
            Study
          </Link>
        </div>

        {loading && <p className="loading">Loading…</p>}
        {!loading && filteredDocs.length === 0 && <p className="empty">No textbooks yet.</p>}
        {filteredDocs.map((doc) => (
          <div key={doc.id} className="doc-row">
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
              <input type="checkbox" checked={selected.has(doc.id)} onChange={() => toggle(doc.id)} />
              <div>
                <div className="doc-row-title">{doc.title}</div>
                <div className="doc-meta">
                  {doc.description ? `${doc.description} · ` : ''}
                  <StatusBadge status={doc.status} />
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
              {doc.status === 'ready' && (
                <Link to={`/study?document=${doc.id}`} className="btn btn-ghost">
                  Study
                </Link>
              )}
              <button type="button" className="btn btn-ghost" onClick={() => {
                setPreviewDocId(doc.id);
                setPreviewFile(null);
                if (previewBlobUrl) {
                  URL.revokeObjectURL(previewBlobUrl);
                  setPreviewBlobUrl(null);
                }
                setPreviewPage(1);
              }}>
                Preview
              </button>
              <button type="button" className="btn btn-danger" disabled={deleting} onClick={() => openSingleDelete(doc)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
