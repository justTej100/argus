import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Argus — Fresh Ideas from the Internet",
  description:
    "Ask anything. Argus reads Reddit, HN, and GitHub in real time and tells you what people are actually saying. Powered by a 4-agent RAG pipeline.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-[#0d1117] text-[#e6edf3] min-h-screen`}>
        <nav className="border-b border-[#30363d] px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
          <Link href="/" className="text-lg font-semibold tracking-tight text-white">
            Argus
          </Link>
          <div className="flex items-center gap-6 text-sm text-[#8b949e]">
            <Link href="/" className="hover:text-white transition-colors">
              Chat
            </Link>
            <Link href="/demo" className="hover:text-white transition-colors">
              Demo
            </Link>
            <Link href="/docs" className="hover:text-white transition-colors">
              Docs
            </Link>
            <a
              href="https://github.com/yourusername/argus"
              target="_blank"
              rel="noopener noreferrer"
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
        <main>{children}</main>
      </body>
    </html>
  );
}