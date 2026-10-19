// /services — same runtime-backed workspace as the home page. Service-
// lookup queries (clinics, banks, etc.) get routed through the same
// /v2/query path; a dedicated services_mode workflow is future work.
export { default } from "../ask/page";
export const metadata = { title: "Services · Navis" };
