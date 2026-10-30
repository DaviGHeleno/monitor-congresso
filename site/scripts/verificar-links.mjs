// Confere se todo link interno (href/src começando pela base do site) aponta para um arquivo gerado em dist/.
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(process.argv[2] ?? "dist");
const BASE = (process.env.BASE_PATH ?? "/monitor-congresso").replace(/\/$/, "");

function* html(pasta) {
  for (const e of fs.readdirSync(pasta, { withFileTypes: true })) {
    const p = path.join(pasta, e.name);
    if (e.isDirectory()) yield* html(p);
    else if (e.name.endsWith(".html")) yield p;
  }
}

const quebrados = new Map();
let paginas = 0, links = 0;
for (const arquivo of html(DIST)) {
  paginas++;
  const texto = fs.readFileSync(arquivo, "utf-8");
  for (const [, alvo] of texto.matchAll(/(?:href|src)="([^"#?]+)/g)) {
    if (!alvo.startsWith(`${BASE}/`)) continue;
    links++;
    const rel = decodeURIComponent(alvo.slice(BASE.length));
    const destino = path.join(DIST, rel);
    const existe = rel.endsWith("/") ? fs.existsSync(path.join(destino, "index.html")) : fs.existsSync(destino);
    if (!existe) quebrados.set(alvo, path.relative(DIST, arquivo));
  }
}
console.log(`${paginas} páginas, ${links} links internos verificados`);
if (quebrados.size) {
  console.error(`${quebrados.size} links quebrados:`);
  for (const [alvo, origem] of [...quebrados].slice(0, 30)) console.error(`  ${alvo}  (em ${origem})`);
  process.exit(1);
}
console.log("Nenhum link quebrado.");
