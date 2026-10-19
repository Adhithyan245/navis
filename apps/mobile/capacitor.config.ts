/**
 * Navis native shell. The app loads the hosted Navis web app (it needs its
 * server: sign-in, sessions, API proxying), so set NAVIS_APP_URL to your
 * production HTTPS origin before `npx cap sync`.
 *
 *   NAVIS_APP_URL=https://app.navis.example npx cap sync
 *
 * appId must be a reverse-domain id you control; it can't change after the
 * first store release.
 */
import type { CapacitorConfig } from "@capacitor/cli";

const appUrl = process.env.NAVIS_APP_URL || "https://app.navis.example";
const host = new URL(appUrl).host;

const config: CapacitorConfig = {
  appId: process.env.NAVIS_APP_ID || "app.navis.mobile",
  appName: "Navis",
  // Bundled fallback page (shown only if the server can't be reached at launch).
  webDir: "www",
  server: {
    url: appUrl,
    // Only our own origin loads inside the app; everything else (OAuth, maps
    // hand-offs, event sites) opens in the system browser.
    allowNavigation: [host],
    // Only for local Wi-Fi testing builds (http://); production must be https.
    cleartext: appUrl.startsWith("http://"),
    errorPath: "offline.html",
  },
  ios: {
    contentInset: "never",
    limitsNavigationsToAppBoundDomains: true,
    scheme: "Navis",
  },
  android: {
    allowMixedContent: false,
    webContentsDebuggingEnabled: false,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      launchAutoHide: true,
      backgroundColor: "#0b0c14",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    PushNotifications: {
      // Show alerts even while the app is open.
      presentationOptions: ["badge", "sound", "alert"],
    },
    StatusBar: {
      overlaysWebView: true,
      style: "DEFAULT",
    },
  },
};

export default config;
