import json

from PIL import Image

from coletor import mosaico


def _cadastro(tmp_path, deputados):
    (tmp_path / "deputados.json").write_text(json.dumps(deputados), encoding="utf-8")


DEPS = [
    {"id": 1, "nome": "Bia", "partido": "AAA", "foto": "f1", "em_exercicio": True},
    {"id": 2, "nome": "Ana", "partido": "BBB", "foto": "f2", "em_exercicio": True},
    {"id": 3, "nome": "Caio", "partido": "BBB", "foto": None, "em_exercicio": True},
    {"id": 4, "nome": "Davi", "partido": "AAA", "foto": "f4", "em_exercicio": False},
]


def baixar_falso(sessao, url):
    return Image.new("RGB", (240, 320), (200, 120, 40)) if url else None


def test_ordem_por_tamanho_de_bancada_e_nome():
    assert [d["id"] for d in mosaico.ordem(DEPS)] == [2, 3, 1]


def test_gera_e_so_refaz_quando_muda(tmp_path):
    _cadastro(tmp_path, DEPS)
    assert mosaico.gerar(tmp_path, baixar=baixar_falso) is True
    meta = json.loads((tmp_path / "mosaico.json").read_text())
    assert meta["ids"] == [2, 3, 1] and meta["colunas"] == mosaico.COLUNAS and meta["linhas"] == 1
    img = Image.open(tmp_path / "mosaico.jpg")
    assert img.size == (mosaico.COLUNAS * 60, 80) and img.mode == "L"
    cel = Image.open(tmp_path / "mosaico-celular.jpg")
    assert cel.size == (mosaico.COLUNAS_CELULAR * 60, 80) and meta["colunas_celular"] == 27
    assert mosaico.gerar(tmp_path, baixar=baixar_falso) is False

    _cadastro(tmp_path, [{**d, "partido": "CCC"} if d["id"] == 1 else d for d in DEPS])
    assert mosaico.gerar(tmp_path, baixar=baixar_falso) is True


def test_513_cadeiras_em_9_linhas():
    fotos = [None] * 513
    folha, linhas = mosaico.montar(fotos)
    assert linhas == 9 and folha.size == (57 * 60, 9 * 80)


def test_513_cadeiras_no_celular_em_19_linhas():
    folha, linhas = mosaico.montar([None] * 513, mosaico.COLUNAS_CELULAR)
    assert linhas == 19 and folha.size == (27 * 60, 19 * 80)
