import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";

import { NativeBridge } from "@/components/NativeBridge";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Navis — your local companion anywhere", template: "%s · Navis" },
  description:
    "Navis helps you land anywhere: maps, events, transit, health and emergency numbers, essentials and local know-how for any city or island.",
  applicationName: "Navis",
  appleWebApp: { capable: true, title: "Navis", statusBarStyle: "default" },
  formatDetection: { telephone: false },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f8fc" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0c14" },
  ],
  width: "device-width",
  initialScale: 1,
  // Draw under the notch / home indicator; layouts pad with safe-area insets.
  viewportFit: "cover",
};

// Applies the persisted (or OS-preferred) theme before first paint so dark
// mode survives reloads without a light flash. Kept in sync with
// DarkModeToggle's storage key.
const THEME_INIT = `(function(){try{var t=localStorage.getItem("navis_theme");var d=t?t==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;if(d)document.documentElement.classList.add("dark")}catch(e){}})();`;

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Per-request CSP nonce from src/proxy.ts.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Browsers hide nonce values from the DOM, so the client sees "". */}
        <script nonce={nonce} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="app-backdrop min-h-full flex flex-col font-sans">
        {children}
        <ServiceWorkerRegistrar />
        <NativeBridge />
      </body>
    </html>
  );
}
