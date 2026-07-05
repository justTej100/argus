type Props = {
  open: boolean;
  title: string;
  items: string[];
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function ConfirmDeleteModal({ open, title, items, busy, error, onCancel, onConfirm }: Props) {
  if (!open) return null;

  const shown = items.slice(0, 10);
  const remaining = items.length - shown.length;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
      <div className="modal panel">
        <h2 id="delete-modal-title" className="page-title" style={{ marginBottom: '0.5rem' }}>
          {title}
        </h2>
        <p className="page-sub" style={{ marginBottom: '1rem' }}>
          This removes the PDF and all embeddings. Cannot be undone.
        </p>
        {items.length > 0 && (
          <ul className="modal-list">
            {shown.map((name) => (
              <li key={name}>{name}</li>
            ))}
            {remaining > 0 && <li className="doc-meta">…and {remaining} more</li>}
          </ul>
        )}
        {error && <p className="login-error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" style={{ background: 'var(--danger)' }} disabled={busy} onClick={onConfirm}>
            {busy ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
