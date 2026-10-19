// /voice — same runtime-backed workspace as the home page. The voice mic
// button lives inside QueryConsole, so this URL surfaces the same UI as /;
// the dedicated /voice URL is preserved for muscle-memory + bookmarks.
export { default } from "../ask/page";
export const metadata = { title: "Voice · Navis" };
