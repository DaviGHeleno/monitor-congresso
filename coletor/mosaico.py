"""Mosaico com as fotos oficiais dos deputados em exercício, para a abertura da página inicial.

    python -m coletor.mosaico [--dados dados]

Gera:
  dados/mosaico.jpg          grade larga (57 colunas x 9 linhas), para telas de computador
  dados/mosaico-celular.jpg  grade alta (27 colunas x 19 linhas), para celular
  dados/mosaico.json         {"colunas", "linhas", "colunas_celular", "linhas_celular", "ids": [ordem], "assinatura"}
Cada célula é uma foto oficial em tons de cinza; o site pinta cada uma com a cor do voto.

Ordem das células: partidos do maior para o menor, e dentro de cada um por nome. Assim, quando o site
pinta cada rosto com o voto, a posição de cada bancada aparece como um bloco.

Só refaz a imagem quando a lista de deputados em exercício (ou seus partidos) muda.
Uma foto que não baixar vira uma célula cinza; o site continua funcionando sem a imagem.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import requests

COLUNAS = 57          # 57 x 9 = 513 cadeiras
COLUNAS_CELULAR = 27  # 27 x 19 = 513
CELULA = (60, 80)     # largura x altura de cada foto, em pixels (3:4)
FUNDO = (58, 58, 58)

log = logging.getLogger("mosaico")


def ordem(deputados: list[dict]) -> list[dict]:
    exercendo = [d for d in deputados if d.get("em_exercicio")]
    tamanho = Counter(d.get("partido") or "" for d in exercendo)
    return sorted(exercendo, key=lambda d: (-tamanho[d.get("partido") or ""], d.get("partido") or "", (d.get("nome") or "").lower()))


def assinatura(lista: list[dict]) -> str:
    chave = "|".join(f"{d['id']}:{d.get('partido')}:{d.get('foto')}" for d in lista)
    return hashlib.sha1(chave.encode()).hexdigest()[:16]


def baixar_foto(sessao: requests.Session, url: str | None):
    from PIL import Image

    if not url:
        return None
    try:
        r = sessao.get(url, timeout=30)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    except Exception as e:  # foto ausente não derruba o mosaico
        log.warning("foto indisponível %s: %s", url, e)
        return None


def preparar(foto):
    """Recorta em 3:4 a partir do topo (rosto), reduz e passa para tons de cinza."""
    from PIL import ImageOps

    foto = ImageOps.exif_transpose(foto).convert("L")
    return ImageOps.fit(foto, CELULA, centering=(0.5, 0.2))


def montar(fotos: list, colunas: int = COLUNAS):
    from PIL import Image

    linhas = max(1, -(-len(fotos) // colunas))
    w, h = CELULA
    folha = Image.new("L", (colunas * w, linhas * h), FUNDO[0])
    for i, foto in enumerate(fotos):
        if foto is not None:
            folha.paste(foto, ((i % colunas) * w, (i // colunas) * h))
    return folha, linhas


def gerar(raiz: Path, baixar=baixar_foto, forcar: bool = False) -> bool:
    """Retorna True se gerou uma imagem nova."""
    deputados = json.loads((raiz / "deputados.json").read_text(encoding="utf-8"))
    lista = ordem(deputados)
    if not lista:
        log.warning("nenhum deputado em exercício no cadastro; mosaico não gerado")
        return False
    sig = assinatura(lista)
    destino_json, destino_jpg, destino_cel = raiz / "mosaico.json", raiz / "mosaico.jpg", raiz / "mosaico-celular.jpg"
    if not forcar and destino_json.exists() and destino_jpg.exists() and destino_cel.exists():
        if json.loads(destino_json.read_text(encoding="utf-8")).get("assinatura") == sig:
            log.info("mosaico em dia")
            return False

    sessao = requests.Session()
    sessao.headers["User-Agent"] = "monitor-congresso"
    fotos, faltando = [], 0
    for n, d in enumerate(lista, 1):
        bruta = baixar(sessao, d.get("foto"))
        fotos.append(preparar(bruta) if bruta is not None else None)
        faltando += bruta is None
        if n % 100 == 0:
            log.info("fotos: %s/%s", n, len(lista))
    folha, linhas = montar(fotos, COLUNAS)
    folha.save(destino_jpg, "JPEG", quality=72, optimize=True, progressive=True)
    folha_cel, linhas_cel = montar(fotos, COLUNAS_CELULAR)
    folha_cel.save(destino_cel, "JPEG", quality=72, optimize=True, progressive=True)
    destino_json.write_text(json.dumps(
        {"colunas": COLUNAS, "linhas": linhas, "colunas_celular": COLUNAS_CELULAR, "linhas_celular": linhas_cel,
         "largura": CELULA[0], "altura": CELULA[1], "ids": [d["id"] for d in lista], "assinatura": sig},
        ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("mosaico gerado: %s deputados, %s sem foto, %s KB", len(lista), faltando, destino_jpg.stat().st_size // 1024)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    gerar(Path(args.dados), forcar=args.forcar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
