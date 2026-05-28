/**
 * Chat UI — the homepage and main product experience.
 *
 * This is a "use client" component, meaning it runs in the browser (not on the
 * server). It needs to be client-side because it holds interactive state: the
 * message history, the input field value, the loading stage, etc.
 *
 * Architecture overview:
 *   - `messages` array is the source of truth for the conversation.
 *     It's the same shape as the OpenAI messages API: [{role, content}, ...].
 *     On every send, the full array is passed to the backend — the server is
 *     stateless and the client owns the history.
 *   - `stage` drives the pipeline progress indicator while loading.
 *     We animate through the 4 agent names on a timer to give the user feedback
 *     during the ~3–5s the backend is working.
 *   - The sources grid is always rendered below each assistant message —
 *     not hidden behind a toggle — so users can see what Argus actually read.
 */

"use client";

import { useState, useRef, useEffect } from "react";

// These come from next.config.ts → env, which loaded them from the root .env.
// NEXT_PUBLIC_* means they're safe to expose to the browser (not secret).
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "demo-key-argus";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Provider = "deepseek" | "gemini";

// The 4 stages of the pipeline, plus idle (not running) and done (finished).
type Stage = "idle" | "search" | "analysis" | "synthesis" | "eval" | "done";

/** One post/repo/story that Argus retrieved and the AI read. */
interface Source {
  source: string;        // "reddit", "hackernews", "github", etc.
  title: string;
  url: string;
  body: string;          // post text / repo description (may be empty)
  author: string | null;
  container: string | null;  // subreddit (r/rust), org, "HackerNews"
  published_at: string | null; // unix timestamp string or ISO date
  engagement: Record<string, number>; // upvotes, comments, stars, etc.
}

/** Grounding check results from EvalAgent. */
interface EvalResult {
  passed: boolean;
  score: number;           // 0.0 = nothing verified, 1.0 = fully grounded
  claims_checked: number;
  claims_grounded: number;
  ungrounded_claims: string[];
  explanation: string;     // EvalAgent's prose summary of the grounding check
}

interface Meta {
  provider: string;
  model: string;
  items_retrieved: number;   // total posts scraped
  items_in_context: number;  // posts that made it into the LLM's context
  search_duration_ms: number;
  grounding_score: number;
}

/** One message in the conversation — user or assistant. */
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  // Only assistant messages have these:
  sources?: Source[];
  eval?: EvalResult;
  meta?: Meta;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Shown in the pipeline progress indicator while the backend is working.
const AGENT_STAGES = [
  { key: "search",    label: "SearchAgent",    desc: "Scanning Reddit, HN, GitHub..." },
  { key: "analysis",  label: "AnalysisAgent",  desc: "Embedding + ranking by relevance..." },
  { key: "synthesis", label: "SynthesisAgent", desc: "Writing your answer..." },
  { key: "eval",      label: "EvalAgent",      desc: "Grounding check..." },
];

// Example queries shown on the empty state to help users get started.
const SUGGESTED = [
  "What are devs saying about AI coding tools right now?",
  "What's the latest drama in crypto?",
  "Most hyped startups this month on HN",
  "What are people building with Rust?",
];

// Tailwind class strings for each source platform badge.
// Keeping these in a lookup dict means we can add new sources without
// touching the rendering code — just add an entry here.
const SOURCE_BADGE: Record<string, string> = {
  reddit:     "bg-orange-950/60 text-orange-400 border-orange-800/50",
  hackernews: "bg-amber-950/60  text-amber-400  border-amber-800/50",
  github:     "bg-purple-950/60 text-purple-400 border-purple-800/50",
  exa:        "bg-sky-950/60    text-sky-400    border-sky-800/50",
};

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/**
 * Convert a published_at timestamp to a human-readable relative time string.
 *
 * Reddit and HN return unix timestamps (seconds since epoch) as strings.
 * GitHub returns ISO 8601 date strings. We handle both.
 */
