import { defineConfig } from "astro/config";

// GitHub Pages de projeto: https://<usuario>.github.io/monitor-congresso/
// SITE_URL e BASE_PATH podem ser trocados por variável de ambiente (ex.: domínio próprio no futuro).
export default defineConfig({
  site: process.env.SITE_URL ?? "https://davigheleno.github.io",
  base: process.env.BASE_PATH ?? "/monitor-congresso",
  trailingSlash: "always",
  build: { format: "directory" },
});
