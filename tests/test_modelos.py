from coletor import modelos


def test_votacao_da_api(fixture):
    detalhe = fixture("api-votacao-2025-04.json")
    v = modelos.montar_votacao(detalhe, fixture("api-votos-2025-04.json"), fixture("api-orientacoes-2025-04.json"), detalhe)

    assert v["id"] == "2456731-84"
    assert v["data"] == "2025-04-09" or v["data"].startswith("2025-04")
    assert v["resultado"] == "mantido"  # aprovacao vem null; resultado sai da descrição
    assert v["tipo"] == "merito"
    assert v["proposicao"]["sigla"] == "PL"
    assert v["proposicao"]["numero"] == 3469 and v["proposicao"]["ano"] == 2024
    assert v["proposicao"]["url"].endswith("idProposicao=2456731")
    assert v["votos_disponiveis"] is True
    assert len(v["votos"]) == 389
    assert v["totais"]["Sim"] + v["totais"]["Não"] <= 389
    deputado_id, partido, uf, voto = v["votos"][0]
    assert isinstance(deputado_id, int) and partido and len(uf) == 2 and voto
    assert all(o["sigla"] for o in v["orientacoes"])


def test_votos_do_arquivo_anual_igualam_formato_da_api(fixture):
    linhas = fixture("arquivo-votos-exemplo-2024.json")
    lista = modelos.votos(linhas)
    assert len(lista) == len(linhas) == 59
    assert all(isinstance(v[0], int) for v in lista)  # id vem como texto no arquivo
    assert lista == sorted(lista, key=lambda v: v[0])


def test_orientacao_vazia_vira_none(fixture):
    orient = modelos.orientacoes(fixture("api-orientacoes-2024-03.json"))
    assert all(o["orientacao"] in (None, "Sim", "Não", "Liberado", "Obstrução", "Abstenção") for o in orient)


def test_resultado():
    assert modelos.resultado(1, "qualquer") == "aprovada"
    assert modelos.resultado("0", "qualquer") == "rejeitada"
    assert modelos.resultado(None, "Suprimido o texto.") == "suprimido"
    assert modelos.resultado(None, "Rejeitada a Emenda nº 5") == "rejeitada"
    assert modelos.resultado(None, None) == "outro"


def test_eh_nominal():
    assert modelos.eh_nominal("Rejeitado o Requerimento. Sim: 106; não: 259", 0)
    assert modelos.eh_nominal("Aprovado.", 10)
    assert not modelos.eh_nominal("Aprovada a Redação Final.", 0)


def test_proposicao_da_descricao():
    p = modelos.proposicao_da_descricao("Aprovado o Projeto de Lei nº 1.987, de 2023.")
    assert (p["sigla"], p["numero"], p["ano"]) == ("PL", 1987, 2023)
    p = modelos.proposicao_da_descricao("Aprovado o Substitutivo ao Projeto de Lei Complementar nº 139, de 2022")
    assert p["sigla"] == "PLP"
    p = modelos.proposicao_da_descricao("Aprovado o Substitutivo do Senado Federal ao Projeto de Lei nº 6.385-C, de 2016")
    assert (p["numero"], p["ano"]) == (6385, 2016)
    assert modelos.proposicao_da_descricao("Rejeitado o Requerimento.") is None


def test_item_indice_nao_carrega_votos(fixture):
    detalhe = fixture("api-votacao-2025-04.json")
    v = modelos.montar_votacao(detalhe, fixture("api-votos-2025-04.json"), [], detalhe)
    item = modelos.item_indice(v)
    assert "votos" not in item and "orientacoes" not in item
    assert item["proposicao"]["sigla"] == "PL"


def test_placar_da_descricao():
    assert modelos.placar_da_descricao("Mantido o texto. Sim: 231; Não: 23; Abstenção: 3; Total: 257.") == {
        "Abstenção": 3, "Não": 23, "Sim": 231}
    assert modelos.placar_da_descricao("Aprovada a Emenda. Sim: 311; não: 107 ; total: 419.") == {"Não": 107, "Sim": 311}
    assert modelos.placar_da_descricao("Aprovada a Redação Final.") == {}


def test_secreta():
    assert modelos.eh_secreta("Votos: \nSr. Edvaldo Nilo de Almeida: \nSim: 411;")
    assert not modelos.eh_secreta("Aprovado o Requerimento. Sim: 10")
    assert not modelos.eh_secreta(None)


def test_sem_votos_usa_placar_do_texto():
    base = {"id": "9-9", "data": "2025-12-09", "descricao": "Mantido o texto. Sim: 231; Não: 23; Total: 257.", "aprovacao": None}
    v = modelos.montar_votacao(base, [], [], None)
    assert v["totais"] == {"Não": 23, "Sim": 231} and v["totais_fonte"] == "descricao"
    assert v["votos_disponiveis"] is False and v["secreta"] is False
