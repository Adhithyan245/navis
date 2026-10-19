/**
 * Renders the Navis app icon (a compass needle on an indigo→violet
 * gradient) to every size the web app, PWA install and the native apps
 * need. Run: node scripts/generate-icons.mjs  (uses sharp, bundled with Next)
 *
 * Outputs
 *   public/icons/icon-192.png, icon-512.png       PWA "any"
 *   public/icons/maskable-512.png                 PWA maskable (safe zone)
 *   public/icons/apple-touch-icon.png             iOS home screen (180, opaque)
 *   ../mobile/assets/icon-only.png (1024)         @capacitor/assets sources
 *   ../mobile/assets/icon-foreground.png, icon-background.png
 *   ../mobile/assets/splash.png, splash-dark.png  (2732)
 */
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const mobileAssets = join(web, "..", "mobile", "assets");

const GRADIENT = `<linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#4f46e5"/><stop offset="1" stop-color="#a855f7"/></linearGradient>`;

// Compass needle in a 100×100 box, centred at (50,50).
function needle(scale = 1) {
  const t = `translate(50 50) scale(${scale}) translate(-50 -50)`;
  return `<g transform="${t}">
    <circle cx="50" cy="50" r="34" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="3"/>
    <path d="M50 18 L62 50 L50 46 L38 50 Z" fill="#ffffff"/>
    <path d="M50 82 L38 50 L50 54 L62 50 Z" fill="#ffffff" fill-opacity="0.55"/>
    <circle cx="50" cy="50" r="4.5" fill="#4f46e5" stroke="#ffffff" stroke-width="2"/>
  </g>`;
}

function iconSvg({ rounded = true, scale = 1, background = true } = {}) {
  const bg = background
    ? `<rect width="100" height="100" ${rounded ? 'rx="22"' : ""} fill="url(#g)"/>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs>${GRADIENT}</defs>${bg}${needle(scale)}</svg>`;
}

function splashSvg(dark) {
  const bg = dark ? "#0b0c14" : "#f8f8fc";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><defs>${GRADIENT}</defs>
    <rect width="1000" height="1000" fill="${bg}"/>
    <g transform="translate(400 400) scale(2)"><rect width="100" height="100" rx="22" fill="url(#g)"/>${needle()}</g></svg>`;
}

async function render(svg, size, out, { flatten } = {}) {
  mkdirSync(dirname(out), { recursive: true });
  let img = sharp(Buffer.from(svg), { density: 600 }).resize(size, size);
  if (flatten) img = img.flatten({ background: flatten });
  await img.png().toFile(out);
  console.log("wrote", out);
}

const pub = join(web, "public", "icons");
await render(iconSvg(), 192, join(pub, "icon-192.png"));
await render(iconSvg(), 512, join(pub, "icon-512.png"));
await render(iconSvg({ rounded: false, scale: 0.72 }), 512, join(pub, "maskable-512.png"));
await render(iconSvg({ rounded: false, scale: 0.86 }), 180, join(pub, "apple-touch-icon.png"), { flatten: "#4f46e5" });

await render(iconSvg({ rounded: false, scale: 0.86 }), 1024, join(mobileAssets, "icon-only.png"), { flatten: "#4f46e5" });
await render(iconSvg({ background: false, scale: 0.62 }), 1024, join(mobileAssets, "icon-foreground.png"));
await render(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs>${GRADIENT}</defs><rect width="100" height="100" fill="url(#g)"/></svg>`,
  1024, join(mobileAssets, "icon-background.png"));
await render(splashSvg(false), 2732, join(mobileAssets, "splash.png"));
await render(splashSvg(true), 2732, join(mobileAssets, "splash-dark.png"));
