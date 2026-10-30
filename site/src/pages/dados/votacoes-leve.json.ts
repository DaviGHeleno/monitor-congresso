// Resumo compartilhado das votações, baixado uma vez pelo navegador e usado nas páginas de deputado.
// Formato: [id, data, descricao_curta, proposicao, tipo, texto_extra_para_busca] na mesma ordem de indice().
import { indice } from "../../lib/dados";
import { buscaProposicao, descricaoCurta, proposicao } from "../../lib/formato";

export function GET() {
  const linhas = indice().map((i) => [
    i.id,
    i.data,
    descricaoCurta(i.descricao),
    proposicao(i.proposicao),
    i.tipo,
    [buscaProposicao(i.proposicao), i.proposicao?.ementa].filter(Boolean).join(" "),
  ]);
  return new Response(JSON.stringify(linhas), { headers: { "Content-Type": "application/json; charset=utf-8" } });
}
