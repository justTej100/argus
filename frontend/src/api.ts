/**
 * HTTP client for the FastAPI backend.
 * All requests use credentials: 'include' for session cookies.
 * Dev: Vite proxies /auth, /documents, /chat, /admin, /me to localhost:8000.
 */
import type { ChatMessage, Document, MeResponse, Scope, Source, StudyMode, StudyResponse } from './types';

export type { MeResponse };

const jsonHeaders = { 'Content-Type': 'application/json' };

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === 'string') {
      const parts = [obj.message];
      if (typeof obj.retry_after_seconds === 'number' && obj.retry_after_seconds > 0) {
        const mins = Math.ceil(obj.retry_after_seconds / 60);
        parts.push(`Next chat in ~${mins} min.`);
      }
      if (typeof obj.remaining_today === 'number') {
        parts.push(`${obj.remaining_today} left today.`);
      }
      return parts.join(' ');
    }
    return JSON.stringify(detail);
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: { ...jsonHeaders, ...init?.headers },
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(formatDetail(detail, `Request failed (${res.status})`));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Session check via /me — 401 means logged out. */
export async function isAuthenticated(): Promise<boolean> {
  const res = await fetch('/me', { credentials: 'include' });
  return res.status === 200;
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>('/me');
}

export function listDocuments(): Promise<Document[]> {
  return request<Document[]>('/documents');
}

export function getDocumentStatus(id: string): Promise<Document & { error_message?: string }> {
  return request(`/documents/${id}/status`);
}

export async function uploadDocument(file: File, title: string, description?: string): Promise<{ id: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title);
  if (description) form.append('description', description);

  const res = await fetch('/documents', {
    method: 'POST',
    credentials: 'include',
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(formatDetail(body.detail, 'Upload failed'));
  }
  return res.json();
}

export function deleteDocument(id: string): Promise<void> {
  return request(`/documents/${id}`, { method: 'DELETE' });
}

export function bulkDeleteDocuments(ids: string[]): Promise<{ deleted: number }> {
  return request('/documents/bulk-delete', {
    method: 'POST',
    body: JSON.stringify({ document_ids: ids }),
  });
}

export function chat(
  messages: ChatMessage[],
  mode: StudyMode,
  scope: Scope,
  emailFlashcards = false,
): Promise<StudyResponse> {
  return request<StudyResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({
      messages,
      mode,
      scope,
      email_flashcards: emailFlashcards,
    }),
  });
}

export function emailFlashcards(topic: string, items: unknown[], sources: Source[]): Promise<void> {
  return request('/flashcards/email', {
    method: 'POST',
    body: JSON.stringify({ topic, items, sources }),
  });
}

export type AdminStats = {
  document_count: number;
  total_vectors: number;
  documents: {
    id: string;
    title: string;
    description?: string | null;
    status: string;
    total_pages?: number | null;
    storage_path?: string;
    chunk_count: number;
  }[];
};

export type AdminConfig = {
  supabaseTableUrl: string | null;
  storageUrl: string | null;
};

export function getAdminConfig(): Promise<AdminConfig> {
  return request('/admin/config');
}

export function getAdminStats(): Promise<AdminStats> {
  return request('/admin/stats');
}

export function getAdminChunks(documentId: string, limit = 5): Promise<{ chunks: { text: string; page_number: number; metadata: Record<string, unknown> }[] }> {
  return request(`/admin/documents/${encodeURIComponent(documentId)}/chunks?limit=${limit}`);
}

export function pdfUrl(documentId: string): string {
  return `/documents/${encodeURIComponent(documentId)}/file`;
}

export function extractPages(text: string): number[] {
  const pages: number[] = [];
  const seen = new Set<number>();
  const re = /\[p(\d+)\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const p = parseInt(m[1], 10);
    if (!seen.has(p)) {
      seen.add(p);
      pages.push(p);
    }
  }
  return pages;
}
