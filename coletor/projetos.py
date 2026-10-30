"""Projetos de autoria dos deputados e sua situação, a partir dos arquivos anuais da Câmara.

Arquivos usados (um por ano de apresentação):
  proposicoes-<ano>.json         dados do projeto + último status (situação atual)
  proposicoesAutores-<ano>.json  autores de cada projeto (deputados e outros)

Funções puras: sem rede e sem disco. Toleram variações de nome de campo
(campos aninhados como "ultimoStatus": {...} ou achatados como "ultimoStatus_descricaoSituacao").

Categorias de situação (sempre com o texto oficial guardado ao lado):
  lei           virou lei (transformado em norma jurídica)
  aprovado      aprovado na Câmara: foi ao Senado, aguarda sanção ou promulgação
  tramitacao    ainda em análise (padrão quando a situação não indica desfecho)
  encerrado     arquivado, rejeitado, retirado, devolvido, prejudicado ou vetado
"""

from __future__ import annotations

import re
import unicodedata

TIPOS_PROJETO = {"PL", "PLP", "PEC", "PDL", "PRC"}
CATEGORIAS = ("lei", "aprovado", "tramitacao", "encerrado")

# Ordem importa: a primeira regra que casar decide.
_REGRAS = [
    ("lei", ("norma juridica",)),
    ("encerrado", ("vetad", "arquivad", "remessa ao arquivo", "rejeitad", "retirad", "devolvid", "prejudicad", "perdeu a eficacia",
                   "nao conhecid", "inconstitucional")),
    ("aprovado", ("senado", "sancao", "promulgacao", "remetid", "enviad", "aguardando envio", "autografo")),
]


def _norm(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def categoria(situacao: str | None) -> str:
    texto = _norm(situacao)
    for nome, chaves in _REGRAS:
        if any(c in texto for c in chaves):
            return nome
    return "tramitacao"


def _campo(registro: dict, *caminhos: str):
    """Primeiro valor não vazio entre caminhos como 'ultimoStatus.descricaoSituacao' ou 'ultimoStatus_descricaoSituacao'."""
    for caminho in caminhos:
        valor = registro
        for parte in caminho.split("."):
            valor = valor.get(parte) if isinstance(valor, dict) else None
        if valor not in (None, ""):
            return valor
    return None


def _inteiro(valor) -> int | None:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _id_da_uri(uri) -> int | None:
    m = re.search(r"/(\d+)/?$", str(uri or ""))
    return int(m.group(1)) if m else None


def projeto_do_arquivo(r: dict) -> dict | None:
    sigla = (_campo(r, "siglaTipo") or "").strip().upper()
    if sigla not in TIPOS_PROJETO:
        return None
    pid = _inteiro(_campo(r, "id", "idProposicao")) or _id_da_uri(_campo(r, "uri"))
    if pid is None:
        return None
    situacao = _campo(r, "ultimoStatus.descricaoSituacao", "ultimoStatus_descricaoSituacao",
                      "statusProposicao.descricaoSituacao", "descricaoSituacao")
    return {
        "id": pid,
        "sigla": sigla,
        "numero": _inteiro(_campo(r, "numero")),
        "ano": _inteiro(_campo(r, "ano")),
        "ementa": (_campo(r, "ementa") or "").strip() or None,
        "apresentacao": str(_campo(r, "dataApresentacao") or "")[:10] or None,
        "situacao": situacao.strip() if isinstance(situacao, str) else None,
        "situacao_data": str(_campo(r, "ultimoStatus.dataHora", "ultimoStatus_dataHora",
                                    "statusProposicao.dataHora") or "")[:10] or None,
        "categoria": categoria(situacao) if situacao else "tramitacao",
        "url": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}",
    }


def autor_do_arquivo(r: dict) -> tuple[int, int, bool] | None:
    """(id_proposicao, id_deputado, é_primeiro_autor) ou None se o autor não é deputado."""
    pid = _inteiro(_campo(r, "idProposicao")) or _id_da_uri(_campo(r, "uriProposicao"))
    did = _inteiro(_campo(r, "idDeputadoAutor"))
    if did is None:
        uri = str(_campo(r, "uriAutor") or "")
        did = _id_da_uri(uri) if "/deputados/" in uri else None
    if pid is None or did is None:
        return None
    ordem = _inteiro(_campo(r, "ordemAssinatura"))
    proponente = str(_campo(r, "proponente") or "").strip().lower() in ("1", "true", "sim")
    return pid, did, ordem == 1 or (ordem is None and proponente)


def projetos_por_deputado(proposicoes: list[dict], autores: list[dict], desde: str) -> dict[int, list[dict]]:
    """Junta projetos e autores. Só projetos apresentados a partir de `desde`."""
    por_id = {}
    for r in proposicoes:
        p = projeto_do_arquivo(r)
        if p and (p["apresentacao"] or "") >= desde:
            por_id[p["id"]] = p
    saida: dict[int, dict[int, dict]] = {}
    for r in autores:
        a = autor_do_arquivo(r)
        if not a or a[0] not in por_id:
            continue
        pid, did, primeiro = a
        atual = saida.setdefault(did, {}).get(pid)
        saida[did][pid] = {**por_id[pid], "primeiro_autor": primeiro or bool(atual and atual["primeiro_autor"])}
    return {did: list(ps.values()) for did, ps in saida.items()}


def resumo(projetos: list[dict]) -> dict[str, int]:
    contagem = {c: 0 for c in CATEGORIAS}
    for p in projetos:
        contagem[p.get("categoria") or "tramitacao"] += 1
    return contagem


# ---------------------------------------------------------------- perfil do deputado

def perfil(detalhe: dict | None, profissoes: list[dict] | None) -> dict:
    """Dados públicos para a descrição do deputado. CPF e endereços pessoais não são guardados."""
    d = detalhe or {}
    status = d.get("ultimoStatus") or {}
    gab = status.get("gabinete") or {}
    titulos = []
    for p in profissoes or []:
        t = (p.get("titulo") or "").strip()
        if t and t not in titulos:
            titulos.append(t)
    gabinete = {k: gab.get(k) for k in ("nome", "predio", "sala", "andar", "telefone", "email") if gab.get(k)}
    return {
        "nome_civil": (d.get("nomeCivil") or "").strip() or None,
        "sexo": d.get("sexo") if d.get("sexo") in ("M", "F") else None,
        "nascimento": d.get("dataNascimento") or None,
        "falecimento": d.get("dataFalecimento") or None,
        "municipio_nascimento": d.get("municipioNascimento") or None,
        "uf_nascimento": d.get("ufNascimento") or None,
        "escolaridade": d.get("escolaridade") or None,
        "profissoes": titulos,
        "redes": [r for r in (d.get("redeSocial") or []) if isinstance(r, str) and r.startswith("http")],
        "situacao": status.get("situacao") or None,
        "condicao_eleitoral": status.get("condicaoEleitoral") or None,
        "gabinete": gabinete or None,
    }
