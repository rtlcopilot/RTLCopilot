import { createClient } from "@supabase/supabase-js";

export const OFFLINE_MODE = import.meta.env.VITE_OFFLINE_MODE === "true";

export const supabase = OFFLINE_MODE
  ? null
  : createClient(
      import.meta.env.VITE_SUPABASE_URL,
      import.meta.env.VITE_SUPABASE_ANON_KEY,
    );

export const IS_DESKTOP =
  typeof window !== "undefined" && window.electronAPI !== undefined;

export const API_BASE = IS_DESKTOP
  ? "http://localhost:8080"
  : import.meta.env.VITE_API_URL || "http://localhost:8080";
