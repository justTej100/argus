import Link from "next/link";

const CODE_CHAT_CURL = `curl -X POST https://api.argus.dev/chat \\
  -H "x-api-key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "messages": [
      {"role": "user", "content": "What are devs saying about Rust right now?"}
    ],
    "provider": "deepseek"
  }'`;

const CODE_CHAT_FOLLOWUP = `# Multi-turn — send the full history on every request
curl -X POST https://api.argus.dev/chat \\
  -H "x-api-key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "messages": [
      {"role": "user",      "content": "What are devs saying about Rust?"},
      {"role": "assistant", "content": "On HN, the top thread this week..."},
      {"role": "user",      "content": "Which post had the most upvotes?"}
    ],
    "provider": "deepseek"
  }'`;

const CODE_CURL = `curl -X POST https://api.argus.dev/search \\
  -H "x-api-key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "bitcoin ETF approval",
    "type": "topic",
    "provider": "deepseek"
  }'`;

const CODE_PYTHON = `import httpx

response = httpx.post(
    "https://api.argus.dev/search",
    headers={"x-api-key": "YOUR_API_KEY"},
    json={
        "query": "Vitalik Buterin",
        "type": "person",
        "provider": "deepseek",
        "sources": ["reddit", "hackernews", "github"],
    },
)

data = response.json()
print(data["brief"])
print(f"Grounding score: {data['eval']['score']}")`;

const CODE_JS = `const response = await fetch("https://api.argus.dev/search", {
  method: "POST",
  headers: {
    "x-api-key": "YOUR_API_KEY",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    query: "AI agent frameworks 2025",
    type: "topic",
    provider: "gemini",
  }),
});

const { brief, eval: evalResult, sources } = await response.json();
console.log(brief);
console.log(\`Grounding: \${evalResult.score}\`);`;

