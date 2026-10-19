"use client";
/**
 * EnvDiagnosticsBanner — surfaces missing or placeholder env keys.
 *
 * Reads getEnvIssues() and renders a visible warning when any required
 * NEXT_PUBLIC_* key is missing or still set to a known placeholder. This
 * is the explicit "fail visibly" path the directive requires for map keys
 * (and any future key we add).
 *
 * Renders nothing when configuration is healthy.
 */
import { AlertTriangle } from "lucide-react";

import { getEnvIssues } from "@/lib/runtime/config";

export function EnvDiagnosticsBanner() {
  const issues = getEnvIssues();
  if (issues.length === 0) return null;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"
    >
      <AlertTriangle className="size-4 mt-0.5 shrink-0" aria-hidden />
      <div className="space-y-1">
        <p className="font-medium">Some features are unavailable</p>
        <ul className="text-xs space-y-0.5">
          {issues.map((issue) => (
            <li key={issue.key}>
              <span className="font-mono">{issue.key}</span>
              {" — "}
              {issue.feature} is disabled (
              {issue.reason === "missing" ? "not set" : "placeholder value"}
              ). Add it to <span className="font-mono">apps/web/.env.local</span>
              {" "}and restart the dev server.
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
