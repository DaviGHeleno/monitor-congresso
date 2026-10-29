"""Cliente HTTP para os dados abertos da Câmara.

Só faz rede: novas tentativas, pausa entre chamadas, paginação e download de arquivos.
Não conhece o formato dos dados do projeto.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

API = "https://dadosabertos.camara.leg.br/api/v2"
ARQUIVOS = "https://dadosabertos.camara.leg.br/arquivos"
ID_PLENARIO = 180

log = logging.getLogger(__name__)


class ErroCamara(Exception):
    """A Câmara não respondeu após todas as tentativas."""


class Cliente:
    def __init__(self, pausa: float = 0.25, tentativas: int = 4, sessao: requests.Session | None = None):
        self.pausa = pausa
        self.tentativas = tentativas
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"Accept": "application/json", "User-Agent": "monitor-congresso"})

    def get_json(self, url: str, params: dict | None = None) -> dict | None:
        """GET com novas tentativas (rede, 429, 5xx). 404 retorna None. Falha persistente levanta ErroCamara."""
        espera = 2.0
        for n in range(1, self.tentativas + 1):
            try:
                r = self.sessao.get(url, params=params, timeout=60)
                if r.status_code == 404:
                    return None
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                time.sleep(self.pausa)
                return r.json()
            except (requests.RequestException, ValueError) as e:
                if n == self.tentativas:
                    raise ErroCamara(f"{url}: {e}") from e
                log.warning("tentativa %s falhou (%s): %s; nova tentativa em %ss", n, e, url, espera)
                time.sleep(espera)
                espera *= 2
        return None

    def dados(self, caminho: str, params: dict | None = None):
        """Atalho: GET em API + caminho e retorna o campo 'dados'."""
        resposta = self.get_json(f"{API}{caminho}", params)
        return None if resposta is None else resposta.get("dados")

    def paginar(self, caminho: str, params: dict | None = None) -> list[dict]:
        """Segue os links 'next' da API até o fim."""
        params = dict(params or {})
        params.setdefault("itens", 100)
        url, itens = f"{API}{caminho}", []
        while url:
            resposta = self.get_json(url, params)
            if resposta is None:
                break
            itens.extend(resposta.get("dados", []))
            url = next((l["href"] for l in resposta.get("links", []) if l.get("rel") == "next"), None)
            params = None  # o link 'next' já traz os parâmetros
        return itens

    def baixar_arquivo(self, tipo: str, ano: int, pasta: Path) -> list[dict] | None:
        """Baixa arquivo anual em massa (ex.: tipo='votacoesVotos') e retorna a lista 'dados'."""
        url = f"{ARQUIVOS}/{tipo}/json/{tipo}-{ano}.json"
        destino = pasta / f"{tipo}-{ano}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        for n in range(1, self.tentativas + 1):
            try:
                with self.sessao.get(url, stream=True, timeout=300) as r:
                    if r.status_code == 404:
                        log.warning("arquivo inexistente: %s", url)
                        return None
                    r.raise_for_status()
                    with open(destino, "wb") as f:
                        for parte in r.iter_content(chunk_size=1 << 20):
                            f.write(parte)
                break
            except requests.RequestException as e:
                if n == self.tentativas:
                    raise ErroCamara(f"{url}: {e}") from e
                time.sleep(2 * n)
        with open(destino, encoding="utf-8") as f:
            conteudo = json.load(f)
        return conteudo.get("dados", []) if isinstance(conteudo, dict) else conteudo