const CODE_RESPONSE = `{
  "query": "bitcoin ETF approval",
  "type": "topic",
  "brief": "Bitcoin ETF approval has dominated discussion across...",
  "eval": {
    "passed": true,
    "score": 0.91,
    "claims_checked": 14,
    "claims_grounded": 13,
    "ungrounded_claims": [],
    "explanation": "13 of 14 claims were traced to the retrieved sources."
  },
  "sources": [
    {
      "source": "reddit",
      "title": "SEC approves spot Bitcoin ETFs...",
      "url": "https://reddit.com/r/Bitcoin/...",
      "body": "The SEC has approved 11 spot Bitcoin ETF applications...",
      "container": "r/Bitcoin",
      "author": "u/cryptonews",
      "published_at": "2024-01-10T14:32:00",
      "engagement": { "upvotes": 18420, "comments": 1204 }
    }
  ],
  "meta": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "sources_hit": ["reddit", "hackernews", "github"],
    "items_retrieved": 47,
    "items_in_context": 8,
    "grounding_score": 0.91,
    "search_duration_ms": 1240
  }
}`;

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  return (
    <div className="bg-[#0d1117] border border-[#30363d] rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#30363d]">
        <span className="text-xs text-[#484f58] font-mono">{lang}</span>
      </div>
      <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-x-auto leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export default function DocsPage() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h1 className="text-3xl font-bold text-white mb-2">API Reference</h1>
      <p className="text-[#8b949e] mb-12">
        Base URL:{" "}
        <code className="text-[#58a6ff] bg-[#161b22] px-2 py-0.5 rounded font-mono text-sm">
          https://api.argus.dev
        </code>
      </p>

      {/* Get a key */}
      <section id="get-key" className="mb-16">
        <h2 className="text-xl font-semibold text-white mb-4">Get an API key</h2>
        <p className="text-[#8b949e] mb-4">
          Use the demo key to test. Generate your own key for higher limits.
        </p>
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-6 mb-4">
          <p className="text-sm text-[#8b949e] mb-2">Demo key (10 requests/day)</p>
          <code className="text-[#58a6ff] font-mono">demo-key-argus</code>
        </div>
        <CodeBlock
          lang="bash"
          code={`curl -X POST "https://api.argus.dev/keys/generate?plan=free"`}
        />
      </section>

      {/* POST /chat — primary endpoint used by the homepage */}
      <section className="mb-16">
        <div className="flex items-center gap-3 mb-4">
          <span className="bg-[#1f6feb] text-white text-xs font-bold px-2 py-1 rounded">POST</span>
          <code className="text-white font-mono text-lg">/chat</code>
          <span className="text-xs bg-[#21262d] text-[#58a6ff] px-2 py-0.5 rounded border border-[#30363d]">
            primary
          </span>
        </div>
        <p className="text-[#8b949e] mb-6">
          Multi-turn chat endpoint. Send the full conversation history on every request — the last
          user message drives the search, and earlier turns are threaded into the LLM prompt so
          follow-up questions are answered in context.
        </p>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Request body
        </h3>
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#30363d]">
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Field</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Type</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Required</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d]">
              {[
                ["messages", 'Array<{role, content}>', "✅", "Full conversation history. Last user message is the query."],
                ["provider", '"deepseek" | "gemini"', "—", 'Default: "deepseek"'],
                ["sources", "string[]", "—", "Default: reddit, hackernews, github"],
              ].map(([field, type, req, desc]) => (
                <tr key={String(field)}>
                  <td className="px-4 py-3 font-mono text-[#58a6ff]">{field}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#8b949e]">{type}</td>
                  <td className="px-4 py-3 text-center">{req}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Examples
        </h3>
        <div className="space-y-4 mb-6">
          <CodeBlock lang="bash — first turn" code={CODE_CHAT_CURL} />
          <CodeBlock lang="bash — follow-up turn" code={CODE_CHAT_FOLLOWUP} />
        </div>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Response
        </h3>
        <p className="text-[#8b949e] text-sm mb-4">
          Same shape as <code className="text-[#58a6ff] font-mono">/search</code> — see the response
          example below.
        </p>
      </section>

      {/* POST /search */}
      <section className="mb-16">
        <div className="flex items-center gap-3 mb-4">
          <span className="bg-[#1f6feb] text-white text-xs font-bold px-2 py-1 rounded">POST</span>
          <code className="text-white font-mono text-lg">/search</code>
        </div>
        <p className="text-[#8b949e] mb-6">
          Runs the full 4-agent pipeline — SearchAgent, AnalysisAgent, SynthesisAgent, EvalAgent —
          and returns a grounded brief with sources.
        </p>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Request body
        </h3>
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#30363d]">
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Field</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Type</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Required</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d]">
              {[
                ["query", "string", "✅", "The topic or person to research"],
                ["type", '"topic" | "person"', "—", 'Default: "topic"'],
                ["provider", '"deepseek" | "gemini"', "—", 'Default: "deepseek"'],
                ["sources", "string[]", "—", "Default: reddit, hackernews, github"],
              ].map(([field, type, req, desc]) => (
                <tr key={String(field)}>
                  <td className="px-4 py-3 font-mono text-[#58a6ff]">{field}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#8b949e]">{type}</td>
                  <td className="px-4 py-3 text-center">{req}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Examples
        </h3>
        <div className="space-y-4 mb-6">
          <CodeBlock lang="bash" code={CODE_CURL} />
          <CodeBlock lang="python" code={CODE_PYTHON} />
          <CodeBlock lang="javascript" code={CODE_JS} />
        </div>

        <h3 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
          Response
        </h3>
        <CodeBlock lang="json" code={CODE_RESPONSE} />
      </section>

      {/* Sources */}
      <section className="mb-16">
        <h2 className="text-xl font-semibold text-white mb-4">Sources</h2>
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#30363d]">
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Source</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Key needed</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">What you get</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d]">
              {[
                ["reddit", "None — free", "Posts, upvotes, comments"],
                ["hackernews", "None — free", "Stories, points, discussions"],
                ["github", "None (token = higher limits)", "Repos, stars, activity"],
                ["exa", "EXA_API_KEY (1k free/mo)", "Semantic web search"],
                ["tiktok", "SCRAPECREATORS_API_KEY", "Posts, views, engagement"],
                ["instagram", "SCRAPECREATORS_API_KEY", "Posts, likes, engagement"],
              ].map(([source, key, desc]) => (
                <tr key={String(source)}>
                  <td className="px-4 py-3 font-mono text-[#58a6ff]">{source}</td>
                  <td className="px-4 py-3 text-[#8b949e] text-xs">{key}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Rate limits */}
      <section className="mb-16">
        <h2 className="text-xl font-semibold text-white mb-4">Rate limits</h2>
        <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#30363d]">
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Plan</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Requests/day</th>
                <th className="text-left px-4 py-3 text-[#8b949e] font-medium">Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d]">
              {[
                ["demo", "10", "Free"],
                ["free", "10", "Free"],
                ["pro", "1,000", "Coming soon"],
              ].map(([plan, reqs, price]) => (
                <tr key={String(plan)}>
                  <td className="px-4 py-3 font-mono text-white">{plan}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{reqs}</td>
                  <td className="px-4 py-3 text-[#8b949e]">{price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="border-t border-[#30363d] pt-8 text-center">
        <Link href="/demo" className="text-[#58a6ff] hover:underline text-sm">
          Try it in the demo →
        </Link>
      </div>
    </div>
  );
}