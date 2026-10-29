"""Converte dados da Câmara (API v2 e arquivos anuais) para o formato do projeto.

Funções puras, sem rede e sem disco.

Formato de uma votação (dados/votacoes/<id>.json):
{
  "id": "2456731-84",
  "data": "2025-04-09",
  "data_hora": "2025-04-09T20:31:10",
  "descricao": "Mantido o texto. Sim: 266; ...",
  "resultado": "aprovada" | "rejeitada" | "mantido" | "suprimido" | "outro",
  "tipo": "merito" | "procedimental",
  "proposicao": {"id": 2456731, "sigla": "PL", "numero": 3469, "ano": 2024, "ementa": "...", "url": "..."} | null,
  "totais": {"Sim": 266, "Não": 118, ...},
  "orientacoes": [{"sigla": "PL", "tipo": "P", "orientacao": "Sim"}, ...],
  "votos": [[deputado_id, "PARTIDO", "UF", "Sim"], ...],   # partido/UF na data do voto
  "votos_disponiveis": true,
  "url_api": "https://dadosabertos.camara.leg.br/api/v2/votacoes/2456731-84"
}
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from coletor.camara import API
from coletor.classificador import classificar

log = logging.getLogger(__name__)

_PLACAR = re.compile(r"\bSim:\s*\d+", re.I)
_PROPOSICAO_NA_DESCRICAO = re.compile(
    r"(?P<nome>Projeto de Lei Complementar|Projeto de Lei|Proposta de Emenda à Constituição|"
    r"Projeto de Decreto Legislativo|Projeto de Resolução|Medida Provisória)\s+nº\s*(?P<numero>[\d.]+)"
    r"(?:-[A-Z])?,?\s*(?:de\s*)?(?P<ano>\d{4})",
    re.I,
)
_SIGLAS = {
    "projeto de lei complementar": "PLP",
    "projeto de lei": "PL",
    "proposta de emenda à constituição": "PEC",
    "projeto de decreto legislativo": "PDL",
    "projeto de resolução": "PRC",
    "medida provisória": "MPV",
}


def url_proposicao(id_proposicao) -> str | None:
    if not id_proposicao:
        return None
    return f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id_proposicao}"


def eh_nominal(descricao: str | None, n_votos: int) -> bool:
    """Votação nominal = tem votos individuais, ou a descrição traz placar ('Sim: 123')."""
    return n_votos > 0 or bool(descricao and _PLACAR.search(descricao))


def resultado(aprovacao, descricao: str | None) -> str:
    if aprovacao in (1, "1"):
        return "aprovada"
    if aprovacao in (0, "0"):
        return "rejeitada"
    texto = (descricao or "").strip().lower()
    for prefixo, valor in (("aprovad", "aprovada"), ("rejeitad", "rejeitada"), ("mantid", "mantido"), ("suprimid", "suprimido")):
        if texto.startswith(prefixo):
            return valor
    return "outro"


def proposicao_da_api(detalhe: dict) -> dict | None:
    """Proposição principal votada, a partir de 'proposicoesAfetadas' do detalhe da API."""
    afetadas = detalhe.get("proposicoesAfetadas") or []
    if not afetadas:
        return None
    p = afetadas[0]
    return {
        "id": p.get("id"),
        "sigla": p.get("siglaTipo"),
        "numero": p.get("numero"),
        "ano": p.get("ano"),
        "ementa": (p.get("ementa") or "").strip() or None,
        "url": url_proposicao(p.get("id")),
    }


def proposicao_da_descricao(descricao: str | None) -> dict | None:
    """Plano B: extrai 'Projeto de Lei nº 1.987, de 2023' do texto. Sem id e sem ementa."""
    m = _PROPOSICAO_NA_DESCRICAO.search(descricao or "")
    if not m:
        return None
    return {
        "id": None,
        "sigla": _SIGLAS[m.group("nome").lower()],
        "numero": int(m.group("numero").replace(".", "")),
        "ano": int(m.group("ano")),
        "ementa": None,
        "url": None,
    }


def _voto_normalizado(linha: dict) -> list | None:
    dep = linha.get("deputado_") or {}
    voto = linha.get("tipoVoto") or linha.get("voto")
    if not dep.get("id") or not voto:
        log.warning("linha de voto incompleta ignorada: %s", linha)
        return None
    return [int(dep["id"]), dep.get("siglaPartido"), dep.get("siglaUf"), voto.strip()]


def votos(linhas: list[dict]) -> list[list]:
    """Normaliza votos da API (/votos) ou do arquivo anual. Ordena por deputado para diffs estáveis."""
    normalizados = [v for v in (_voto_normalizado(l) for l in linhas) if v]
    return sorted(normalizados, key=lambda v: v[0])


def deputados_dos_votos(linhas: list[dict], data: str) -> dict[int, dict]:
    """Dados cadastrais vistos nos votos, com a data da observação (para saber o partido mais recente)."""
    vistos = {}
    for l in linhas:
        dep = l.get("deputado_") or {}
        if not dep.get("id"):
            continue
        vistos[int(dep["id"])] = {
            "id": int(dep["id"]),
            "nome": dep.get("nome"),
            "partido": dep.get("siglaPartido"),
            "uf": dep.get("siglaUf"),
            "foto": dep.get("urlFoto"),
            "visto_em": data,
        }
    return vistos


def orientacoes(linhas: list[dict]) -> list[dict]:
    saida = []
    for l in linhas:
        sigla = l.get("siglaPartidoBloco") or l.get("siglaBancada") or l.get("sigla")
        if not sigla:
            continue
        saida.append(
            {
                "sigla": sigla,
                "tipo": l.get("codTipoLideranca"),
                "orientacao": (l.get("orientacaoVoto") or l.get("orientacao") or "").strip() or None,
            }
        )
    return sorted(saida, key=lambda o: o["sigla"])


def totais(lista_votos: list[list]) -> dict[str, int]:
    return dict(sorted(Counter(v[3] for v in lista_votos).items()))


def montar_votacao(base: dict, linhas_votos: list[dict], linhas_orientacoes: list[dict], detalhe: dict | None) -> dict:
    """Junta as peças numa votação no formato do projeto.

    base: registro da votação (lista/detalhe da API ou linha do arquivo anual votacoes-<ano>.json).
    detalhe: detalhe da API (/votacoes/{id}), usado para a proposição; pode ser None.
    """
    vid = str(base.get("id"))
    descricao = (base.get("descricao") or "").strip() or None
    lista = votos(linhas_votos)
    proposicao = (proposicao_da_api(detalhe) if detalhe else None) or proposicao_da_descricao(descricao)
    return {
        "id": vid,
        "data": base.get("data"),
        "data_hora": base.get("dataHoraRegistro"),
        "descricao": descricao,
        "resultado": resultado(base.get("aprovacao"), descricao),
        "tipo": classificar(descricao),
        "proposicao": proposicao,
        "totais": totais(lista),
        "orientacoes": orientacoes(linhas_orientacoes),
        "votos": lista,
        "votos_disponiveis": bool(lista),
        "url_api": f"{API}/votacoes/{vid}",
    }


CAMPOS_INDICE = ("id", "data", "data_hora", "descricao", "resultado", "tipo", "proposicao", "totais", "votos_disponiveis")


def item_indice(votacao: dict) -> dict:
    item = {k: votacao.get(k) for k in CAMPOS_INDICE}
    if item["proposicao"]:
        p = item["proposicao"]
        item["proposicao"] = {"sigla": p.get("sigla"), "numero": p.get("numero"), "ano": p.get("ano"), "ementa": p.get("ementa")}
    return item


def projeto(p: dict) -> dict:
    """Proposição de autoria de um deputado (lista /proposicoes)."""
    return {
        "id": p.get("id"),
        "sigla": p.get("siglaTipo"),
        "numero": p.get("numero"),
        "ano": p.get("ano"),
        "ementa": (p.get("ementa") or "").strip() or None,
        "url": url_proposicao(p.get("id")),
    }
