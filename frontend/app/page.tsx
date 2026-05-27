"use client";

import { useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY || "demo-key-argus";

const SOURCES = ["reddit", "hackernews", "github"];

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"topic" | "person">("topic");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": DEMO_KEY,
        },
        body: JSON.stringify({ query, type, provider: "deepseek" }),
      });
      if (!res.ok) throw new Error(await res.text());
      setResult(await res.json());
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6">
      {/* Hero */}
      <div className="pt-24 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-[#161b22] border border-[#30363d] rounded-full px-4 py-1.5 text-sm text-[#8b949e] mb-8">
          <span className="w-2 h-2 rounded-full bg-[#3fb950] animate-pulse" />
          4-agent RAG pipeline · DeepSeek + Gemini · pgvector
        </div>

        <h1 className="text-5xl font-bold tracking-tight text-white mb-6 leading-tight">
          Research anything.
          <br />
          <span className="text-[#58a6ff]">One API call.</span>
        </h1>

        <p className="text-xl text-[#8b949e] max-w-2xl mx-auto mb-12">
          Argus fans out to Reddit, HackerNews, GitHub, and the web simultaneously —
          embeds results for semantic ranking, synthesizes with AI, and grounding-checks
          every claim before returning it to you.
        </p>

        {/* Live demo widget */}
        <form
          onSubmit={handleSearch}
          className="bg-[#161b22] border border-[#30363d] rounded-xl p-6 text-left max-w-2xl mx-auto"
        >
          <div className="flex gap-2 mb-4">
            {(["topic", "person"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setType(t)}
                className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                  type === t
                    ? "bg-[#58a6ff] text-black"
                    : "text-[#8b949e] hover:text-white"
                }`}
              >
                {t === "topic" ? "Topic" : "Person"}
              </button>
            ))}
          </div>

          <div className="flex gap-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={type === "topic" ? "bitcoin ETF approval..." : "Vitalik Buterin..."}
              className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-3 text-white placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] transition-colors"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="bg-[#238636] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#2ea043] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="flex gap-2 mt-3 text-xs text-[#484f58]">
            {SOURCES.map((s) => (
              <span key={s} className="bg-[#0d1117] border border-[#30363d] rounded px-2 py-1">
                {s}
              </span>
            ))}
            <span className="border border-[#30363d] rounded px-2 py-1">+ more</span>
          </div>

          {error && (
            <p className="mt-4 text-sm text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg p-3">
              {error}
            </p>
          )}

          {loading && (
            <div className="mt-6 space-y-2">
              {["SearchAgent — scanning sources...", "AnalysisAgent — embedding + ranking...", "SynthesisAgent — generating brief..."].map((msg) => (
                <div key={msg} className="flex items-center gap-3 text-sm text-[#8b949e]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#58a6ff] animate-pulse" />
                  {msg}
                </div>
              ))}
            </div>
          )}

          {result && (
            <div className="mt-6 space-y-4">
              {/* Grounding badge */}
              <div className="flex items-center gap-3">
                <span
                  className={`text-xs font-medium px-2 py-1 rounded-full ${
                    result.eval.score >= 0.8
                      ? "bg-green-900/40 text-green-400 border border-green-900"
                      : result.eval.score >= 0.6
                      ? "bg-yellow-900/40 text-yellow-400 border border-yellow-900"
                      : "bg-red-900/40 text-red-400 border border-red-900"
                  }`}
                >
                  Grounding: {(result.eval.score * 100).toFixed(0)}%
                </span>
                <span className="text-xs text-[#484f58]">
                  {result.meta.items_retrieved} sources · {result.meta.search_duration_ms}ms
                </span>
              </div>

              {/* Brief */}
              <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-4 text-sm text-[#c9d1d9] leading-relaxed whitespace-pre-wrap">
                {result.brief}
              </div>

              <Link
                href="/demo"
                className="inline-block text-sm text-[#58a6ff] hover:underline"
              >
                Open full demo →
              </Link>
            </div>
          )}
        </form>

        <p className="mt-4 text-xs text-[#484f58]">
          Demo key rate limited to 10 requests/day.{" "}
          <Link href="/docs#get-key" className="text-[#58a6ff] hover:underline">
            Get your own key →
          </Link>
        </p>
      </div>

      {/* Features */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 pb-24">
        {[
          {
            title: "Agentic pipeline",
            desc: "4 named agents — Search, Analysis, Synthesis, Eval — each with a single job, composed into a full research workflow.",
          },
          {
            title: "RAG retrieval",
            desc: "Results are embedded and ranked by cosine similarity before the LLM sees them. No hallucination from memory.",
          },
          {
            title: "Grounding evals",
            desc: "Every brief gets a second-pass LLM grounding check. Unverified claims are flagged before they reach you.",
          },
          {
            title: "Switchable AI",
            desc: "DeepSeek or Gemini — both via OpenAI-compatible endpoints. Switch with a single parameter.",
          },
        ].map((f) => (
          <div
            key={f.title}
            className="bg-[#161b22] border border-[#30363d] rounded-xl p-5"
          >
            <h3 className="font-semibold text-white mb-2">{f.title}</h3>
            <p className="text-sm text-[#8b949e] leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}