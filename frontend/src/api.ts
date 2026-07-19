/**
 * HTTP client for the FastAPI backend.
 * Dev: Vite proxies /auth, /documents, /study, /feed, /admin, /me to localhost:8000.
 */
import type {
  Document,
  DocumentSection,
  FeedPost,
  MeResponse,
  NewsItem,
  Source,
  StudyMode,
  StudyResponse,
} from './types';
import type { FlashcardOffer } from './types';

export type { MeResponse, FlashcardOffer };

const jsonHeaders = { 'Content-Type': 'application/json' };

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === 'string') {
      const parts = [obj.message];
      if (typeof obj.retry_after_seconds === 'number' && obj.retry_after_seconds > 0) {
        const mins = Math.ceil(obj.retry_after_seconds / 60);
        parts.push(`Next study in ~${mins} min.`);
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

export function listSections(documentId: string): Promise<DocumentSection[]> {
  return request<DocumentSection[]>(`/documents/${encodeURIComponent(documentId)}/sections`);
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

export function getFeed(limit = 40, cursor?: string): Promise<{ posts: FeedPost[] }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (cursor) q.set('cursor', cursor);
  return request<{ posts: FeedPost[] }>(`/feed?${q}`);
}

export function getNews(): Promise<{ items: NewsItem[] }> {
  return request<{ items: NewsItem[] }>('/news');
}

export function study(
  documentId: string,
  mode: StudyMode,
  sectionId: string | null,
  email = false,
): Promise<StudyResponse> {
  return request<StudyResponse>('/study', {
    method: 'POST',
    body: JSON.stringify({
      document_id: documentId,
      section_id: sectionId,
      mode,
      email,
    }),
  });
}

export function emailFlashcards(topic: string, items: unknown[], sources: Source[]): Promise<void> {
  return request('/flashcards/email', {
    method: 'POST',
    body: JSON.stringify({ topic, items, sources }),
  });
}

export function listFlashcardOffers(): Promise<FlashcardOffer[]> {
  return request<FlashcardOffer[]>('/flashcards/offers');
}

export function subscribeFlashcards(documentId: string): Promise<void> {
  return request('/flashcards/subscribe', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId }),
  });
}

export function unsubscribeFlashcards(documentId: string): Promise<void> {
  return request('/flashcards/unsubscribe', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId }),
  });
}

export function setFlashcardsOpen(documentId: string, enabled: boolean): Promise<{ flashcards_open: boolean }> {
  return request(`/documents/${encodeURIComponent(documentId)}/flashcards-open`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export function broadcastFlashcards(
  documentId: string,
  topic: string,
  items: unknown[],
  sources: Source[],
): Promise<{ sent: number; failed: number }> {
  return request('/flashcards/broadcast', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId, topic, items, sources }),
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

export function getAdminChunks(
  documentId: string,
  limit = 5,
): Promise<{ chunks: { text: string; page_number: number; metadata: Record<string, unknown> }[] }> {
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
