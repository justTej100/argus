"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "demo-key-argus";

const AGENT_STAGES = [
  { key: "search", label: "SearchAgent", desc: "Scanning Reddit, HN, GitHub..." },
  { key: "analysis", label: "AnalysisAgent", desc: "Embedding + semantic ranking..." },
  { key: "synthesis", label: "SynthesisAgent", desc: "Generating brief..." },
  { key: "eval", label: "EvalAgent", desc: "Grounding check..." },
];

type Stage = "idle" | "search" | "analysis" | "synthesis" | "eval" | "done";

export default function DemoPage() {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"topic" | "person">("topic");
  const [provider, setProvider] = useState<"deepseek" | "gemini">("deepseek");
  const [apiKey, setApiKey] = useState(DEMO_KEY);
  const [stage, setStage] = useState<Stage>("idle");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setError("");
    setResult(null);

    // Simulate agent stages for UX
    const stages: Stage[] = ["search", "analysis", "synthesis", "eval"];
    let i = 0;
    const interval = setInterval(() => {
      if (i < stages.length) setStage(stages[i++]);
      else clearInterval(interval);
    }, 1800);

    try {
      const res = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
        },
        body: JSON.stringify({ query, type, provider }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      clearInterval(interval);
      setStage("done");
      setResult(data);
    } catch (err: any) {
      clearInterval(interval);
      setStage("idle");
      setError(err.message || "Something went wrong");
    }
  }

  const stageIndex = AGENT_STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <h1 className="text-3xl font-bold text-white mb-2">Demo</h1>
      <p className="text-[#8b949e] mb-8">
        Run the full 4-agent pipeline. Uses the demo key by default (10 req/day).
      </p>

      {/* Search form */}
      <form onSubmit={handleSearch} className="bg-[#161b22] border border-[#30363d] rounded-xl p-6 mb-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search query..."
            className="md:col-span-2 bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-2.5 text-white placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff]"
          />
          <select
            value={type}
            onChange={(e) => setType(e.target.value as any)}
            className="bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-2.5 text-white focus:outline-none"
          >
            <option value="topic">Topic</option>
            <option value="person">Person</option>
          </select>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as any)}
            className="bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-2.5 text-white focus:outline-none"
          >
            <option value="deepseek">DeepSeek</option>
            <option value="gemini">Gemini</option>
          </select>
        </div>

        <div className="flex gap-4 items-center">
          <input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API key"
            className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-2.5 text-white placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] font-mono text-sm"
          />
          <button
            type="submit"
            disabled={stage !== "idle" && stage !== "done"}
            className="bg-[#238636] text-white px-6 py-2.5 rounded-lg font-medium hover:bg-[#2ea043] disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {stage !== "idle" && stage !== "done" ? "Running..." : "Run Pipeline"}
          </button>
        </div>

        {error && (
          <p className="mt-4 text-sm text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg p-3">
            {error}
          </p>
        )}
      </form>

      {/* Agent status */}
      {stage !== "idle" && (
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6 mb-8">
          <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-4">
            Pipeline
          </h2>
          <div className="space-y-3">
            {AGENT_STAGES.map((s, i) => {
              const isActive = s.key === stage;
              const isDone = stage === "done" || stageIndex > i;
              return (
                <div key={s.key} className="flex items-center gap-4">
                  <div
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      isDone
                        ? "bg-[#3fb950]"
                        : isActive
                        ? "bg-[#58a6ff] animate-pulse"
                        : "bg-[#30363d]"
                    }`}
                  />
                  <span
                    className={`font-mono text-sm ${
                      isDone ? "text-[#3fb950]" : isActive ? "text-white" : "text-[#484f58]"
                    }`}
                  >
                    {s.label}
                  </span>
                  <span className="text-sm text-[#484f58]">
                    {isActive ? s.desc : isDone ? "✓" : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Brief */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-white">Brief</h2>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[#484f58] font-mono">
                    {result.meta.model}
                  </span>
                  <span
                    className={`text-xs font-medium px-2 py-1 rounded-full ${
                      result.eval.score >= 0.8
                        ? "bg-green-900/40 text-green-400 border border-green-900"
                        : result.eval.score >= 0.6
                        ? "bg-yellow-900/40 text-yellow-400 border border-yellow-900"
                        : "bg-red-900/40 text-red-400 border border-red-900"
                    }`}
                  >
                    Grounding {(result.eval.score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <p className="text-sm text-[#c9d1d9] leading-relaxed whitespace-pre-wrap">
                {result.brief}
              </p>
            </div>

            {/* Eval detail */}
            <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6">
              <h2 className="font-semibold text-white mb-4">Eval — grounding check</h2>
              <div className="grid grid-cols-3 gap-4 mb-4 text-center">
                <div>
                  <div className="text-2xl font-bold text-white">{result.eval.claims_checked}</div>
                  <div className="text-xs text-[#484f58]">claims checked</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-[#3fb950]">{result.eval.claims_grounded}</div>
                  <div className="text-xs text-[#484f58]">grounded</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-red-400">
                    {result.eval.claims_checked - result.eval.claims_grounded}
                  </div>
                  <div className="text-xs text-[#484f58]">ungrounded</div>
                </div>
              </div>
              {result.eval.ungrounded_claims.length > 0 && (
                <div>
                  <p className="text-xs text-[#8b949e] mb-2">Ungrounded claims:</p>
                  <ul className="space-y-1">
                    {result.eval.ungrounded_claims.map((c: string, i: number) => (
                      <li key={i} className="text-xs text-red-400 bg-red-900/10 rounded px-3 py-1">
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Sources sidebar */}
          <div className="space-y-4">
            <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6">
              <h2 className="font-semibold text-white mb-1">Sources</h2>
              <p className="text-xs text-[#484f58] mb-4">
                {result.meta.items_retrieved} retrieved · {result.meta.items_in_context} in context
              </p>
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                {result.sources.map((s: any, i: number) => (
                  <a
                    key={i}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-[#0d1117] border border-[#30363d] rounded-lg p-3 hover:border-[#58a6ff] transition-colors group"
                  >
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="text-xs bg-[#21262d] text-[#8b949e] px-1.5 py-0.5 rounded">
                        {s.source}
                      </span>
                      {/* container = subreddit, GitHub org, "HackerNews", etc. */}
                      {s.container && (
                        <span className="text-xs text-[#484f58]">{s.container}</span>
                      )}
                      {Object.entries(s.engagement || {}).filter(([, v]) => Number(v) > 0).map(([k, v]) => (
                        <span key={k} className="text-xs text-[#484f58]">
                          {Number(v).toLocaleString()} {k}
                        </span>
                      ))}
                    </div>
                    <p className="text-xs text-[#c9d1d9] line-clamp-2 group-hover:text-white transition-colors mb-1">
                      {s.title}
                    </p>
                    {/* body excerpt — the actual post text Argus read */}
                    {s.body && (
                      <p className="text-[11px] text-[#484f58] line-clamp-2 leading-relaxed">
                        {s.body}
                      </p>
                    )}
                  </a>
                ))}
              </div>
            </div>

            {/* Meta */}
            <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6">
              <h2 className="font-semibold text-white mb-3">Meta</h2>
              <div className="space-y-2 text-xs font-mono">
                {[
                  ["duration", `${result.meta.search_duration_ms}ms`],
                  ["sources", result.meta.sources_hit?.join(", ")],
                  ["tokens (est)", result.meta.token_estimate],
                  ["grounding", result.eval.score],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex justify-between">
                    <span className="text-[#484f58]">{k}</span>
                    <span className="text-[#8b949e]">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}