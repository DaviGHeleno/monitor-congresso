import pytest

from coletor import projetos


@pytest.mark.parametrize("situacao, esperado", [
    ("Transformado em Norma Jurídica", "lei"),
    ("Transformado em norma jurídica com veto parcial", "lei"),
    ("Aguardando Apreciação pelo Senado Federal", "aprovado"),
    ("Remetida ao Senado Federal", "aprovado"),
    ("Aguardando Sanção", "aprovado"),
    ("Aguardando Promulgação", "aprovado"),
    ("Arquivada", "encerrado"),
    ("Aguardando Remessa ao Arquivo", "encerrado"),
    ("Retirado pelo(a) Autor(a)", "encerrado"),
    ("Devolvida ao(à) Autor(a)", "encerrado"),
    ("Vetado totalmente", "encerrado"),
    ("Prejudicada", "encerrado"),
    ("Aguardando Parecer do Relator na Comissão de Finanças e Tributação (CFT)", "tramitacao"),
    ("Tramitando em Conjunto", "tramitacao"),
    ("Pronta para Pauta no PLENÁRIO (PLEN)", "tramitacao"),
    ("Aguardando Designação de Relator(a)", "tramitacao"),
    ("Ag. Análise de Inconstitucionalidade", "tramitacao"),
    ("Aguardando Redação Final", "aprovado"),
    ("Aguardando Envio à Redação Final", "aprovado"),
    ("Aguardando Apreciação do Veto", "aprovado"),
    (None, "tramitacao"),
])
def test_categoria(situacao, esperado):
    assert projetos.categoria(situacao) == esperado


PROP_ANINHADA = {
    "id": 2400001, "siglaTipo": "PL", "numero": 10, "ano": 2024, "ementa": " Dispõe sobre X. ",
    "dataApresentacao": "2024-03-01T10:00", "ultimoStatus": {"descricaoSituacao": "Arquivada", "dataHora": "2025-01-31T00:00"},
}
PROP_ACHATADA = {
    "id": "2400002", "siglaTipo": "PEC", "numero": "5", "ano": "2023", "ementa": "Altera Y.",
    "dataApresentacao": "2023-05-02T10:00:00", "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica",
}
REQ = {"id": 2400003, "siglaTipo": "REQ", "numero": 1, "ano": 2024, "dataApresentacao": "2024-01-01"}
ANTIGO = {"id": 1, "siglaTipo": "PL", "numero": 1, "ano": 2019, "dataApresentacao": "2019-01-01"}


def test_projeto_do_arquivo_aninhado_e_achatado():
    a = projetos.projeto_do_arquivo(PROP_ANINHADA)
    assert (a["id"], a["sigla"], a["categoria"], a["ementa"], a["situacao_data"]) == (2400001, "PL", "encerrado", "Dispõe sobre X.", "2025-01-31")
    b = projetos.projeto_do_arquivo(PROP_ACHATADA)
    assert (b["id"], b["numero"], b["ano"], b["categoria"]) == (2400002, 5, 2023, "lei")
    assert projetos.projeto_do_arquivo(REQ) is None


def test_projetos_por_deputado():
    autores = [
        {"idProposicao": 2400001, "idDeputadoAutor": 7, "ordemAssinatura": 1, "proponente": 1},
        {"idProposicao": 2400001, "idDeputadoAutor": 8, "ordemAssinatura": 2, "proponente": 1},
        {"uriProposicao": "https://x/api/v2/proposicoes/2400002", "uriAutor": "https://x/api/v2/deputados/7", "ordemAssinatura": "3"},
        {"idProposicao": 2400002, "uriAutor": "https://x/api/v2/orgaos/1", "nomeAutor": "Senado"},
        {"idProposicao": 2400003, "idDeputadoAutor": 7},
        {"idProposicao": 1, "idDeputadoAutor": 7},
    ]
    r = projetos.projetos_por_deputado([PROP_ANINHADA, PROP_ACHATADA, REQ, ANTIGO], autores, "2023-02-01")
    assert sorted(p["id"] for p in r[7]) == [2400001, 2400002]
    assert {p["id"]: p["primeiro_autor"] for p in r[7]} == {2400001: True, 2400002: False}
    assert [p["primeiro_autor"] for p in r[8]] == [False]
    assert projetos.resumo(r[7]) == {"lei": 1, "aprovado": 0, "tramitacao": 0, "encerrado": 1, "sem_informacao": 0}
    sem = projetos.projeto_do_arquivo({**PROP_ANINHADA, "ultimoStatus": {}})
    assert sem["categoria"] is None and projetos.resumo([sem])["sem_informacao"] == 1


def test_perfil_nao_guarda_cpf():
    detalhe = {
        "id": 7, "nomeCivil": "Fulano de Tal", "cpf": "00000000000", "dataNascimento": "1990-01-01",
        "municipioNascimento": "Belo Horizonte", "ufNascimento": "MG", "escolaridade": "Superior",
        "redeSocial": ["https://x.com/fulano", "invalido"],
        "ultimoStatus": {"situacao": "Exercício", "condicaoEleitoral": "Titular",
                         "gabinete": {"nome": "101", "predio": "4", "telefone": "3215-0000", "email": None}},
    }
    p = projetos.perfil(detalhe, [{"titulo": "Advogado"}, {"titulo": "Advogado"}, {"titulo": "Professor"}])
    assert "cpf" not in p and "00000000000" not in str(p)
    assert p["profissoes"] == ["Advogado", "Professor"]
    assert p["redes"] == ["https://x.com/fulano"]
    assert p["gabinete"] == {"nome": "101", "predio": "4", "telefone": "3215-0000"}
    assert projetos.perfil(None, None)["nome_civil"] is None
