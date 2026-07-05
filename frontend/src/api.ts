/**
 * HTTP client for the FastAPI backend.
 * All requests use credentials: 'include' for session cookies.
 * Dev: Vite proxies /auth, /documents, /chat, /admin to localhost:8000.
 */
import type { ChatMessage, Document, Scope, Source, StudyMode, StudyResponse } from './types';

const jsonHeaders = { 'Content-Type': 'application/json' };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: { ...jsonHeaders, ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Uses existing /chat — 401 means logged out, 400 means session is valid. */
export async function isAuthenticated(): Promise<boolean> {
  const res = await fetch('/chat', {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders,
    body: JSON.stringify({ messages: [] }),
  });
  return res.status !== 401;
}

export function listDocuments(course?: string): Promise<Document[]> {
  const q = course ? `?course=${encodeURIComponent(course)}` : '';
  return request<Document[]>(`/documents${q}`);
}

export function getDocumentStatus(id: string): Promise<Document & { error_message?: string }> {
  return request(`/documents/${id}/status`);
}

export async function uploadDocument(file: File, title: string, course?: string): Promise<{ id: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title);
  if (course) form.append('course', course);

  const res = await fetch('/documents', {
    method: 'POST',
    credentials: 'include',
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Upload failed');
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
    course?: string | null;
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
