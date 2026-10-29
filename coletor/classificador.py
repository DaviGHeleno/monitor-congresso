"""Classifica uma votação como 'merito' ou 'procedimental'.

Procedimental = decide o andamento da sessão, não o conteúdo de uma lei
(requerimentos de urgência, adiamento, retirada de pauta, ordem de votação,
preferência, recursos contra tramitação, inclusão em pauta).

Na dúvida: 'merito', para nunca esconder algo importante.
"""

from __future__ import annotations

import re
import unicodedata

# Tipos de proposição que são, por natureza, procedimentais.
TIPOS_PROCEDIMENTAIS = {"REQ", "RPD", "RPDR", "REC", "RQU"}

# Núcleo da descrição: "Aprovado/Rejeitado [, ...,] o/a <objeto>".
_OBJETO = re.compile(
    r"^(?:aprovad[oa]s?|rejeitad[oa]s?|mantid[oa]s?)\b[^.]*?\b(?:o|a|os|as)\s+(?P<objeto>[a-z]+)",
)

OBJETOS_PROCEDIMENTAIS = {"requerimento", "requerimentos", "preferencia", "recurso", "recursos", "inclusao"}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def classificar(descricao: str | None, sigla_tipo: str | None = None) -> str:
    if sigla_tipo and sigla_tipo.upper() in TIPOS_PROCEDIMENTAIS:
        return "procedimental"
    if not descricao:
        return "merito"
    texto = _normalizar(descricao)
    m = _OBJETO.match(texto)
    if m and m.group("objeto") in OBJETOS_PROCEDIMENTAIS:
        return "procedimental"
    return "merito"
