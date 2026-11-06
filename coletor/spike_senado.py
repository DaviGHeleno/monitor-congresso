"""Teste de disponibilidade dos dados do Senado (antes de escrever o coletor).

    python coletor/spike_senado.py --saida saida-spike-senado

Consulta a API de Dados Abertos do Senado (legis.senado.leg.br/dadosabertos) em vários endereços candidatos
e registra, para cada um: código HTTP, tamanho e estrutura da resposta. Guarda amostras em fixtures/.

Perguntas que o relatório responde:
  1. Como listar os 81 senadores em exercício (nome, partido, UF, foto)?
  2. Como obter as votações nominais do Plenário num período, com o voto de cada senador?
  3. Como obter os projetos de autoria de cada senador e a situação de cada um?
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://legis.senado.leg.br/dadosabertos"
sessao = requests.Session()
sessao.headers.update({"Accept": "application/json", "User-Agent": "monitor-congresso-spike"})


def estrutura(obj, nivel=0, maximo=4) -> list[str]:
    """Esqueleto das chaves (até `maximo` níveis), para ver o formato sem ler tudo."""
    linhas = []
    pre = "  " * nivel
    if nivel >= maximo:
        return linhas
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:25]:
            tipo = type(v).__name__
            extra = f" [{len(v)}]" if isinstance(v, (list, dict)) else f" = {str(v)[:60]!r}"
            linhas.append(f"{pre}{k}: {tipo}{extra}")
            linhas += estrutura(v, nivel + 1, maximo)
    elif isinstance(obj, list) and obj:
        linhas.append(f"{pre}[0]:")
        linhas += estrutura(obj[0], nivel + 1, maximo)
    return linhas


def buscar(nome: str, caminho: str, pasta: Path, params: dict | None = None) -> dict:
    url = caminho if caminho.startswith("http") else f"{BASE}{caminho}"
    registro = {"nome": nome, "url": url, "params": params}
    for tentativa in range(3):
        try:
            r = sessao.get(url, params=params, timeout=90)
            registro.update(status=r.status_code, tipo=r.headers.get("Content-Type", ""), bytes=len(r.content))
            if r.status_code >= 500 and tentativa < 2:
                time.sleep(5)
                continue
            try:
                corpo = r.json()
                registro["estrutura"] = estrutura(corpo)
            except ValueError:
                corpo = None
                registro["inicio"] = r.text[:400]
            arquivo = pasta / f"{nome}.json"
            if corpo is not None:
                texto = json.dumps(corpo, ensure_ascii=False, indent=1)
                arquivo.write_text(texto[:400_000], encoding="utf-8")
            else:
                arquivo.with_suffix(".txt").write_text(r.text[:100_000], encoding="utf-8")
            registro["corpo"] = corpo
            break
        except requests.RequestException as e:
            registro.update(status="erro", erro=str(e))
            time.sleep(5)
    time.sleep(0.5)
    return registro


def primeiro(obj, *chaves):
    """Procura recursivamente a primeira ocorrência de uma das chaves."""
    if isinstance(obj, dict):
        for k in chaves:
            if k in obj and obj[k] not in (None, ""):
                return obj[k]
        for v in obj.values():
            achou = primeiro(v, *chaves)
            if achou is not None:
                return achou
    elif isinstance(obj, list):
        for v in obj:
            achou = primeiro(v, *chaves)
            if achou is not None:
                return achou
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="saida-spike-senado")
    args = ap.parse_args()
    saida = Path(args.saida)
    fix = saida / "fixtures"
    fix.mkdir(parents=True, exist_ok=True)
    resultados = []

    # Documentação da API (lista de endereços disponíveis).
    for nome, cam in [("api-docs-v3", "/v3/api-docs"), ("api-docs", "/api-docs"), ("swagger", "/swagger-ui/index.html")]:
        resultados.append(buscar(nome, cam, fix))

    # 1. Senadores
    atual = buscar("senador-lista-atual", "/senador/lista/atual.json", fix)
    resultados.append(atual)
    resultados.append(buscar("senador-lista-legislatura-57", "/senador/lista/legislatura/57.json", fix))
    codigo = primeiro(atual.get("corpo"), "CodigoParlamentar", "codigoParlamentar", "codigo")
    print("código de exemplo:", codigo, flush=True)

    if codigo:
        resultados.append(buscar("senador-detalhe", f"/senador/{codigo}.json", fix))
        resultados.append(buscar("senador-autorias", f"/senador/{codigo}/autorias.json", fix))
        resultados.append(buscar("senador-votacoes-2025", f"/senador/{codigo}/votacoes.json", fix, {"ano": 2025}))
        resultados.append(buscar("senador-votacoes", f"/senador/{codigo}/votacoes.json", fix))
        resultados.append(buscar("processo-por-autor", "/processo.json", fix, {"codigoParlamentarAutor": codigo}))
        resultados.append(buscar("processo-por-autor-sem-ext", "/processo", fix, {"codigoParlamentarAutor": codigo}))

    # 2. Votações do Plenário (formatos antigo e novo)
    resultados.append(buscar("plenario-votacao-2025-04", "/plenario/lista/votacao/20250401/20250430.json", fix))
    resultados.append(buscar("plenario-votacao-2026-10", "/plenario/lista/votacao/20261001/20261031.json", fix))
    resultados.append(buscar("votacao-nova-2025-04", "/votacao", fix, {"dataInicio": "2025-04-01", "dataFim": "2025-04-30"}))
    resultados.append(buscar("votacao-nova-json-2025-04", "/votacao.json", fix, {"dataInicio": "2025-04-01", "dataFim": "2025-04-30"}))
    resultados.append(buscar("plenario-orientacao-2025-04", "/plenario/votacao/orientacaoBancada/20250401/20250430.json", fix))

    # 3. Arquivos em massa, se existirem
    resultados.append(buscar("materia-pesquisa-2025", "/materia/pesquisa/lista.json", fix, {"ano": 2025, "sigla": "PL", "tramitando": "S"}))

    linhas = ["# Relatório do spike do Senado", ""]
    for r in resultados:  # lista completa de endereços da documentação, se veio
        caminhos = (r.get("corpo") or {}).get("paths") if isinstance(r.get("corpo"), dict) else None
        if caminhos:
            (saida / "endpoints-senado.txt").write_text("\n".join(sorted(caminhos)), encoding="utf-8")
            linhas += [f"Documentação ({r['nome']}): {len(caminhos)} endereços. Os ligados a votação, senador e processo:", "", "```"]
            linhas += [c for c in sorted(caminhos) if any(k in c.lower() for k in ("vota", "senador", "processo", "autoria", "materia"))][:120]
            linhas += ["```", ""]
            break
    linhas += ["| Endereço | HTTP | Tipo | Tamanho |", "|---|---|---|---|"]
    for r in resultados:
        linhas.append(f"| `{r['url'].replace(BASE, '')}` {r.get('params') or ''} | {r.get('status')} | {r.get('tipo', '')[:30]} | {r.get('bytes', '')} |")
    linhas.append("")
    for r in resultados:
        linhas += [f"## {r['nome']}", "", f"`{r['url']}` {r.get('params') or ''} → {r.get('status')}", ""]
        if r.get("estrutura"):
            linhas += ["```", *r["estrutura"][:80], "```", ""]
        elif r.get("inicio") or r.get("erro"):
            linhas += ["```", (r.get("inicio") or r.get("erro"))[:400], "```", ""]
    relatorio = "\n".join(linhas)
    (saida / "relatorio-senado.md").write_text(relatorio, encoding="utf-8")
    (saida / "resumo.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "corpo"} for r in resultados], ensure_ascii=False, indent=1), encoding="utf-8")
    print(relatorio[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
