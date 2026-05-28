import type { NextConfig } from "next";
import path from "path";

// Load the single root .env (argus/.env) before Next.js processes env vars.
// `override: false` means shell env vars still take priority.
require("dotenv").config({
  path: path.resolve(process.cwd(), "../.env"),
  override: false,
});

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_DEMO_KEY:
      process.env.NEXT_PUBLIC_DEMO_KEY ?? "demo-key-argus",
  },
};

export default nextConfig;
