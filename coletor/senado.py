"""Coleta do Senado Federal (API de Dados Abertos: legis.senado.leg.br/dadosabertos).

    python -m coletor.senado            # senadores, votações (desde a última data - 45 dias) e projetos
    python -m coletor.senado --inicial  # votações desde 01/02/2023

Endereços usados (confirmados no spike de 10/11/2026):
  /senador/lista/atual.json                         81 senadores em exercício
  /votacao?dataInicio=AAAA-MM-DD&dataFim=...        votações nominais do Plenário, com o voto de cada senador
  /processo?codigoParlamentarAutor=<código>         proposições de autoria do senador, com situação atual

Grava em dados/senado/:
  senadores.json             cadastro
  votacoes/<id>.json         uma votação por arquivo (id = codigoSessaoVotacao)
  votacoes/indice.json       resumo de todas, mais recente primeiro
  senadores/<código>.json    projetos de cada senador
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import requests

from coletor.classificador import classificar

BASE = "https://legis.senado.leg.br/dadosabertos"
INICIO = "2023-02-01"
TIPOS_PROJETO = {"PL", "PLP", "PEC", "PDL", "PRS"}

# Votos em que o senador de fato votou (entram no placar).
VOTOS = {"Sim": "Sim", "Não": "Não", "Nao": "Não", "Abstenção": "Abstenção", "Abst": "Abstenção", "Abstencao": "Abstenção",
         "Presidente (art. 51 RISF)": "Presidente", "Obstrução": "Obstrução"}
# Ausências e registros que não são voto (aparecem na lista, fora do placar).
AUSENCIAS = {"P-NRV": "Presente, não votou", "AP": "Ausente em atividade parlamentar", "LS": "Licença saúde",
             "LP": "Licença particular", "MIS": "Missão oficial", "NCom": "Não compareceu", "REP": "Em representação",
             "LAP": "Licença", "LC": "Licença", "LG": "Licença gestante", "AUS": "Ausente"}


def _norm(texto: str | None) -> str:
    sem = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem.lower().replace("_", " ").split())


def rotulo_voto(sigla: str | None) -> str:
    s = (sigla or "").strip()
    return VOTOS.get(s) or AUSENCIAS.get(s) or s or "Não informado"


def e_voto(rotulo: str) -> bool:
    return rotulo in set(VOTOS.values())


# ---------- Senadores ----------

def senadores_da_lista(corpo: dict) -> list[dict]:
    lista = (((corpo or {}).get("ListaParlamentarEmExercicio") or {}).get("Parlamentares") or {}).get("Parlamentar") or []
    if isinstance(lista, dict):
        lista = [lista]
    saida = []
    for p in lista:
        i = p.get("IdentificacaoParlamentar") or {}
        mandato = p.get("Mandato") or {}
        cod = i.get("CodigoParlamentar")
        if not cod:
            continue
        sexo = (i.get("SexoParlamentar") or "")[:1].upper() or None
        saida.append({
            "id": int(cod),
            "nome": i.get("NomeParlamentar") or f"Senador {cod}",
            "nome_completo": i.get("NomeCompletoParlamentar"),
            "sexo": sexo if sexo in ("M", "F") else None,
            "partido": i.get("SiglaPartidoParlamentar"),
            "uf": i.get("UfParlamentar") or mandato.get("UfParlamentar"),
            "foto": (i.get("UrlFotoParlamentar") or "").replace("http://", "https://") or None,
            "email": i.get("EmailParlamentar"),
            "url": (i.get("UrlPaginaParlamentar") or "").replace("http://", "https://") or None,
            "bloco": (i.get("Bloco") or {}).get("NomeBloco"),
            "participacao": (mandato.get("DescricaoParticipacao") or None),
            "em_exercicio": True,
        })
    return sorted(saida, key=lambda s: _norm(s["nome"]))


# ---------- Votações ----------

def _resultado(codigo: str | None, texto: str | None) -> str:
    c = (codigo or "").strip().upper()
    if c == "A":
        return "aprovada"
    if c == "R":
        return "rejeitada"
    t = _norm(texto)
    if "rejeitad" in t:
        return "rejeitada"
    if "aprovad" in t:
        return "aprovada"
    return "outro"


def _inteiro(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def votacao_do_registro(r: dict) -> dict | None:
    vid = r.get("codigoSessaoVotacao") or r.get("codigoVotacao")
    if not vid:
        return None
    votos_brutos = r.get("votos") or []
    votos = []
    for v in votos_brutos:
        cod = _inteiro(v.get("codigoParlamentar"))
        if cod is None:
            continue
        votos.append([cod, v.get("siglaPartidoParlamentar"), v.get("siglaUFParlamentar"), rotulo_voto(v.get("siglaVotoParlamentar")),
                      v.get("nomeParlamentar")])
    totais: dict[str, int] = {}
    for _, _, _, rot, _ in votos:
        if e_voto(rot):
            totais[rot] = totais.get(rot, 0) + 1
    fonte = "votos"
    if not totais:  # secreta ou sem votos individuais: usa os totais oficiais
        for chave, rot in (("totalVotosSim", "Sim"), ("totalVotosNao", "Não"), ("totalVotosAbstencao", "Abstenção")):
            n = _inteiro(r.get(chave))
            if n:
                totais[rot] = n
        fonte = "oficial"
    sigla, numero, ano = r.get("sigla"), _inteiro(r.get("numero")), _inteiro(r.get("ano"))
    prop = None
    if sigla and numero and ano:
        cm = r.get("codigoMateria")
        prop = {"id": _inteiro(cm), "sigla": sigla, "numero": numero, "ano": ano, "ementa": r.get("ementa"),
                "url": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cm}" if cm else None}
    informe = r.get("informeLegislativo") or {}
    descricao = r.get("descricaoVotacao") or ""
    secreta = (r.get("votacaoSecreta") or "").upper() == "S"
    return {
        "id": str(vid),
        "data": (r.get("dataSessao") or "")[:10],
        "data_hora": r.get("dataSessao"),
        "descricao": descricao,
        "resultado": _resultado(r.get("resultadoVotacao"), informe.get("texto") if isinstance(informe, dict) else None),
        "tipo": classificar(descricao, sigla),
        "proposicao": prop,
        "totais": totais,
        "totais_fonte": fonte,
        "votos_disponiveis": any(e_voto(v[3]) for v in votos),
        "secreta": secreta,
        "informe": (informe.get("texto") or "").strip() if isinstance(informe, dict) else "",
        "votos": votos,
        "url_api": f"{BASE}/votacao?codigoSessao={r.get('codigoSessao')}" if r.get("codigoSessao") else f"{BASE}/votacao",
    }


def item_indice(v: dict) -> dict:
    return {k: v[k] for k in ("id", "data", "data_hora", "descricao", "resultado", "tipo", "proposicao", "totais",
                              "votos_disponiveis", "secreta")}


# ---------- Projetos ----------

_REGRAS = [
    ("lei", ("norma juridica",)),
    ("encerrado", ("arquivad", "rejeitad", "retirad", "prejudicad", "vetad", "tramitacao encerrada", "devolvid", "perdeu a eficacia")),
    ("aprovado", ("remetida a camara", "remetido a camara", "sancao", "promulgacao", "aprovada", "aprovado pelo plenario",
                  "remetida a sancao", "aguardando sancao")),
]


def categoria(situacao: str | None) -> str | None:
    if not situacao:
        return None
    t = _norm(situacao)
    if t.startswith("aprovado parecer"):
        return "tramitacao"
    for nome, chaves in _REGRAS:
        if any(c in t for c in chaves):
            return nome
    return "tramitacao"


def _primeiro_autor(autoria: str | None) -> str:
    primeiro = (autoria or "").split(",")[0]
    primeiro = re.sub(r"^\s*senador[a]?\s+", "", primeiro, flags=re.I)
    return _norm(re.sub(r"\s*\(.*$", "", primeiro))


def projetos_do_autor(registros: list[dict], nome_senador: str, desde: str = INICIO) -> list[dict]:
    saida, vistos = [], set()
    for r in registros or []:
        ident = r.get("identificacao") or ""
        m = re.match(r"^([A-Z]+)\s+(\d+)/(\d{4})", ident)
        if not m or m.group(1) not in TIPOS_PROJETO:
            continue
        apresent = (r.get("dataApresentacao") or "")[:10]
        if apresent and apresent < desde:
            continue
        pid = _inteiro(r.get("id")) or _inteiro(r.get("codigoMateria"))
        if pid in vistos:
            continue
        vistos.add(pid)
        cm = r.get("codigoMateria")
        situacao = r.get("situacaoAtual")
        saida.append({
            "id": pid, "sigla": m.group(1), "numero": int(m.group(2)), "ano": int(m.group(3)),
            "ementa": r.get("ementa"),
            "url": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cm}" if cm else None,
            "apresentacao": apresent or None,
            "situacao": situacao.capitalize() if situacao else None,
            "situacao_data": (r.get("dataSituacaoAtual") or "")[:10] or None,
            "categoria": categoria(situacao),
            "primeiro_autor": _primeiro_autor(r.get("autoria")) == _norm(nome_senador),
        })
    saida.sort(key=lambda p: p["apresentacao"] or "", reverse=True)
    return saida


# ---------- Rede e disco ----------

class Cliente:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", "User-Agent": "monitor-congresso (github.com/DaviGHeleno)"})

    def get(self, caminho: str, params: dict | None = None):
        for tentativa in range(6):
            try:
                r = self.s.get(f"{BASE}{caminho}", params=params, timeout=120)
                if r.status_code == 404:
                    return None
                if r.status_code < 500:
                    r.raise_for_status()
                    time.sleep(0.3)
                    return r.json()
            except (requests.RequestException, ValueError) as e:
                if tentativa == 5:
                    raise
                print(f"  aviso: {caminho} {e}", flush=True)
            time.sleep(min(60, 5 * 2 ** tentativa))
        raise RuntimeError(f"Senado fora do ar: {caminho}")


def _gravar(arquivo: Path, obj) -> bool:
    texto = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if arquivo.exists() and arquivo.read_text(encoding="utf-8") == texto:
        return False
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8")
    return True


def _meses(inicio: date, fim: date):
    atual = inicio
    while atual <= fim:
        prox = date(atual.year + (atual.month == 12), atual.month % 12 + 1, 1)
        yield atual, min(fim, prox - timedelta(days=1))
        atual = prox


def coletar_votacoes(cli: Cliente, pasta: Path, inicial: bool) -> int:
    vpasta = pasta / "votacoes"
    indice_arq = vpasta / "indice.json"
    indice = {i["id"]: i for i in (json.loads(indice_arq.read_text(encoding="utf-8")) if indice_arq.exists() else [])}
    if inicial or not indice:
        inicio = date.fromisoformat(INICIO)
    else:
        inicio = date.fromisoformat(max(i["data"] for i in indice.values())) - timedelta(days=45)
    novas = 0
    for a, b in _meses(inicio, date.today()):
        corpo = cli.get("/votacao", {"dataInicio": a.isoformat(), "dataFim": b.isoformat()}) or []
        for r in corpo if isinstance(corpo, list) else []:
            v = votacao_do_registro(r)
            if not v:
                continue
            novas += v["id"] not in indice
            _gravar(vpasta / f"{v['id']}.json", v)
            indice[v["id"]] = item_indice(v)
        print(f"  {a:%m/%Y}: {len(corpo) if isinstance(corpo, list) else 0} votações", flush=True)
    ordem = sorted(indice.values(), key=lambda i: (i["data_hora"] or i["data"], i["id"]), reverse=True)
    _gravar(indice_arq, ordem)
    return novas


def coletar_senadores(cli: Cliente, pasta: Path) -> list[dict]:
    lista = senadores_da_lista(cli.get("/senador/lista/atual.json") or {})
    if lista:
        _gravar(pasta / "senadores.json", lista)
    elif (pasta / "senadores.json").exists():
        lista = json.loads((pasta / "senadores.json").read_text(encoding="utf-8"))
    return lista


def coletar_projetos(cli: Cliente, pasta: Path, senadores: list[dict]) -> None:
    for n, s in enumerate(senadores, 1):
        try:
            corpo = cli.get("/processo", {"codigoParlamentarAutor": s["id"]}) or []
        except Exception as e:  # um senador com erro não para os outros
            print(f"  erro em {s['nome']}: {e}", flush=True)
            continue
        projs = projetos_do_autor(corpo if isinstance(corpo, list) else [], s["nome"])
        _gravar(pasta / "senadores" / f"{s['id']}.json", {"id": s["id"], "projetos": projs})
        print(f"  {n}/{len(senadores)} {s['nome']}: {len(projs)} projetos", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--inicial", action="store_true")
    ap.add_argument("--sem-projetos", action="store_true")
    args = ap.parse_args(argv)
    pasta = Path(args.dados) / "senado"
    cli = Cliente()
    print("Senadores…", flush=True)
    senadores = coletar_senadores(cli, pasta)
    print(f"  {len(senadores)} senadores", flush=True)
    print("Votações…", flush=True)
    print(f"  {coletar_votacoes(cli, pasta, args.inicial)} novas", flush=True)
    if not args.sem_projetos:
        print("Projetos…", flush=True)
        coletar_projetos(cli, pasta, senadores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
