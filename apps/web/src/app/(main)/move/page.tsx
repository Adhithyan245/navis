// /move — same runtime-backed workspace as the home page. Relocation/
// move-in queries go through the same /v2/query path; dedicated workflows
// (settle_mode, move_mode) are future work.
export { default } from "../ask/page";
export const metadata = { title: "Move · Navis" };
