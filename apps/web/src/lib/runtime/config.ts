/**
 * Typed runtime configuration with validation.
 *
 * Reads NEXT_PUBLIC_* env vars (the only ones exposed to the browser by
 * Next.js) and surfaces any missing/empty keys explicitly. The diagnostics
 * banner consumes `getEnvIssues()` to render a visible configuration
 * error rather than silently failing.
 */

const DEFAULT_API_BASE = "http://127.0.0.1:8100";

export interface RuntimeConfig {
  apiBaseUrl: string;
  /** MapTiler API key. Empty string when not configured. */
  maptilerKey: string;
}

export interface EnvIssue {
  key: string;
  reason: "missing" | "placeholder";
  feature: string;
}

const PLACEHOLDER_VALUES = new Set([
  "",
  "your_api_key",
  "your_maptiler_api_key",
  "your_mapbox_token_here",
  "your_maptiler_key_here",
]);

// Template-literal style placeholders like `<your-key-here>` or
// `${SOMETHING}` show up when someone copy-pastes setup instructions
// verbatim without substituting the value. They look like real values
// to a naïve length check but produce broken upstream requests, so we
// detect + reject them here.
function looksLikeTemplate(value: string): boolean {
  if (!value) return false;
  if (value.startsWith("<") && value.endsWith(">")) return true;
  if (value.startsWith("${") && value.endsWith("}")) return true;
  if (value.toLowerCase().includes("your_")) return true;
  if (value.toLowerCase().includes("replace_me")) return true;
  return false;
}


// Webpack's DefinePlugin only rewrites LITERAL `process.env.NEXT_PUBLIC_*`
// expressions at build time. Dynamic `process.env[key]` access is NOT
// rewritten — it returns undefined on the client and produces a different
// value than the server saw, breaking hydration. Enumerate every public
// key we consume here as a literal access so both sides get the same value.
type PublicEnvKey = "NEXT_PUBLIC_API_URL" | "NEXT_PUBLIC_MAPTILER_API_KEY";

function readPublic(key: PublicEnvKey): string {
  switch (key) {
    case "NEXT_PUBLIC_API_URL":
      return (process.env.NEXT_PUBLIC_API_URL ?? "").trim();
    case "NEXT_PUBLIC_MAPTILER_API_KEY":
      return (process.env.NEXT_PUBLIC_MAPTILER_API_KEY ?? "").trim();
  }
}


function sanitizeKey(value: string): string {
  if (PLACEHOLDER_VALUES.has(value.toLowerCase())) return "";
  if (looksLikeTemplate(value)) return "";
  return value;
}


export function getRuntimeConfig(): RuntimeConfig {
  const apiBaseUrl =
    readPublic("NEXT_PUBLIC_API_URL") || DEFAULT_API_BASE;
  const maptilerKey = sanitizeKey(readPublic("NEXT_PUBLIC_MAPTILER_API_KEY"));
  return { apiBaseUrl, maptilerKey };
}


/**
 * List configuration problems the UI should surface. Empty = all good.
 *
 * Intentionally narrow: only flags keys we ACTUALLY consume in this build.
 * Adding a future key (e.g. NEXT_PUBLIC_AUTH_DOMAIN) means adding it here.
 */
export function getEnvIssues(): EnvIssue[] {
  const issues: EnvIssue[] = [];
  const rawMaptiler = readPublic("NEXT_PUBLIC_MAPTILER_API_KEY");
  if (!rawMaptiler) {
    issues.push({
      key: "NEXT_PUBLIC_MAPTILER_API_KEY",
      reason: "missing",
      feature: "Interactive map",
    });
  } else if (
    PLACEHOLDER_VALUES.has(rawMaptiler.toLowerCase()) ||
    looksLikeTemplate(rawMaptiler)
  ) {
    issues.push({
      key: "NEXT_PUBLIC_MAPTILER_API_KEY",
      reason: "placeholder",
      feature: "Interactive map",
    });
  }
  return issues;
}


export function isMapAvailable(): boolean {
  return getRuntimeConfig().maptilerKey.length > 0;
}