function timeAgo(published_at: string | null): string {
  if (!published_at) return "";
  // If it's all digits, treat it as a unix timestamp (seconds → ms).
  const ts = /^\d+$/.test(published_at)
    ? parseInt(published_at) * 1000
    : new Date(published_at).getTime();
  if (isNaN(ts)) return "";
  const days = Math.floor((Date.now() - ts) / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  const mo = Math.floor(days / 30);
  return mo === 1 ? "1mo ago" : `${mo}mo ago`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * SourceCard — one retrieved post/repo shown in the sources grid.
 *
 * Every card is a real link to the original post. The body excerpt and
 * engagement numbers let users quickly judge the quality/popularity of
 * the source before clicking through.
 */
function SourceCard({ src }: { src: Source }) {
  const badge = SOURCE_BADGE[src.source] ?? "bg-[#21262d] text-[#8b949e] border-[#30363d]";
  // Only show engagement entries that have a non-zero value — skip empty fields.
  const engagementEntries = Object.entries(src.engagement || {}).filter(([, v]) => v > 0);

  return (
    <a
      href={src.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-[#0d1117] border border-[#30363d] rounded-lg p-3 hover:border-[#58a6ff] transition-colors group"
    >
      {/* Header row: platform badge + subreddit + timestamp */}
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded border ${badge}`}>
          {src.source}
        </span>
        {src.container && (
          <span className="text-[11px] text-[#484f58]">{src.container}</span>
        )}
        {src.published_at && (
          <span className="text-[11px] text-[#484f58] ml-auto">{timeAgo(src.published_at)}</span>
        )}
      </div>

      {/* Post title — this is what the user reads to decide if it's worth clicking */}
      <p className="text-xs text-[#c9d1d9] leading-relaxed line-clamp-2 group-hover:text-white transition-colors mb-1.5">
        {src.title}
      </p>

      {/* Body excerpt — gives a preview of the post content */}
      {src.body && (
        <p className="text-[11px] text-[#484f58] leading-relaxed line-clamp-2 mb-1.5">
          {src.body}
        </p>
      )}

      {/* Engagement numbers — upvotes, comments, stars, etc. */}
      {engagementEntries.length > 0 && (
        <div className="flex items-center gap-3">
          {engagementEntries.map(([k, v]) => (
            <span key={k} className="text-[11px] text-[#484f58]">
              {Number(v).toLocaleString()} {k}
            </span>
          ))}
        </div>
      )}
    </a>
  );
}

/**
 * AssistantBubble — renders one AI response with its sources and grounding info.
 *
 * Structure:
 *   1. The answer text (the AI's response).
 *   2. The sources grid — ALWAYS visible, not behind a toggle.
 *      This is the proof that the answer came from real posts, not memory.
 *   3. A grounding badge showing what % of claims were verifiable.
 */
function AssistantBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className="space-y-4">
      {/* Answer text — whitespace-pre-wrap preserves newlines from the LLM */}
      <div className="text-sm text-[#e6edf3] leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </div>

      {/* Sources grid — always rendered, shows what Argus actually read */}
      {msg.sources && msg.sources.length > 0 && (
        <div>
          {/* Header: how many posts were read, how long it took */}
          <p className="text-[11px] text-[#484f58] mb-2 flex items-center gap-2">
            <span className="font-medium text-[#8b949e]">
              {msg.sources.length} posts read
            </span>
            {msg.meta && (
              <>
                <span>·</span>
                <span>{msg.meta.search_duration_ms}ms</span>
                <span>·</span>
                {/* items_retrieved = total scraped; items_in_context = sent to LLM */}
                <span>{msg.meta.items_retrieved} retrieved, {msg.meta.items_in_context} in context</span>
              </>
            )}
          </p>
          {/* 2-column grid on wider screens, single column on mobile */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {msg.sources.map((src, i) => (
              <SourceCard key={i} src={src} />
            ))}
          </div>
        </div>
      )}

      {/* Grounding badge — color-coded: green ≥80%, yellow ≥60%, red <60% */}
      {msg.eval && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-3">
            <span
              className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                msg.eval.score >= 0.8
                  ? "bg-green-950/60 text-green-400 border-green-900/50"
                  : msg.eval.score >= 0.6
                  ? "bg-yellow-950/60 text-yellow-400 border-yellow-900/50"
                  : "bg-red-950/60 text-red-400 border-red-900/50"
              }`}
            >
              {(msg.eval.score * 100).toFixed(0)}% grounded
            </span>
            {msg.eval.claims_checked > 0 && (
              <span className="text-[11px] text-[#484f58]">
                {msg.eval.claims_grounded}/{msg.eval.claims_checked} claims verified
              </span>
            )}
            {msg.meta && (
              <span className="text-[11px] text-[#484f58] font-mono ml-auto">
                {msg.meta.model}
              </span>
            )}
          </div>
          {/* Show EvalAgent's explanation when the grounding score is imperfect */}
          {msg.eval.explanation && msg.eval.score < 1.0 && (
            <p className="text-[11px] text-[#484f58] leading-relaxed">
              {msg.eval.explanation}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function ChatPage() {
  // `messages` is the full conversation history.
  // We send the entire array to the backend on every request so it can
  // inject prior turns into the LLM prompt for multi-turn context.
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<Provider>("deepseek");

  // Which pipeline stage we're currently animating through (for the progress UI).
  const [stage, setStage] = useState<Stage>("idle");

  const [error, setError] = useState("");

  // Ref to the bottom of the messages list — used to auto-scroll after new messages.
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Ref to the textarea — used to focus it and auto-resize it.
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to the bottom whenever a new message is added or the stage changes.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stage]);

  // Auto-resize the textarea as the user types.
  // We reset to "auto" first so the height shrinks when text is deleted.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [input]);

  /** Clear the conversation and start fresh. */
  function newChat() {
    setMessages([]);
    setInput("");
    setStage("idle");
    setError("");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  /**
   * Send a message and run the full pipeline.
   *
   * Accepts an optional `text` parameter so suggested queries can be sent
   * directly without going through the input field state.
   */
  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || (stage !== "idle" && stage !== "done")) return;

    // Add the user message to state immediately so the UI feels responsive.
    const userMsg: ChatMessage = { id: `${Date.now()}`, role: "user", content: q };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setError("");

    // Show loading state immediately so the user gets instant feedback.
    // Without this, stage stays "idle" for 1.8s and the button stays enabled,
    // which would let a double-send slip through on suggested query clicks.
    setStage("search");

    // Continue cycling through remaining stages on a timer (cosmetic only).
    // The real pipeline runs on the backend — we just animate for UX.
    // Timer is cleared as soon as the actual response arrives.
    const stages: Stage[] = ["search", "analysis", "synthesis", "eval"];
    let si = 1; // start at 1 — "search" was already set above
    const interval = setInterval(() => {
      if (si < stages.length) setStage(stages[si++]);
      else clearInterval(interval);
    }, 1800);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": DEMO_KEY,
        },
        body: JSON.stringify({
          // Send the FULL conversation history every time.
          // The backend extracts the last user message as the search query
          // and uses the rest as conversation context for the LLM.
          messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),
          provider,
        }),
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      clearInterval(interval);
      setStage("done");

      // Append the assistant's response (with sources and eval) to the messages.
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now() + 1}`,
          role: "assistant",
          content: data.brief,
          sources: data.sources,
          eval: data.eval,
          meta: data.meta,
        },
      ]);
    } catch (err: any) {
      clearInterval(interval);
      setStage("idle");
      setError(err.message || "Something went wrong");
    }
  }

  /** Send on Enter, newline on Shift+Enter (standard chat behavior). */
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  // Pipeline is running when stage is anything other than idle/done.
  const isRunning = stage !== "idle" && stage !== "done";
  // Which stage index we're on (used to show earlier stages as "done").
  const stageIndex = AGENT_STAGES.findIndex((s) => s.key === stage);
  // Just the user messages — shown as a history list in the sidebar.
  const userQueries = messages.filter((m) => m.role === "user");

  return (
    // h-[calc(100vh-61px)] = full viewport height minus the nav bar height (≈61px).
    // This makes the chat area fill the remaining screen without page-level scrolling.
    <div className="flex h-[calc(100vh-61px)]">

      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside className="w-60 border-r border-[#30363d] flex flex-col bg-[#0d1117] flex-shrink-0">
        <div className="p-3">
          <button
            onClick={newChat}
            className="w-full flex items-center gap-2 bg-[#161b22] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white hover:bg-[#21262d] transition-colors"
          >
            {/* Plus icon */}
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
              <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            New Chat
          </button>
        </div>

        {/* Provider toggle — switch between DeepSeek and Gemini */}
        <div className="px-3 pb-3">
          <p className="text-[11px] text-[#484f58] mb-1.5 uppercase tracking-wider">Model</p>
          <div className="flex gap-1 bg-[#161b22] border border-[#30363d] rounded-lg p-1">
            {(["deepseek", "gemini"] as Provider[]).map((p) => (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className={`flex-1 text-[11px] py-1 rounded-md font-medium transition-colors ${
                  provider === p
                    ? "bg-[#58a6ff] text-black"   // active: blue pill
                    : "text-[#8b949e] hover:text-white"
                }`}
              >
                {p === "deepseek" ? "DeepSeek" : "Gemini"}
              </button>
            ))}
          </div>
        </div>

        {/* Session history — the user's queries in this tab session */}
        {userQueries.length > 0 && (
          <div className="px-3 flex-1 overflow-y-auto min-h-0">
            <p className="text-[11px] text-[#484f58] mb-1.5 uppercase tracking-wider">This session</p>
            <div className="space-y-0.5">
              {userQueries.map((m) => (
                // `title` shows the full text on hover if it's truncated.
                <div
                  key={m.id}
                  className="text-[11px] text-[#8b949e] px-2 py-1.5 rounded hover:bg-[#161b22] truncate cursor-default"
                  title={m.content}
                >
                  {m.content}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Source legend — quick reference for the colored platform badges */}
        <div className="p-3 border-t border-[#30363d] mt-auto">
          <p className="text-[11px] text-[#484f58] mb-1.5 uppercase tracking-wider">Sources</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(SOURCE_BADGE).map(([src, cls]) => (
              <span key={src} className={`text-[11px] px-1.5 py-0.5 rounded border ${cls}`}>
                {src}
              </span>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Main chat pane ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Scrollable messages area */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 && !isRunning ? (

            /* Empty state — shown before the first message */
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-lg px-6">
                {/* Logo icon */}
                <div className="w-12 h-12 rounded-2xl bg-[#58a6ff]/10 border border-[#58a6ff]/20 flex items-center justify-center mx-auto mb-5">
                  <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                    <circle cx="11" cy="11" r="9" stroke="#58a6ff" strokeWidth="1.5"/>
                    <path d="M7 11c0-2.2 1.8-4 4-4s4 1.8 4 4" stroke="#58a6ff" strokeWidth="1.5" strokeLinecap="round"/>
                    <circle cx="11" cy="14" r="1" fill="#58a6ff"/>
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  What&apos;s everyone talking about?
                </h2>
                <p className="text-sm text-[#8b949e] leading-relaxed mb-6">
                  Ask anything. Argus reads real posts from Reddit, HackerNews, and GitHub right
                  now — then uses AI to tell you what people are actually saying.
                </p>
                {/* Suggested queries — clicking one sends it immediately */}
                <div className="grid grid-cols-1 gap-2 text-left">
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="text-sm text-[#8b949e] bg-[#161b22] border border-[#30363d] rounded-lg px-4 py-3 hover:border-[#58a6ff] hover:text-white transition-colors text-left"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>

          ) : (

            /* Message list */
            <div className="max-w-3xl mx-auto px-6 py-8 space-y-10">
              {messages.map((msg) =>
                msg.role === "user" ? (

                  /* User bubble — right-aligned blue pill */
                  <div key={msg.id} className="flex justify-end">
                    <div className="bg-[#58a6ff] text-black rounded-2xl rounded-tr-sm px-5 py-3 max-w-sm text-sm leading-relaxed font-medium">
                      {msg.content}
                    </div>
                  </div>

                ) : (

                  /* Assistant response — answer + sources + grounding */
                  <div key={msg.id}>
                    <AssistantBubble msg={msg} />
                  </div>
                )
              )}

              {/* Pipeline progress indicator — shown while the backend is working */}
              {isRunning && (
                <div className="space-y-2 pl-1">
                  {AGENT_STAGES.map((s, i) => {
                    const isActive = s.key === stage;
                    // A stage is "done" if the current stage index is past it.
                    const isDone = stageIndex > i;
                    return (
                      <div key={s.key} className="flex items-center gap-3">
                        <div
                          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors ${
                            isDone    ? "bg-[#3fb950]"                   // green = done
                            : isActive ? "bg-[#58a6ff] animate-pulse"    // blue pulsing = active
                            :            "bg-[#30363d]"                  // grey = not yet
                          }`}
                        />
                        <span
                          className={`text-xs font-mono transition-colors ${
                            isDone ? "text-[#3fb950]" : isActive ? "text-white" : "text-[#484f58]"
                          }`}
                        >
                          {s.label}
                        </span>
                        <span className="text-xs text-[#484f58]">
                          {isActive ? s.desc : isDone ? "done" : "—"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Error message — shown if the API call fails */}
              {error && (
                <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/40 rounded-lg p-3">
                  {error}
                </p>
              )}

              {/* Invisible div at the bottom — scrolled into view after each new message */}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Input bar ── fixed at the bottom of the chat pane */}
        <div className="border-t border-[#30363d] p-4 bg-[#0d1117]">
          <div className="max-w-3xl mx-auto">
            <div className="flex gap-3 items-end bg-[#161b22] border border-[#30363d] rounded-xl px-4 py-3 focus-within:border-[#58a6ff] transition-colors">
              {/*
                Textarea instead of input so users can write multi-line queries
                with Shift+Enter. Auto-resizes via the useEffect above.
              */}
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Ask about any topic, trend, or idea..."
                rows={1}
                disabled={isRunning}
                className="flex-1 bg-transparent text-white placeholder-[#484f58] resize-none outline-none text-sm leading-relaxed disabled:opacity-50"
              />
              <button
                onClick={() => send()}
                disabled={isRunning || !input.trim()}
                className="bg-[#58a6ff] text-black rounded-lg px-4 py-1.5 text-sm font-semibold hover:bg-[#79b8ff] disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
              >
                {isRunning ? (
                  /* Three bouncing dots while loading */
                  <span className="flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:0ms]" />
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:150ms]" />
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:300ms]" />
                  </span>
                ) : (
                  /* Send icon */
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M13 1L1 5.5l5 1.5 1.5 5L13 1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                  </svg>
                )}
              </button>
            </div>
            <p className="text-[11px] text-[#484f58] text-center mt-2">
              Enter to send · Shift+Enter for newline · Results grounded in real posts
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
