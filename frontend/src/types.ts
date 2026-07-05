export type Document = {
  id: string;
  title: string;
  course?: string | null;
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
  type: 'library' | 'course' | 'document';
  document_id?: string | null;
  course?: string | null;
};

export type Source = {
  source_type: string;
  document_id: string;
  document_title?: string;
  course?: string | null;
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
