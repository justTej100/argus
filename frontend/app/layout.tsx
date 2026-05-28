/**
 * Root layout — wraps every page in the app.
 *
 * In Next.js App Router, layout.tsx at the top of the app/ directory is the
 * outermost shell. It renders once and stays mounted as users navigate between
 * pages — the <nav> here appears on /, /demo, and /docs without re-rendering.
 *
 * This file is a Server Component (no "use client") which means it runs on the
 * server at request time and sends HTML to the browser. That's fine here because
 * the nav has no interactive state — it's just links.
 */

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";

// next/font downloads Inter from Google Fonts at build time and self-hosts it.
// This avoids an extra network request to fonts.google.com at page load.
const inter = Inter({ subsets: ["latin"] });

// The <head> metadata — title and description show up in browser tabs,
// search results, and when the URL is shared on social media.
export const metadata: Metadata = {
  title: "Argus — Fresh Ideas from the Internet",
  description:
    "Ask anything. Argus reads Reddit, HN, and GitHub in real time and tells you what people are actually saying. Powered by a 4-agent RAG pipeline.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      {/*
        bg-[#0d1117]  — GitHub's dark background color (near-black)
        min-h-screen  — ensures the dark bg covers the full viewport even on short pages
      */}
      <body className={`${inter.className} bg-[#0d1117] text-[#e6edf3] min-h-screen`}>
        <nav className="border-b border-[#30363d] px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
          {/* Brand link — clicking "Argus" always takes you back to the chat */}
          <Link href="/" className="text-lg font-semibold tracking-tight text-white">
            Argus
          </Link>

          <div className="flex items-center gap-6 text-sm text-[#8b949e]">
            {/* Chat = homepage (/) — the main product experience */}
            <Link href="/" className="hover:text-white transition-colors">
              Chat
            </Link>
            {/* Demo = /demo — same pipeline but with a more explicit step-by-step UI */}
            <Link href="/demo" className="hover:text-white transition-colors">
              Demo
            </Link>
            {/* Docs = /docs — API reference for developers using the REST endpoints */}
            <Link href="/docs" className="hover:text-white transition-colors">
              Docs
            </Link>
            <a
              href="https://github.com/yourusername/argus"
              target="_blank"
              rel="noopener noreferrer"  // security: prevents the new tab from accessing window.opener
              className="hover:text-white transition-colors"
            >
              GitHub
            </a>
            <Link
              href="/docs#get-key"
              className="bg-[#238636] text-white px-3 py-1.5 rounded-md hover:bg-[#2ea043] transition-colors"
            >
              Get API Key
            </Link>
          </div>
        </nav>

        {/* children = the page component for whatever route is active */}
        <main>{children}</main>
      </body>
    </html>
  );
}
