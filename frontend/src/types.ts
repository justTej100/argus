export type Document = {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  total_pages?: number | null;
  has_scan_warning?: boolean;
  error_message?: string | null;
};

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type Scope = {
  type: 'library' | 'document';
  document_id?: string | null;
};

export type Source = {
  source_type: string;
  document_id: string;
  document_title?: string;
  description?: string | null;
  page_number: number;
  text: string;
  similarity?: number;
  metadata?: Record<string, unknown>;
};

export type StudyResponse = {
  query: string;
  type: string;
  brief: string;
  eval: {
    passed: boolean;
    score: number;
    citation_errors: string[];
    explanation: string;
  };
  sources: Source[];
  meta: Record<string, unknown>;
  structured?: Record<string, unknown> | null;
};

export type StudyMode = 'chat' | 'quiz' | 'flashcards' | 'summary';

export type MeResponse = {
  email: string;
  is_admin: boolean;
  chat: {
    cooldown_seconds: number;
    daily_limit: number;
    remaining_today: number | null;
    retry_after_seconds: number;
    unlimited: boolean;
  };
};
