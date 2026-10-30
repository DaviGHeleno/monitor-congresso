"""Fluxos do coletor com uma Câmara falsa (sem internet), alimentada pelas amostras reais."""

from datetime import date

import pytest

from coletor import coletar
from coletor.armazenamento import Armazem
from coletor.camara import ErroCamara
from tests.conftest import carregar

ID_API = "2456731-84"          # votação de 2025 com detalhe, votos e orientações na API
ID_ARQUIVO = "945492-151"      # votação de 2024 com votos no arquivo anual


class CamaraFalsa:
    def __init__(self, falhar_detalhe=False):
        self.falhar_detalhe = falhar_detalhe
        self.chamadas = []
        detalhe = carregar("api-votacao-2025-04.json")
        self.arquivos = {
            ("votacoes", 2024): [
                {"id": ID_ARQUIVO, "data": "2024-12-11", "dataHoraRegistro": "2024-12-11T13:20:00", "siglaOrgao": "PLEN",
                 "descricao": "Aprovado o Projeto de Lei nº 1.987, de 2023. Sim: 50; Não: 9", "aprovacao": 1},
                {"id": "1-1", "data": "2024-12-11", "siglaOrgao": "PLEN", "descricao": "Aprovada a Redação Final.", "aprovacao": 1},
                {"id": "1-2", "data": "2024-12-11", "siglaOrgao": "CCJC", "descricao": "Aprovado. Sim: 30; Não: 2", "aprovacao": 1},
            ],
            ("votacoesVotos", 2024): carregar("arquivo-votos-exemplo-2024.json"),
            ("votacoes", 2025): [{**detalhe, "siglaOrgao": "PLEN"}],
            ("votacoesVotos", 2025): [],
        }
        self.api = {
            f"/votacoes/{ID_API}": detalhe,
            f"/votacoes/{ID_API}/votos": carregar("api-votos-2025-04.json"),
            f"/votacoes/{ID_API}/orientacoes": carregar("api-orientacoes-2025-04.json"),
            f"/votacoes/{ID_ARQUIVO}": {"id": ID_ARQUIVO, "data": "2024-12-11", "descricao": "Aprovado o Projeto de Lei nº 1.987, de 2023.",
                                        "aprovacao": 1, "proposicoesAfetadas": [{"id": 999, "siglaTipo": "PL", "numero": 1987, "ano": 2023, "ementa": "Ementa X"}]},
            f"/votacoes/{ID_ARQUIVO}/orientacoes": carregar("api-orientacoes-2024-03.json"),
        }

    def baixar_arquivo(self, tipo, ano, pasta):
        return self.arquivos.get((tipo, ano), [])

    def dados(self, caminho, params=None):
        self.chamadas.append(caminho)
        if self.falhar_detalhe and caminho.count("/") == 2:
            raise ErroCamara("fora do ar")
        return self.api.get(caminho, [])

    def paginar(self, caminho, params=None):
        self.chamadas.append(caminho)
        if caminho == "/votacoes":
            return [{"id": ID_API, "data": carregar("api-votacao-2025-04.json")["data"], "siglaOrgao": "PLEN"}]
        return []


@pytest.fixture(autouse=True)
def hoje_fixo(monkeypatch):
    monkeypatch.setattr(coletar, "hoje", lambda: date(2025, 4, 10))


def test_carga_inicial(tmp_path):
    camara, armazem = CamaraFalsa(), Armazem(tmp_path)
    coletar.carga_inicial(camara, armazem, "2023-02-01")

    indice = armazem.ler(armazem.pasta_votacoes / "indice.json")
    assert [i["id"] for i in indice] == [ID_API, ID_ARQUIVO]  # sem simbólica, sem comissão, mais recente primeiro

    v = armazem.votacao(ID_ARQUIVO)
    assert len(v["votos"]) == 59 and v["proposicao"]["id"] == 999 and v["orientacoes"]
    assert armazem.votacao(ID_API)["proposicao"]["sigla"] == "PL"
    assert len(armazem.deputados()) > 400
    assert armazem.estado()["ultima_data"] == carregar("api-votacao-2025-04.json")["data"]


def test_carga_inicial_e_retomavel_e_idempotente(tmp_path):
    armazem = Armazem(tmp_path)
    coletar.carga_inicial(CamaraFalsa(), armazem, "2023-02-01")
    antes = {p.name: p.read_text() for p in tmp_path.rglob("*.json")}
    camara = CamaraFalsa()
    coletar.carga_inicial(camara, armazem, "2023-02-01")
    depois = {p.name: p.read_text() for p in tmp_path.rglob("*.json")}
    assert antes == depois
    assert f"/votacoes/{ID_API}" not in camara.chamadas  # completas não são buscadas de novo


