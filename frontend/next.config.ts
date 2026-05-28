import type { NextConfig } from "next";
import path from "path";

// Load the single root .env (argus/.env) before Next.js processes env vars.
//
// Why do this here instead of relying on Next.js's built-in .env loading?
// Next.js looks for .env files in the app directory (frontend/) by default.
// Since we want one .env at the project root, we load it manually.
//
// `override: false` means if a variable is already set in the shell environment,
// the .env file value won't overwrite it — shell env vars take priority.
require("dotenv").config({
  path: path.resolve(process.cwd(), "../.env"),
  override: false,
});

const nextConfig: NextConfig = {
  // Inject these into the Next.js build so they're available on the client side.
  // NEXT_PUBLIC_* vars are baked in at build time — they're not secret.
  // The defaults here mean the app works out of the box for local development
  // even if the .env file doesn't set them.
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_DEMO_KEY:
      process.env.NEXT_PUBLIC_DEMO_KEY ?? "demo-key-argus",
  },
};

export default nextConfig;
