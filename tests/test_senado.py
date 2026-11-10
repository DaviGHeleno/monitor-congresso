import json
from pathlib import Path

from coletor import senado

F = Path(__file__).parent / "fixtures" / "senado"


def ler(n):
    return json.loads((F / n).read_text(encoding="utf-8"))


def test_senadores():
    lista = senado.senadores_da_lista(ler("lista-atual.json"))
    assert len(lista) == 5
    alan = next(s for s in lista if s["id"] == 5672)
    assert alan["uf"] == "AC" and alan["sexo"] == "M" and alan["foto"].startswith("https://")


def test_votacao():
    v = senado.votacao_do_registro(ler("votacao-2025-04.json")[0])
    assert v["id"] == "6923" and v["data"] == "2025-04-01" and v["resultado"] == "aprovada"
    assert v["proposicao"]["sigla"] == "PLP" and v["votos_disponiveis"]
    assert len(v["votos"]) == 81
    assert sum(v["totais"].values()) <= 81 and v["totais"]["Sim"] > v["totais"].get("Não", 0)
    assert "AP" not in v["totais"]


def test_rotulos():
    assert senado.rotulo_voto("P-NRV") == "Presente, não votou"
    assert senado.e_voto(senado.rotulo_voto("Presidente (art. 51 RISF)"))
    assert not senado.e_voto(senado.rotulo_voto("LS"))


def test_categoria():
    assert senado.categoria("TRANSFORMADA EM NORMA JURÍDICA COM VETO PARCIAL") == "lei"
    assert senado.categoria("REMETIDA À CÂMARA DOS DEPUTADOS") == "aprovado"
    assert senado.categoria("ARQUIVADA") == "encerrado"
    assert senado.categoria("TRAMITAÇÃO ENCERRADA") == "encerrado"
    assert senado.categoria("APROVADO PARECER NA COMISSÃO") == "tramitacao"
    assert senado.categoria("AGUARDANDO DESIGNAÇÃO DO RELATOR") == "tramitacao"
    assert senado.categoria(None) is None


def test_projetos():
    ps = senado.projetos_do_autor(ler("processo-5672.json"), "Alan Rick")
    assert ps and all(p["sigla"] in senado.TIPOS_PROJETO for p in ps)
    assert all(p["apresentacao"] >= "2023-02-01" for p in ps)
    assert len({p["id"] for p in ps}) == len(ps)
