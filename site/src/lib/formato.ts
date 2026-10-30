import type { ItemIndice, Orientacao, Proposicao } from "./dados";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
export const url = (caminho: string) => `${BASE}${caminho.startsWith("/") ? caminho : `/${caminho}`}`;

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export function data(iso: string | null | undefined, longo = false): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  if (longo) return `${Number(d)} de ${MESES[Number(m) - 1]} de ${a}`;
  return `${d}/${m}/${a}`;
}

export function hora(iso: string | null | undefined): string {
  return iso && iso.length > 10 ? iso.slice(11, 16) : "";
}

export function proposicao(p: Proposicao | null | undefined): string {
  if (!p) return "";
  return `${p.sigla} ${Number(p.numero).toLocaleString("pt-BR")}/${p.ano}`;
}

/** Variações para busca: "PL 3.469/2024", "PL 3469/2024", "PL3469", "3469/2024". */
export function buscaProposicao(p: Proposicao | null | undefined): string {
  if (!p) return "";
  return [proposicao(p), `${p.sigla} ${p.numero}/${p.ano}`, `${p.sigla}${p.numero}`, `${p.numero}/${p.ano}`].join(" ");
}

/** Descrição sem o placar (o placar é mostrado à parte). */
export function descricaoCurta(texto: string | null | undefined): string {
  if (!texto) return "Votação sem descrição";
  const limpo = texto.replace(/\s+/g, " ").trim();
  if (/^votos:/i.test(limpo)) return "Eleição com voto secreto";
  return limpo.replace(/\s*Sim:\s*\d+.*$/i, "").trim() || limpo;
}

export const RESULTADO: Record<string, string> = {
  aprovada: "Aprovada",
  rejeitada: "Rejeitada",
  mantido: "Texto mantido",
  suprimido: "Texto suprimido",
  outro: "Resultado não informado",
};

export const TIPO: Record<ItemIndice["tipo"], string> = { merito: "Mérito", procedimental: "Procedimental" };

/** Ordem fixa de exibição dos tipos de voto. */
export const ORDEM_VOTOS = ["Sim", "Não", "Abstenção", "Obstrução", "Artigo 17"];

export function ordenarTotais(totais: Record<string, number>): [string, number][] {
  return Object.entries(totais).sort(
    ([a], [b]) => (ORDEM_VOTOS.indexOf(a) + 99) % 99 - (ORDEM_VOTOS.indexOf(b) + 99) % 99 || a.localeCompare(b),
  );
}

export function classeVoto(voto: string): string {
  const mapa: Record<string, string> = { Sim: "sim", Não: "nao", Abstenção: "abst", Obstrução: "obst", "Artigo 17": "art17" };
  return mapa[voto] ?? "outro";
}

export const LIDERANCAS = ["Governo", "Maioria", "Minoria", "Oposição"];

/** Orientação que vale para um partido: a do próprio partido ou a da federação que o inclui. */
export function orientacaoDoPartido(partido: string | null, orientacoes: Orientacao[]): string | null {
  if (!partido) return null;
  const alvo = partido.toUpperCase();
  const direta = orientacoes.find((o) => o.sigla.toUpperCase() === alvo);
  if (direta) return direta.orientacao;
  const federacao = orientacoes.find(
    (o) => o.sigla.startsWith("Fdr ") && o.sigla.slice(4).toUpperCase().split("-").includes(alvo),
  );
  return federacao?.orientacao ?? null;
}

export const total = (totais: Record<string, number>) => Object.values(totais).reduce((s, n) => s + n, 0);

export const CATEGORIA_PROJETO: Record<string, { rotulo: string; descricao: string }> = {
  lei: { rotulo: "Virou lei", descricao: "Transformado em norma jurídica" },
  aprovado: { rotulo: "Aprovado na Câmara", descricao: "Foi ao Senado, aguarda sanção ou promulgação" },
  tramitacao: { rotulo: "Em tramitação", descricao: "Ainda em análise nas comissões ou no Plenário" },
  encerrado: { rotulo: "Arquivado ou rejeitado", descricao: "Arquivado, rejeitado, retirado, prejudicado ou vetado" },
};

/** Idade em anos completos numa data (padrão: hoje). */
export function idade(nascimento: string, ate?: string | null): number {
  const n = new Date(nascimento.slice(0, 10) + "T12:00:00");
  const f = ate ? new Date(ate.slice(0, 10) + "T12:00:00") : new Date();
  let anos = f.getFullYear() - n.getFullYear();
  if (f.getMonth() < n.getMonth() || (f.getMonth() === n.getMonth() && f.getDate() < n.getDate())) anos--;
  return anos;
}

/** Nome legível de uma rede social a partir do endereço. */
export function nomeRede(endereco: string): string {
  const host = endereco.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0].toLowerCase();
  const nomes: Record<string, string> = {
    "instagram.com": "Instagram", "facebook.com": "Facebook", "twitter.com": "X (Twitter)", "x.com": "X (Twitter)",
    "youtube.com": "YouTube", "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "threads.net": "Threads",
  };
  return nomes[host] ?? host;
}
