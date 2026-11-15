"""Gastos da cota parlamentar (CEAP na Câmara, CEAPS no Senado), de 2023 em diante.

    python -m coletor.gastos              # anos 2023 até hoje
    python -m coletor.gastos --anos 2026  # só um ano (os demais ficam como estão)

Fontes (arquivos anuais, públicos):
  Câmara: https://www.camara.leg.br/cotas/Ano-AAAA.json.zip        (uma linha por despesa, com link da nota fiscal)
          reserva: API /deputados/{id}/despesas, deputado a deputado
  Senado: https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/AAAA
          reserva: https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_AAAA.csv

Grava em dados/gastos/:
  camara/<id>.json, senado/<código>.json   resumo por parlamentar (por ano, por categoria, fornecedores, últimas despesas)
  estado.json                              o que foi coletado e de onde

As despesas linha a linha não ficam no repositório (seriam centenas de MB): todo dia os arquivos anuais
são baixados de novo e só o resumo de cada parlamentar é guardado.

CPF de pessoa física não é guardado: fornecedor pessoa física aparece só com o nome.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

ANO_INICIAL = 2023
DESDE = "2023-02-01"
ULTIMAS = 60
FORNECEDORES = 12

sessao = requests.Session()
sessao.headers.update({"User-Agent": "monitor-congresso (github.com/DaviGHeleno)", "Accept": "*/*"})


def _norm(t: str | None) -> str:
    sem = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return " ".join(sem.lower().split())


def _valor(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").strip()
    if "," in s:  # formato brasileiro 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _data(v) -> str:
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _doc_publico(doc: str | None) -> str | None:
    """Só CNPJ (empresa). CPF de pessoa física não é guardado."""
    d = re.sub(r"\D", "", doc or "")
    return d if len(d) == 14 else None


def _campo(r: dict, *nomes):
    for n in nomes:
        if n in r and r[n] not in (None, ""):
            return r[n]
    return None


def _categoria(t: str | None) -> str:
    t = " ".join((t or "Outros").split())
    return t[:1].upper() + t[1:].lower() if t.isupper() else t


# ---------- Normalização: uma despesa = dict comum ----------

def despesa_camara(r: dict) -> dict | None:
    pid = _campo(r, "nuDeputadoId", "ideCadastro", "idDeputado")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    valor = _valor(_campo(r, "valorLiquido", "vlrLiquido", "valorDocumento", "vlrDocumento"))
    ano = int(_campo(r, "numAno", "ano") or 0)
    mes = int(_campo(r, "numMes", "mes") or 0)
    return {
        "id": pid, "ano": ano, "mes": mes,
        "data": _data(_campo(r, "dataEmissao", "datEmissao", "dataDocumento")) or (f"{ano}-{mes:02d}-01" if ano and mes else ""),
        "categoria": _categoria(_campo(r, "descricao", "txtDescricao", "tipoDespesa")),
        "fornecedor": " ".join(str(_campo(r, "fornecedor", "txtFornecedor", "nomeFornecedor") or "Não informado").split()),
        "cnpj": _doc_publico(_campo(r, "cnpjCPF", "txtCNPJCPF", "cnpjCpfFornecedor")),
        "valor": round(valor, 2),
        "url": _campo(r, "urlDocumento") or None,
    }


def despesa_senado(r: dict, por_nome: dict[str, int]) -> dict | None:
    pid = _campo(r, "codSenador", "codigoSenador", "COD_SENADOR")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = por_nome.get(_norm(_campo(r, "nomeSenador", "SENADOR", "senador")))
    if not pid:
        return None
    ano = int(_campo(r, "ano", "ANO") or 0)
    mes = int(_campo(r, "mes", "MES") or 0)
    return {
        "id": pid, "ano": ano, "mes": mes,
        "data": _data(_campo(r, "data", "DATA", "dataDocumento")) or (f"{ano}-{mes:02d}-01" if ano and mes else ""),
        "categoria": _categoria(_campo(r, "tipoDespesa", "TIPO_DESPESA")),
        "fornecedor": " ".join(str(_campo(r, "fornecedor", "FORNECEDOR") or "Não informado").split()),
        "cnpj": _doc_publico(_campo(r, "cpfCnpj", "CNPJ_CPF", "cnpjCpf")),
        "valor": round(_valor(_campo(r, "valorReembolsado", "VALOR_REEMBOLSADO", "valor")), 2),
        "url": None,
    }


# ---------- Resumo por parlamentar ----------

def resumir(despesas: list[dict]) -> dict:
    por_ano, por_cat, forn = defaultdict(float), defaultdict(float), {}
    validas = [d for d in despesas if d["valor"] and (not d["data"] or d["data"] >= DESDE)]
    for d in validas:
        por_ano[str(d["ano"])] += d["valor"]
        por_cat[d["categoria"]] += d["valor"]
        chave = d["cnpj"] or _norm(d["fornecedor"])
        f = forn.setdefault(chave, {"nome": d["fornecedor"], "cnpj": d["cnpj"], "valor": 0.0, "n": 0})
        f["valor"] += d["valor"]
        f["n"] += 1
    ultimas = sorted(validas, key=lambda d: (d["data"], d["valor"]), reverse=True)[:ULTIMAS]
    r2 = lambda x: round(x, 2)
    return {
        "total": r2(sum(d["valor"] for d in validas)),
        "n": len(validas),
        "por_ano": {k: r2(v) for k, v in sorted(por_ano.items())},
        "por_categoria": [{"categoria": k, "valor": r2(v)} for k, v in sorted(por_cat.items(), key=lambda kv: -kv[1])],
        "fornecedores": [{**f, "valor": r2(f["valor"])} for f in sorted(forn.values(), key=lambda f: -f["valor"])[:FORNECEDORES]],
        "ultimas": [{k: d[k] for k in ("data", "categoria", "fornecedor", "valor", "url")} for d in ultimas],
    }


# ---------- Download ----------

def _get(url: str, **kw) -> requests.Response:
    for tentativa in range(5):
        try:
            r = sessao.get(url, timeout=300, **kw)
            if r.status_code == 404:
                return r
            if r.status_code < 500:
                r.raise_for_status()
                return r
        except requests.RequestException as e:
            if tentativa == 4:
                raise
            print(f"  aviso: {url} {e}", flush=True)
        time.sleep(min(60, 5 * 2 ** tentativa))
    raise RuntimeError(f"fora do ar: {url}")


def baixar_camara(ano: int) -> tuple[list[dict], str]:
    url = f"https://www.camara.leg.br/cotas/Ano-{ano}.json.zip"
    r = _get(url)
    if r.status_code == 404:
        return [], f"{url} (não encontrado)"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".json"))
        corpo = json.loads(z.read(nome).decode("utf-8-sig"))
    linhas = corpo.get("dados", corpo) if isinstance(corpo, dict) else corpo
    return [d for d in (despesa_camara(x) for x in linhas) if d], url


def baixar_camara_api(ano: int, ids: list[int]) -> tuple[list[dict], str]:
    """Reserva: deputado a deputado pela API (mais lento)."""
    saida = []
    for n, pid in enumerate(ids, 1):
        pagina = 1
        while True:
            r = _get(f"https://dadosabertos.camara.leg.br/api/v2/deputados/{pid}/despesas",
                     params={"ano": ano, "itens": 100, "pagina": pagina}, headers={"Accept": "application/json"})
            dados = r.json().get("dados", []) if r.status_code == 200 else []
            for x in dados:
                d = despesa_camara({**x, "nuDeputadoId": pid, "descricao": x.get("tipoDespesa"),
                                    "fornecedor": x.get("nomeFornecedor"), "cnpjCPF": x.get("cnpjCpfFornecedor")})
                if d:
                    saida.append(d)
            if len(dados) < 100:
                break
            pagina += 1
        if n % 50 == 0:
            print(f"  API {ano}: {n}/{len(ids)} deputados", flush=True)
    return saida, "API da Câmara, /deputados/{id}/despesas"


def baixar_senado(ano: int, por_nome: dict[str, int]) -> tuple[list[dict], str]:
    url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
    try:
        r = _get(url, headers={"Accept": "application/json"})
        if r.status_code == 200 and r.text.strip().startswith("["):
            linhas = [d for d in (despesa_senado(x, por_nome) for x in r.json()) if d]
            if linhas:
                return linhas, url
    except Exception as e:
        print(f"  aviso: {url} {e}", flush=True)
    url = f"https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
    r = _get(url)
    if r.status_code == 404:
        return [], f"{url} (não encontrado)"
    texto = r.content.decode("utf-8-sig") if r.content[:3] == b"\xef\xbb\xbf" else r.content.decode("latin-1")
    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if l.upper().startswith('"ANO"') or l.upper().startswith("ANO;")), 0)
    leitor = csv.DictReader(io.StringIO("\n".join(linhas[inicio:])), delimiter=";")
    return [d for d in (despesa_senado(x, por_nome) for x in leitor) if d], url


# ---------- Principal ----------

def _gravar(arquivo: Path, obj) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    if not arquivo.exists() or arquivo.read_text(encoding="utf-8") != texto:
        arquivo.write_text(texto, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="dados")
    args = ap.parse_args(argv)
    dados = Path(args.dados)
    pasta = dados / "gastos"
    hoje = date.today()
    anos = list(range(ANO_INICIAL, hoje.year + 1))
    estado = {"camara": {}, "senado": {}}

    deps = json.loads((dados / "deputados.json").read_text(encoding="utf-8")) if (dados / "deputados.json").exists() else []
    sens = json.loads((dados / "senado/senadores.json").read_text(encoding="utf-8")) if (dados / "senado/senadores.json").exists() else []
    por_nome = {}
    for s in sens:
        for nome in (s.get("nome"), s.get("nome_completo")):
            if nome:
                por_nome[_norm(nome)] = s["id"]

    for casa in ("camara", "senado"):
        por_pessoa: dict[int, list[dict]] = defaultdict(list)
        falhou = False
        for ano in anos:
            print(f"{casa} {ano}…", flush=True)
            try:
                if casa == "camara":
                    linhas, fonte = baixar_camara(ano)
                    if not linhas:
                        linhas, fonte = baixar_camara_api(ano, [d["id"] for d in deps])
                else:
                    linhas, fonte = baixar_senado(ano, por_nome)
            except Exception as e:
                print(f"  erro: {e}", flush=True)
                estado[casa][str(ano)] = {"erro": str(e)[:300]}
                falhou = True
                continue
            for d in linhas:
                por_pessoa[d["id"]].append(d)
            estado[casa][str(ano)] = {"fonte": fonte, "despesas": len(linhas), "total": round(sum(d["valor"] for d in linhas), 2)}
            print(f"  {len(linhas)} despesas · {fonte}", flush=True)
        if falhou:  # não sobrescreve resumos bons com dados incompletos
            print(f"{casa}: algum ano falhou; resumos anteriores mantidos", flush=True)
            continue
        for pid, lista in por_pessoa.items():
            _gravar(pasta / casa / f"{pid}.json", resumir(lista))
        print(f"{casa}: {len(por_pessoa)} parlamentares com despesas", flush=True)

    estado["atualizado_em"] = hoje.isoformat()
    _gravar(pasta / "estado.json", estado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
