from coletor import modelos
from coletor.armazenamento import Armazem


def _votacao(fixture):
    detalhe = fixture("api-votacao-2025-04.json")
    return modelos.montar_votacao(detalhe, fixture("api-votos-2025-04.json"), fixture("api-orientacoes-2025-04.json"), detalhe)


def test_gravar_duas_vezes_nao_altera(tmp_path, fixture):
    a = Armazem(tmp_path)
    v = _votacao(fixture)
    assert a.gravar_votacao(v) is True
    assert a.gravar_votacao(v) is False
    assert a.reconstruir_indice() is True
    assert a.reconstruir_indice() is False


def test_nao_troca_votos_por_vazio(tmp_path, fixture):
    a = Armazem(tmp_path)
    completa = _votacao(fixture)
    a.gravar_votacao(completa)
    sem_votos = {**completa, "votos": [], "totais": {}, "votos_disponiveis": False, "orientacoes": []}
    a.gravar_votacao(sem_votos)
    salva = a.votacao(completa["id"])
    assert salva["votos_disponiveis"] is True
    assert len(salva["votos"]) == len(completa["votos"])
    assert salva["orientacoes"] == completa["orientacoes"]


def test_indice_ordenado_mais_recente_primeiro(tmp_path, fixture):
    a = Armazem(tmp_path)
    v = _votacao(fixture)
    a.gravar_votacao({**v, "id": "1-1", "data": "2023-05-01", "data_hora": "2023-05-01T10:00:00"})
    a.gravar_votacao({**v, "id": "2-1", "data": "2026-04-01", "data_hora": "2026-04-01T10:00:00"})
    a.reconstruir_indice()
    indice = a.ler(a.pasta_votacoes / "indice.json")
    assert [i["id"] for i in indice] == ["2-1", "1-1"]


def test_mesclar_deputados_usa_observacao_mais_recente(tmp_path):
    a = Armazem(tmp_path)
    a.mesclar_deputados({7: {"id": 7, "nome": "Fulano", "partido": "AAA", "uf": "MG", "visto_em": "2024-01-01"}})
    a.mesclar_deputados({7: {"id": 7, "nome": "Fulano", "partido": "BBB", "uf": "MG", "visto_em": "2023-01-01"}})
    assert a.deputados()[7]["partido"] == "AAA"
    a.mesclar_deputados({7: {"id": 7, "nome": "Fulano", "partido": "CCC", "uf": "MG", "visto_em": "2025-01-01"}})
    assert a.deputados()[7]["partido"] == "CCC"


def test_um_voto_por_linha_e_json_valido(tmp_path, fixture):
    import json

    a = Armazem(tmp_path)
    v = _votacao(fixture)
    a.gravar_votacao(v)
    texto = a.caminho_votacao(v["id"]).read_text(encoding="utf-8")
    assert json.loads(texto) == v
    linhas_de_voto = [l for l in texto.splitlines() if l.strip().startswith("[") and l.strip().rstrip(",").endswith("]")]
    assert len(linhas_de_voto) == len(v["votos"])


def test_estado_pendentes_sem_duplicata(tmp_path):
    a = Armazem(tmp_path)
    a.gravar_estado({"ultima_data": "2026-10-01", "pendentes": ["b", "a", "b"]})
    assert a.estado()["pendentes"] == ["a", "b"]


def test_migrar_votacoes_antigas(tmp_path, fixture):
    a = Armazem(tmp_path)
    v = _votacao(fixture)
    antiga = {k: val for k, val in v.items() if k not in ("totais_fonte", "secreta")}
    sem_votos = {**antiga, "id": "8-8", "votos": [], "totais": {}, "votos_disponiveis": False,
                 "descricao": "Votos: \nSr. Fulano: \nSim: 10;\nNão: 2;"}
    a.gravar(a.caminho_votacao(antiga["id"]), antiga)
    a.gravar(a.caminho_votacao("8-8"), sem_votos)
    assert a.migrar() == 2
    assert a.votacao(v["id"])["totais_fonte"] == "votos"
    m = a.votacao("8-8")
    assert m["secreta"] is True and m["totais"] == {"Não": 2, "Sim": 10}
    assert a.migrar() == 0
