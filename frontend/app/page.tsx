"use client";

import { useState, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "demo-key-argus";

type Provider = "deepseek" | "gemini";
type Stage = "idle" | "search" | "analysis" | "synthesis" | "eval" | "done";

interface Source {
  source: string;
  title: string;
  url: string;
  body: string;
  author: string | null;
  container: string | null;
  published_at: string | null;
  engagement: Record<string, number>;
}

interface EvalResult {
  passed: boolean;
  score: number;
  claims_checked: number;
  claims_grounded: number;
  ungrounded_claims: string[];
}

interface Meta {
  provider: string;
  model: string;
  items_retrieved: number;
  items_in_context: number;
  search_duration_ms: number;
  grounding_score: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  eval?: EvalResult;
  meta?: Meta;
}

const AGENT_STAGES = [
  { key: "search",    label: "SearchAgent",    desc: "Scanning Reddit, HN, GitHub..." },
  { key: "analysis",  label: "AnalysisAgent",  desc: "Embedding + ranking by relevance..." },
  { key: "synthesis", label: "SynthesisAgent", desc: "Writing your answer..." },
  { key: "eval",      label: "EvalAgent",      desc: "Grounding check..." },
];

const SOURCE_BADGE: Record<string, string> = {
  reddit:      "bg-orange-950/60 text-orange-400 border-orange-800/50",
  hackernews:  "bg-amber-950/60  text-amber-400  border-amber-800/50",
  github:      "bg-purple-950/60 text-purple-400 border-purple-800/50",
  exa:         "bg-sky-950/60    text-sky-400    border-sky-800/50",
};

const SUGGESTED = [
  "What are devs saying about AI coding tools right now?",
  "What's the latest drama in crypto?",
  "Most hyped startups this month on HN",
  "What are people building with Rust?",
];

function timeAgo(published_at: string | null): string {
  if (!published_at) return "";
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

function SourceCard({ src }: { src: Source }) {
  const badge = SOURCE_BADGE[src.source] ?? "bg-[#21262d] text-[#8b949e] border-[#30363d]";
  const engagementEntries = Object.entries(src.engagement || {}).filter(([, v]) => v > 0);

  return (
    <a
      href={src.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-[#0d1117] border border-[#30363d] rounded-lg p-3 hover:border-[#58a6ff] transition-colors group"
    >
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

      <p className="text-xs text-[#c9d1d9] leading-relaxed line-clamp-2 group-hover:text-white transition-colors mb-1.5">
        {src.title}
      </p>

      {src.body && (
        <p className="text-[11px] text-[#484f58] leading-relaxed line-clamp-2 mb-1.5">
          {src.body}
        </p>
      )}

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

function AssistantBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className="space-y-4">
      {/* Answer text */}
      <div className="text-sm text-[#e6edf3] leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </div>

      {/* Sources — always visible */}
      {msg.sources && msg.sources.length > 0 && (
        <div>
          <p className="text-[11px] text-[#484f58] mb-2 flex items-center gap-2">
            <span className="font-medium text-[#8b949e]">
              {msg.sources.length} posts read
            </span>
            {msg.meta && (
              <>
                <span>·</span>
                <span>{msg.meta.search_duration_ms}ms</span>
                <span>·</span>
                <span>{msg.meta.items_retrieved} retrieved, {msg.meta.items_in_context} in context</span>
              </>
            )}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {msg.sources.map((src, i) => (
              <SourceCard key={i} src={src} />
            ))}
          </div>
        </div>
      )}

      {/* Grounding + model row */}
      {msg.eval && (
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
      )}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<Provider>("deepseek");
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stage]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [input]);

  function newChat() {
    setMessages([]);
    setInput("");
    setStage("idle");
    setError("");
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || (stage !== "idle" && stage !== "done")) return;

    const userMsg: ChatMessage = { id: `${Date.now()}`, role: "user", content: q };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setError("");

    // Simulate pipeline stages for UX feedback
    const stages: Stage[] = ["search", "analysis", "synthesis", "eval"];
    let si = 0;
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
          messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),
          provider,
        }),
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      clearInterval(interval);
      setStage("done");

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

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const isRunning = stage !== "idle" && stage !== "done";
  const stageIndex = AGENT_STAGES.findIndex((s) => s.key === stage);
  const userQueries = messages.filter((m) => m.role === "user");

  return (
    <div className="flex h-[calc(100vh-61px)]">
      {/* ── Sidebar ── */}
      <aside className="w-60 border-r border-[#30363d] flex flex-col bg-[#0d1117] flex-shrink-0">
        <div className="p-3">
          <button
            onClick={newChat}
            className="w-full flex items-center gap-2 bg-[#161b22] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white hover:bg-[#21262d] transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
              <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            New Chat
          </button>
        </div>

        {/* Provider toggle */}
        <div className="px-3 pb-3">
          <p className="text-[11px] text-[#484f58] mb-1.5 uppercase tracking-wider">Model</p>
          <div className="flex gap-1 bg-[#161b22] border border-[#30363d] rounded-lg p-1">
            {(["deepseek", "gemini"] as Provider[]).map((p) => (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className={`flex-1 text-[11px] py-1 rounded-md font-medium transition-colors ${
                  provider === p
                    ? "bg-[#58a6ff] text-black"
                    : "text-[#8b949e] hover:text-white"
                }`}
              >
                {p === "deepseek" ? "DeepSeek" : "Gemini"}
              </button>
            ))}
          </div>
        </div>

        {/* Session history */}
        {userQueries.length > 0 && (
          <div className="px-3 flex-1 overflow-y-auto min-h-0">
            <p className="text-[11px] text-[#484f58] mb-1.5 uppercase tracking-wider">This session</p>
            <div className="space-y-0.5">
              {userQueries.map((m) => (
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

        {/* Source legend */}
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

      {/* ── Main pane ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 && !isRunning ? (
            /* Empty state */
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-lg px-6">
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
            <div className="max-w-3xl mx-auto px-6 py-8 space-y-10">
              {messages.map((msg) =>
                msg.role === "user" ? (
                  /* User bubble */
                  <div key={msg.id} className="flex justify-end">
                    <div className="bg-[#58a6ff] text-black rounded-2xl rounded-tr-sm px-5 py-3 max-w-sm text-sm leading-relaxed font-medium">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  /* Assistant response */
                  <div key={msg.id}>
                    <AssistantBubble msg={msg} />
                  </div>
                )
              )}

              {/* Live pipeline status */}
              {isRunning && (
                <div className="space-y-2 pl-1">
                  {AGENT_STAGES.map((s, i) => {
                    const isActive = s.key === stage;
                    const isDone = stageIndex > i;
                    return (
                      <div key={s.key} className="flex items-center gap-3">
                        <div
                          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors ${
                            isDone ? "bg-[#3fb950]" : isActive ? "bg-[#58a6ff] animate-pulse" : "bg-[#30363d]"
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

              {error && (
                <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/40 rounded-lg p-3">
                  {error}
                </p>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="border-t border-[#30363d] p-4 bg-[#0d1117]">
          <div className="max-w-3xl mx-auto">
            <div className="flex gap-3 items-end bg-[#161b22] border border-[#30363d] rounded-xl px-4 py-3 focus-within:border-[#58a6ff] transition-colors">
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
                  <span className="flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:0ms]" />
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:150ms]" />
                    <span className="w-1 h-1 rounded-full bg-black animate-bounce [animation-delay:300ms]" />
                  </span>
                ) : (
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
