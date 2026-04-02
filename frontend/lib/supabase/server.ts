import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let cachedClient: SupabaseClient | null | undefined;

type SupabaseConfig = {
  url: string;
  key: string;
};

function readEnv(name: string): string | null {
  const value = process.env[name];
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed === '""' || trimmed === "''") {
    return null;
  }
  return trimmed;
}

function getSupabaseConfig(): SupabaseConfig | null {
  const url = readEnv("NEXT_PUBLIC_SUPABASE_URL") ?? readEnv("SUPABASE_URL");
  const key =
    readEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY") ??
    readEnv("SUPABASE_SERVICE_ROLE_KEY") ??
    readEnv("SUPABASE_SECRET_KEY");
  if (!url || !key) {
    return null;
  }
  return { url, key };
}

export function isSupabaseConfigured(): boolean {
  return getSupabaseConfig() !== null;
}

export function getSupabaseBaseUrl(): string | null {
  return readEnv("NEXT_PUBLIC_SUPABASE_URL") ?? readEnv("SUPABASE_URL");
}

export function getSupabaseReadClient(): SupabaseClient | null {
  const config = getSupabaseConfig();
  if (!config) {
    return null;
  }
  if (cachedClient !== undefined) {
    return cachedClient;
  }
  cachedClient = createClient(
    config.url,
    config.key,
    {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    },
  );
  return cachedClient;
}
