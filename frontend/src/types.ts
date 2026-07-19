export type Document = {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  total_pages?: number | null;
  has_scan_warning?: boolean;
  error_message?: string | null;
  flashcards_open?: boolean;
  embed_total?: number;
  embed_done?: number;
  chunks_skipped?: number;
};

export type DocumentSection = {
  id: string;
  document_id: string;
  title: string;
  level: number;
  start_page: number;
  end_page: number;
  sort_key: number;
};

export type FlashcardOffer = {
  document_id: string;
  title: string;
  description?: string | null;
  subscribed: boolean;
  subscriber_count: number;
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
  chapter?: string;
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

export type StudyMode = 'quiz' | 'flashcards' | 'summary';

export type MeResponse = {
  email: string;
  is_admin: boolean;
  study: {
    cooldown_seconds: number;
    daily_limit: number;
    remaining_today: number | null;
    retry_after_seconds: number;
    unlimited: boolean;
  };
};

export type FeedAccount = {
  handle: string;
  display_name: string;
  bio?: string;
  kind: string;
  avatar_key?: string;
  topic?: string | null;
};

export type FeedPost = {
  id: string;
  account_id: string;
  body: string;
  document_id?: string | null;
  page_number?: number | null;
  leetcode_url?: string | null;
  created_at?: string;
  account: FeedAccount;
};

export type NewsItem = {
  kind: string;
  title: string;
  body: string;
  document_id?: string | null;
};
