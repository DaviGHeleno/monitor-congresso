"""Spike de disponibilidade de dados da Câmara (Fase 1 do plano).

Responde: para cada ano desde 2023, de onde vêm os votos individuais?
  - API v2: /votacoes/{id}/votos
  - Arquivos anuais em massa: votacoesVotos-<ano>.json

Uso:
    python coletor/spike.py --saida saida-spike

Gera em --saida:
    relatorio-spike.md   tabela legível com a conclusão
    resumo.json          mesmos números em formato de máquina
    fixtures/            amostras reais para os testes da Fase 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

API = "https://dadosabertos.camara.leg.br/api/v2"
ARQUIVOS = "https://dadosabertos.camara.leg.br/arquivos"
ANOS = [2023, 2024, 2025, 2026]

# Janelas da amostra via API: um mês com sessão em cada período relevante,
# incluindo antes e depois de maio/2024 (ponto do problema relatado).
JANELAS_API = [
    ("2023-04-01", "2023-04-30"),
    ("2024-03-01", "2024-03-31"),
    ("2024-10-01", "2024-10-31"),
    ("2025-04-01", "2025-04-30"),
    ("2026-04-01", "2026-04-30"),
]
AMOSTRA_POR_JANELA = 15

sessao = requests.Session()
sessao.headers.update({"Accept": "application/json", "User-Agent": "monitor-congresso-spike"})


def log(msg: str) -> None:
    print(msg, flush=True)


def get_json(url: str, params: dict | None = None, tentativas: int = 4) -> dict | None:
    """GET com novas tentativas para erro de rede, 429 e 5xx. Retorna None se 404."""
    espera = 2
    for n in range(1, tentativas + 1):
        try:
            r = sessao.get(url, params=params, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if n == tentativas:
                log(f"  falhou: {url} ({e})")
                return None
            time.sleep(espera)
            espera *= 2
    return None


def baixar_arquivo(url: str, destino: Path) -> Path | None:
    """Baixa arquivo grande em partes. Retorna caminho ou None se indisponível."""
    if destino.exists():
        return destino
    try:
        with sessao.get(url, stream=True, timeout=300) as r:
            if r.status_code != 200:
                log(f"  arquivo indisponível ({r.status_code}): {url}")
                return None
            destino.parent.mkdir(parents=True, exist_ok=True)
            with open(destino, "wb") as f:
                for parte in r.iter_content(chunk_size=1 << 20):
                    f.write(parte)
        return destino
    except requests.RequestException as e:
        log(f"  falha ao baixar {url}: {e}")
        return None


def ler_dados(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        conteudo = json.load(f)
    return conteudo.get("dados", conteudo) if isinstance(conteudo, dict) else conteudo


def campo(registro: dict, *nomes: str):
    """Primeiro campo existente entre os nomes dados (tolera variações de nome)."""
    for nome in nomes:
        if nome in registro and registro[nome] not in (None, ""):
            return registro[nome]
    return None


def mes_de(valor) -> str | None:
    return str(valor)[:7] if valor else None


# ---------------------------------------------------------------- arquivos


def analisar_arquivos(pasta_tmp: Path, pasta_fix: Path) -> dict:
    """Por ano e mês: votações do Plenário × votações com votos individuais no arquivo."""
    resultado = {}
    for ano in ANOS:
        log(f"[arquivos] {ano}")
        f_vot = baixar_arquivo(f"{ARQUIVOS}/votacoes/json/votacoes-{ano}.json", pasta_tmp / f"votacoes-{ano}.json")
        f_votos = baixar_arquivo(
            f"{ARQUIVOS}/votacoesVotos/json/votacoesVotos-{ano}.json", pasta_tmp / f"votacoesVotos-{ano}.json"
        )
        f_ori = baixar_arquivo(
            f"{ARQUIVOS}/votacoesOrientacoes/json/votacoesOrientacoes-{ano}.json",
            pasta_tmp / f"votacoesOrientacoes-{ano}.json",
        )
        info = {"votacoes_disponivel": bool(f_vot), "votos_disponivel": bool(f_votos), "orientacoes_disponivel": bool(f_ori)}

        data_por_id: dict[str, str] = {}
        plen_por_mes: Counter = Counter()
        if f_vot:
            votacoes = ler_dados(f_vot)
            descricoes = []
            for v in votacoes:
                vid = str(campo(v, "id", "idVotacao"))
                data = campo(v, "data", "dataHoraRegistro")
                orgao = campo(v, "siglaOrgao")
                data_por_id[vid] = data
                if orgao == "PLEN":
                    plen_por_mes[mes_de(data)] += 1
                    descricoes.append(
                        {
                            "id": vid,
                            "data": data,
                            "descricao": campo(v, "descricao"),
                            "proposicaoObjeto": campo(v, "proposicaoObjeto"),
                            "aprovacao": campo(v, "aprovacao"),
                        }
                    )
            info["chaves_votacao"] = sorted(votacoes[0].keys()) if votacoes else []
            salvar(pasta_fix / f"descricoes-plenario-{ano}.json", descricoes)

        com_votos_por_mes: Counter = Counter()
        ids_com_votos: set[str] = set()
        if f_votos:
            votos = ler_dados(f_votos)
            info["total_linhas_votos"] = len(votos)
            info["chaves_voto"] = sorted(votos[0].keys()) if votos else []
            for linha in votos:
                ids_com_votos.add(str(campo(linha, "idVotacao", "id")))
            for vid in ids_com_votos:
                com_votos_por_mes[mes_de(data_por_id.get(vid))] += 1
            if votos:
                exemplo_id = str(campo(votos[-1], "idVotacao", "id"))
                salvar(pasta_fix / f"arquivo-votos-exemplo-{ano}.json", [l for l in votos if str(campo(l, "idVotacao", "id")) == exemplo_id])

        ids_com_orientacao: set[str] = set()
        if f_ori:
            for linha in ler_dados(f_ori):
                ids_com_orientacao.add(str(campo(linha, "idVotacao", "id")))

        meses = sorted(m for m in set(plen_por_mes) | set(com_votos_por_mes) if m and m.startswith(str(ano)))
        info["por_mes"] = [
            {"mes": m, "votacoes_plenario": plen_por_mes.get(m, 0), "votacoes_com_votos": com_votos_por_mes.get(m, 0)}
            for m in meses
        ]
        info["ids_com_votos"] = len(ids_com_votos)
        info["ids_com_orientacao"] = len(ids_com_orientacao)
        resultado[ano] = info
        resultado[f"_ids_votos_{ano}"] = ids_com_votos
    return resultado


# ---------------------------------------------------------------- API


def analisar_api(pasta_fix: Path, ids_arquivo: set[str]) -> list[dict]:
    linhas = []
    for inicio, fim in JANELAS_API:
        if date.fromisoformat(inicio) > date.today():
            continue
        log(f"[api] {inicio} a {fim}")
        lista = get_json(
            f"{API}/votacoes",
            {"dataInicio": inicio, "dataFim": fim, "itens": 200, "ordem": "DESC", "ordenarPor": "dataHoraRegistro"},
        )
        if lista is None:
            linhas.append({"janela": f"{inicio} a {fim}", "erro": "lista indisponível"})
            continue
        plen = [v for v in lista.get("dados", []) if v.get("siglaOrgao") == "PLEN"][:AMOSTRA_POR_JANELA]
        com_votos = com_orient = no_arquivo = 0
        fixture_salva = False
        for v in plen:
            vid = str(v["id"])
            votos = get_json(f"{API}/votacoes/{vid}/votos") or {}
            orient = get_json(f"{API}/votacoes/{vid}/orientacoes") or {}
            n_votos = len(votos.get("dados", []))
            n_orient = len(orient.get("dados", []))
            com_votos += n_votos > 0
            com_orient += n_orient > 0
            no_arquivo += vid in ids_arquivo
            if not fixture_salva and (n_votos > 0 or n_orient > 0):
                detalhe = get_json(f"{API}/votacoes/{vid}") or {}
                tag = inicio[:7]
                salvar(pasta_fix / f"api-votacao-{tag}.json", detalhe)
                salvar(pasta_fix / f"api-votos-{tag}.json", votos)
                salvar(pasta_fix / f"api-orientacoes-{tag}.json", orient)
                fixture_salva = True
            time.sleep(0.3)
        linhas.append(
            {
                "janela": f"{inicio} a {fim}",
                "amostra_plenario": len(plen),
                "api_com_votos": com_votos,
                "api_com_orientacoes": com_orient,
                "mesmas_no_arquivo_com_votos": no_arquivo,
            }
        )
    return linhas


# ---------------------------------------------------------------- saída


def salvar(caminho: Path, conteudo) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)


def montar_relatorio(arquivos: dict, api: list[dict]) -> str:
    l = ["# Relatório do spike — disponibilidade de votos individuais", ""]
    l += ["## Amostra via API v2 (votações do Plenário)", ""]
    l += ["| Janela | Amostra | API com votos | API com orientações | Mesmas votações com votos no arquivo anual |", "|---|---|---|---|---|"]
    for x in api:
        if "erro" in x:
            l.append(f"| {x['janela']} | erro: {x['erro']} | | | |")
        else:
            l.append(
                f"| {x['janela']} | {x['amostra_plenario']} | {x['api_com_votos']} | "
                f"{x['api_com_orientacoes']} | {x['mesmas_no_arquivo_com_votos']} |"
            )
    l.append("")
    l.append("Obs.: nem toda votação do Plenário é nominal (há votações simbólicas, sem voto individual). "
             "O que importa é comparar as colunas entre períodos.")
    l += ["", "## Arquivos anuais em massa", ""]
    for ano in ANOS:
        info = arquivos.get(ano, {})
        l.append(f"### {ano}")
        l.append(
            f"Arquivo de votações: {'sim' if info.get('votacoes_disponivel') else 'NÃO'} · "
            f"votos: {'sim' if info.get('votos_disponivel') else 'NÃO'} · "
            f"orientações: {'sim' if info.get('orientacoes_disponivel') else 'NÃO'} · "
            f"votações com votos: {info.get('ids_com_votos', 0)} · com orientação: {info.get('ids_com_orientacao', 0)}"
        )
        l.append("")
        if info.get("por_mes"):
            l += ["| Mês | Votações do Plenário | Votações com votos individuais |", "|---|---|---|"]
            for m in info["por_mes"]:
                l.append(f"| {m['mes']} | {m['votacoes_plenario']} | {m['votacoes_com_votos']} |")
            l.append("")
    return "\n".join(l)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="saida-spike")
    args = ap.parse_args()
    saida = Path(args.saida)
    pasta_fix = saida / "fixtures"
    pasta_tmp = saida / "_downloads"

    arquivos = analisar_arquivos(pasta_tmp, pasta_fix)
    ids_arquivo: set[str] = set()
    for ano in ANOS:
        ids_arquivo |= arquivos.pop(f"_ids_votos_{ano}", set())
    api = analisar_api(pasta_fix, ids_arquivo)

    salvar(saida / "resumo.json", {"arquivos": {str(k): v for k, v in arquivos.items()}, "api": api})
    relatorio = montar_relatorio(arquivos, api)
    (saida / "relatorio-spike.md").write_text(relatorio, encoding="utf-8")
    print("\n" + relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
