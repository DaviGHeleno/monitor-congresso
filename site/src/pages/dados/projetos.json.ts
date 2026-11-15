// Todos os projetos, num formato compacto, baixado pela página Projetos.
// Linha: [casa ("c"|"s"), sigla, numero, ano, apresentacao, ementa, url, situacao, categoria, autores, total_autores]
// autores (até 4): [casa ("c"|"s"), id, nome, "PARTIDO-UF", primeiro (1|0)]
import { todosProjetos } from "../../lib/dados";

export function GET() {
  const linhas = todosProjetos().map((p) => [
    p.casa === "senado" ? "s" : "c",
    p.sigla, p.numero, p.ano, p.apresentacao ?? "", (p.ementa ?? "").length > 500 ? `${p.ementa!.slice(0, 497).trimEnd()}…` : p.ementa ?? "", p.url ?? "",
    p.situacao ?? "", p.situacao ? (p.categoria ?? "tramitacao") : "sem_informacao",
    p.autores.slice(0, 4).map((a) => [a.casa === "senado" ? "s" : "c", a.id, a.nome, [a.partido, a.uf].filter(Boolean).join("-"), a.primeiro ? 1 : 0]),
    p.autores.length,
  ]);
  return new Response(JSON.stringify(linhas), { headers: { "Content-Type": "application/json; charset=utf-8" } });
}
