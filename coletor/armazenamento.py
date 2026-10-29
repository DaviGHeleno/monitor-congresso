"""Leitura e escrita em dados/. Idempotente: só regrava arquivo cujo conteúdo mudou. Nunca apaga.

dados/
├── votacoes/<id>.json      votação completa (fonte da verdade)
├── votacoes/indice.json    resumo de todas, mais recente primeiro (derivado)
├── deputados.json          cadastro de todos os deputados vistos (derivado + API)
├── deputados/<id>.json     projetos apresentados
└── estado-coleta.json      controle da coleta
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from coletor.modelos import item_indice


# Lista só de valores simples (ex.: um voto [123, "PT", "MG", "Sim"]) fica numa linha só:
# arquivos ~3x menores e diffs legíveis (um voto por linha).
_LISTA_SIMPLES = re.compile(r'\[\n(?:[ ]*(?:"(?:[^"\\\n]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null),?\n)+[ ]*\]')


def _colapsar(m: re.Match) -> str:
    return json.dumps(json.loads(m.group(0)), ensure_ascii=False)


def _serializar(conteudo) -> str:
    texto = json.dumps(conteudo, ensure_ascii=False, indent=1, sort_keys=False)
    return _LISTA_SIMPLES.sub(_colapsar, texto) + "\n"


class Armazem:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)
        self.pasta_votacoes = self.raiz / "votacoes"
        self.pasta_deputados = self.raiz / "deputados"

    # ------------------------------------------------------------ genérico

    def ler(self, caminho: Path, padrao=None):
        if not caminho.exists():
            return padrao
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)

    def gravar(self, caminho: Path, conteudo) -> bool:
        """Grava só se mudou. Retorna True se gravou."""
        texto = _serializar(conteudo)
        if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
            return False
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return True

    # ------------------------------------------------------------ votações

    def caminho_votacao(self, vid: str) -> Path:
        return self.pasta_votacoes / f"{vid}.json"

    def votacao(self, vid: str) -> dict | None:
        return self.ler(self.caminho_votacao(vid))

    def tem_votacao_completa(self, vid: str) -> bool:
        v = self.votacao(vid)
        return bool(v and v.get("votos_disponiveis"))

    def gravar_votacao(self, nova: dict) -> bool:
        """Grava votação. Não troca dado bom por dado pior: se já havia votos e a nova versão veio sem, mantém os antigos."""
        antiga = self.votacao(nova["id"])
        if antiga:
            if antiga.get("votos_disponiveis") and not nova.get("votos_disponiveis"):
                nova = {**nova, "votos": antiga["votos"], "totais": antiga["totais"], "votos_disponiveis": True}
            if not nova.get("orientacoes") and antiga.get("orientacoes"):
                nova = {**nova, "orientacoes": antiga["orientacoes"]}
            if not (nova.get("proposicao") or {}).get("id") and (antiga.get("proposicao") or {}).get("id"):
                nova = {**nova, "proposicao": antiga["proposicao"]}
        return self.gravar(self.caminho_votacao(nova["id"]), nova)

    def todas_votacoes(self):
        for caminho in sorted(self.pasta_votacoes.glob("*.json")):
            if caminho.name != "indice.json":
                yield self.ler(caminho)

    def reconstruir_indice(self) -> bool:
        itens = [item_indice(v) for v in self.todas_votacoes()]
        itens.sort(key=lambda i: (i.get("data_hora") or i.get("data") or "", i["id"]), reverse=True)
        return self.gravar(self.pasta_votacoes / "indice.json", itens)

    # ------------------------------------------------------------ deputados

    def deputados(self) -> dict[int, dict]:
        lista = self.ler(self.raiz / "deputados.json", [])
        return {d["id"]: d for d in lista}

    def gravar_deputados(self, por_id: dict[int, dict]) -> bool:
        lista = sorted(por_id.values(), key=lambda d: (d.get("nome") or "").lower())
        return self.gravar(self.raiz / "deputados.json", lista)

    def mesclar_deputados(self, vistos: dict[int, dict]) -> None:
        """Atualiza cadastro com observações mais recentes (partido muda ao longo do tempo)."""
        atuais = self.deputados()
        for did, novo in vistos.items():
            velho = atuais.get(did)
            if velho is None or (novo.get("visto_em") or "") >= (velho.get("visto_em") or ""):
                atuais[did] = {**(velho or {}), **{k: v for k, v in novo.items() if v is not None}}
        self.gravar_deputados(atuais)

    def gravar_projetos(self, did: int, projetos: list[dict]) -> bool:
        projetos = sorted(projetos, key=lambda p: (p.get("ano") or 0, p.get("numero") or 0), reverse=True)
        return self.gravar(self.pasta_deputados / f"{did}.json", {"id": did, "projetos": projetos})

    # ------------------------------------------------------------ estado

    def estado(self) -> dict:
        return self.ler(self.raiz / "estado-coleta.json", {"ultima_data": None, "pendentes": []})

    def gravar_estado(self, estado: dict) -> bool:
        estado = {**estado, "pendentes": sorted(set(estado.get("pendentes", [])))}
        return self.gravar(self.raiz / "estado-coleta.json", estado)
