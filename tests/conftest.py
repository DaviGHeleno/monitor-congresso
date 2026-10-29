import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

FIXTURES = Path(__file__).parent / "fixtures"


def carregar(nome: str):
    with open(FIXTURES / nome, encoding="utf-8") as f:
        conteudo = json.load(f)
    return conteudo.get("dados", conteudo) if isinstance(conteudo, dict) else conteudo


@pytest.fixture
def fixture():
    return carregar