def test_falha_no_detalhe_vira_pendente_e_e_completada_depois(tmp_path):
    armazem = Armazem(tmp_path)
    coletar.carga_inicial(CamaraFalsa(falhar_detalhe=True), armazem, "2023-02-01")
    v = armazem.votacao(ID_ARQUIVO)
    assert len(v["votos"]) == 59                     # votos do arquivo garantidos
    assert v["proposicao"]["id"] is None             # proposição veio só da descrição
    assert v["proposicao"]["sigla"] == "PL"
    assert ID_ARQUIVO in armazem.estado()["pendentes"]

    coletar.carga_inicial(CamaraFalsa(), armazem, "2023-02-01")
    assert armazem.votacao(ID_ARQUIVO)["proposicao"]["id"] == 999
    assert ID_ARQUIVO not in armazem.estado()["pendentes"]


def test_incremental(tmp_path):
    armazem = Armazem(tmp_path)
    coletar.incremental(CamaraFalsa(), armazem)
    v = armazem.votacao(ID_API)
    assert v["votos_disponiveis"] and v["orientacoes"] and v["proposicao"]["id"]
    assert armazem.estado()["ultima_data"] == carregar("api-votacao-2025-04.json")["data"]
    assert armazem.estado()["pendentes"] == []


def test_deputados_em_exercicio_separados_da_legislatura(tmp_path):
    class Falsa(CamaraFalsa):
        def paginar(self, caminho, params=None):
            if caminho == "/deputados" and "idLegislatura" in (params or {}):
                return [{"id": 1, "nome": "Ana", "siglaPartido": "AAA", "siglaUf": "MG"},
                        {"id": 2, "nome": "Bia", "siglaPartido": "BBB", "siglaUf": "SP"}]
            if caminho == "/deputados":
                return [{"id": 1, "nome": "Ana", "siglaPartido": "CCC", "siglaUf": "MG"}]
            return []

    armazem = Armazem(tmp_path)
    coletar.atualizar_deputados(Falsa(), armazem)
    deps = armazem.deputados()
    assert deps[1]["em_exercicio"] is True and deps[1]["partido"] == "CCC"
    assert deps[2]["em_exercicio"] is False


def test_secreta_nao_fica_pendente(tmp_path):
    camara = CamaraFalsa()
    camara.arquivos[("votacoes", 2024)].append(
        {"id": "7-7", "data": "2024-12-11", "siglaOrgao": "PLEN", "descricao": "Votos: \nSr. Fulano: \nSim: 300;\nNão: 9;"})
    armazem = Armazem(tmp_path)
    coletar.carga_inicial(camara, armazem, "2023-02-01")
    assert armazem.votacao("7-7")["secreta"] is True
    assert "7-7" not in armazem.estado()["pendentes"]


def test_atualizar_deputados_com_perfil_e_projetos(tmp_path):
    class Falsa(CamaraFalsa):
        def paginar(self, caminho, params=None):
            if caminho == "/deputados":
                return [{"id": 7, "nome": "Ana", "siglaPartido": "AAA", "siglaUf": "MG"}]
            return []

        def dados(self, caminho, params=None):
            if caminho == "/deputados/7":
                return {"id": 7, "nomeCivil": "Ana Maria", "cpf": "123", "dataNascimento": "1980-02-03", "escolaridade": "Superior"}
            if caminho == "/deputados/7/profissoes":
                return [{"titulo": "Professora"}]
            return super().dados(caminho, params)

        def baixar_arquivo(self, tipo, ano, pasta):
            if (tipo, ano) == ("proposicoes", 2024):
                return [{"id": 50, "siglaTipo": "PL", "numero": 1, "ano": 2024, "dataApresentacao": "2024-02-02",
                         "ultimoStatus": {"descricaoSituacao": "Transformado em Norma Jurídica"}}]
            if (tipo, ano) == ("proposicoesAutores", 2024):
                return [{"idProposicao": 50, "idDeputadoAutor": 7, "ordemAssinatura": 1}]
            return []

    armazem = Armazem(tmp_path)
    coletar.atualizar_deputados(Falsa(), armazem)
    d = armazem.deputados()[7]
    assert d["perfil"]["nome_civil"] == "Ana Maria" and d["perfil"]["profissoes"] == ["Professora"]
    assert "123" not in str(d)
    arq = armazem.ler(armazem.pasta_deputados / "7.json")
    assert arq["resumo"]["lei"] == 1 and arq["projetos"][0]["primeiro_autor"] is True


def test_arquivos_de_projetos_vazios_nao_apagam_existentes(tmp_path):
    class Falsa(CamaraFalsa):
        def paginar(self, caminho, params=None):
            return [{"id": 7, "nome": "Ana"}] if caminho == "/deputados" else []

    armazem = Armazem(tmp_path)
    armazem.gravar_projetos(7, [{"id": 1, "sigla": "PL", "numero": 1, "ano": 2024}])
    coletar.atualizar_deputados(Falsa(), armazem)
    assert len(armazem.ler(armazem.pasta_deputados / "7.json")["projetos"]) == 1
