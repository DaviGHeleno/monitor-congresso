// Leitura dos JSON gerados pelo coletor (pasta dados/ na raiz do repositório).
// Roda só no build. O site nunca chama a API da Câmara.
import fs from "node:fs";
import path from "node:path";

const RAIZ = process.env.DADOS_DIR ?? path.resolve(process.cwd(), "..", "dados");

export type Proposicao = { id?: number | null; sigla: string; numero: number; ano: number; ementa?: string | null; url?: string | null };
export type Voto = [number, string | null, string | null, string]; // [deputado_id, partido, UF, voto]
export type Orientacao = { sigla: string; tipo: string | null; orientacao: string | null };

export type ItemIndice = {
  id: string;
  data: string;
  data_hora: string | null;
  descricao: string | null;
  resultado: string;
  tipo: "merito" | "procedimental";
  proposicao: Proposicao | null;
  totais: Record<string, number>;
  votos_disponiveis: boolean;
  secreta?: boolean;
};

export type Votacao = ItemIndice & {
  orientacoes: Orientacao[];
  votos: Voto[];
  totais_fonte?: "votos" | "descricao";
  url_api: string;
};

export type Deputado = {
  id: number;
  nome: string;
  partido: string | null;
  uf: string | null;
  foto?: string | null;
  email?: string | null;
  em_exercicio?: boolean;
  url?: string;
  perfil?: Perfil;
};

export type Perfil = {
  nome_civil: string | null;
  sexo?: "M" | "F" | null;
  nascimento: string | null;
  falecimento: string | null;
  municipio_nascimento: string | null;
  uf_nascimento: string | null;
  escolaridade: string | null;
  profissoes: string[];
  redes: string[];
  situacao: string | null;
  condicao_eleitoral: string | null;
  gabinete: { nome?: string; predio?: string; sala?: string; andar?: string; telefone?: string; email?: string } | null;
};

export type CategoriaProjeto = "lei" | "aprovado" | "tramitacao" | "encerrado";
export type Projeto = {
  id: number; sigla: string; numero: number; ano: number; ementa: string | null; url: string | null;
  apresentacao?: string | null; situacao?: string | null; situacao_data?: string | null;
  categoria?: CategoriaProjeto | null; primeiro_autor?: boolean;
};

function ler<T>(relativo: string, padrao: T): T {
  const arquivo = path.join(RAIZ, relativo);
  if (!fs.existsSync(arquivo)) return padrao;
  return JSON.parse(fs.readFileSync(arquivo, "utf-8")) as T;
}

let _indice: ItemIndice[] | null = null;
export function indice(): ItemIndice[] {
  return (_indice ??= ler<ItemIndice[]>("votacoes/indice.json", []));
}

export function votacao(id: string): Votacao {
  return ler<Votacao>(`votacoes/${id}.json`, null as unknown as Votacao);
}

let _deputados: Map<number, Deputado> | null = null;
export function deputados(): Map<number, Deputado> {
  if (!_deputados) {
    const lista = ler<Deputado[]>("deputados.json", []);
    _deputados = new Map(lista.map((d) => [d.id, d]));
  }
  return _deputados;
}

export function projetos(id: number): Projeto[] {
  return ler<{ projetos: Projeto[] }>(`deputados/${id}.json`, { projetos: [] }).projetos;
}

export type VotoDoDeputado = { votacao: ItemIndice; voto: string; partido: string | null };

let _historico: Map<number, VotoDoDeputado[]> | null = null;
/** Histórico de votos por deputado, calculado a partir das votações (mais recente primeiro). */
export function historico(): Map<number, VotoDoDeputado[]> {
  if (_historico) return _historico;
  const mapa = new Map<number, VotoDoDeputado[]>();
  for (const item of indice()) {
    if (!item.votos_disponiveis) continue;
    for (const [id, partido, , voto] of votacao(item.id).votos) {
      if (!mapa.has(id)) mapa.set(id, []);
      mapa.get(id)!.push({ votacao: item, voto, partido });
    }
  }
  return (_historico = mapa);
}

/** Todos que aparecem no cadastro ou votaram em alguma votação. */
export function todosDeputados(): Deputado[] {
  const mapa = new Map(deputados());
  for (const id of historico().keys()) {
    if (!mapa.has(id)) mapa.set(id, { id, nome: `Deputado ${id}`, partido: null, uf: null });
  }
  return [...mapa.values()].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}

/** Controle da coleta: data da última consulta à Câmara e da votação mais recente. */
export function estadoColeta(): { ultima_data?: string | null; ultima_consulta?: string | null } {
  return ler("estado-coleta.json", {});
}

export type Mosaico = {
  colunas: number; linhas: number; colunas_celular: number; linhas_celular: number;
  largura: number; altura: number; ids: number[];
} | null;

/** Grade de fotos gerada pelo coletor (coletor/mosaico.py). Null se ainda não existir. */
export function mosaico(): Mosaico {
  const m = ler<Mosaico>("mosaico.json", null);
  const temImagens = fs.existsSync(caminhoMosaico()) && fs.existsSync(caminhoMosaico(true));
  return m && m.colunas_celular && temImagens ? m : null;
}

export function caminhoMosaico(celular = false): string {
  return path.join(RAIZ, celular ? "mosaico-celular.jpg" : "mosaico.jpg");
}

/** Projetos apresentados por deputados desde 2023, sem repetir coautorias, contados por situação. */
export function resumoProjetos(): { total: number; lei: number; aprovado: number; tramitacao: number; encerrado: number; sem_informacao: number } {
  const pasta = path.join(RAIZ, "deputados");
  const vistos = new Map<number, Projeto>();
  if (fs.existsSync(pasta)) {
    for (const nome of fs.readdirSync(pasta)) {
      if (!nome.endsWith(".json")) continue;
      const { projetos = [] } = JSON.parse(fs.readFileSync(path.join(pasta, nome), "utf-8")) as { projetos?: Projeto[] };
      for (const p of projetos) vistos.set(p.id, p);
    }
  }
  const r = { total: vistos.size, lei: 0, aprovado: 0, tramitacao: 0, encerrado: 0, sem_informacao: 0 };
  for (const p of vistos.values()) {
    const cat = p.situacao ? (p.categoria ?? "tramitacao") : "sem_informacao";
    r[cat as keyof typeof r]++;
  }
  return r;
}
