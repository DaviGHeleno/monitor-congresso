"""Descrições reais de votações nominais do Plenário (2023–2026), tiradas do spike."""

import pytest

from coletor.classificador import classificar

PROCEDIMENTAIS = [
    "Rejeitado o Requerimento. Sim: 106; não: 259; total: 365.",
    "Aprovado o Requerimento de Urgência (Art. 154 do RICD). Sim: 300; Não: 100; Total: 400.",
    "Rejeitado o Requerimento de Urgência (Art. 155 do RICD).",
    "Aprovado, por unanimidade, o Requerimento de Urgência (Art. 155 do RICD).",
    "Aprovado o Requerimento.",
    "Aprovado o Requerimento nº 2.150/2023, dos Senhores Líderes, que solicita a quebra de interstício de 5 sessões",
    "Rejeitado o Requerimento do Dep. Gilson Marques, que solicita que a pauta da presente Sessão seja apreciada na seguinte ordem",
    "Rejeitada a preferência.",
    "Aprovada a preferência.",
    "Rejeitado o Recurso nº 33/2023, contra a apreciação conclusiva das comissões sobre o Projeto de Lei nº 3.905, de 2021.",
    "Rejeitado o Recurso nº 7/2026 (art. 58, § 1º c/c art. 132, § 2º, RICD). Sim: 154; Não: 245; Abstenção: 3; Total: 402.",
    "Rejeitado o Recurso.",
    "Aprovado o Recurso.",
    "Rejeitada a inclusão.",
]

MERITO = [
    "Mantido o texto. Sim: 266; Não: 118; Total: 384.",
    "Suprimido o texto.",
    "Rejeitada a Emenda de Comissão nº 15.",
    "Aprovado o Substitutivo ao Projeto de Lei Complementar nº 139, de 2022, adotado pelo Relator da Comissão de Finanças e Tributação.",
    "Aprovada a Subemenda Substitutiva Global ao Projeto de Lei nº 1.085, de 2023, adotada pela relatora",
    "Aprovado o Projeto de Lei nº 1.987, de 2023.",
    "Aprovada a Emenda de Plenário nº 4.",
    "Aprovada, em segundo turno, a Proposta de Emenda à Constituição nº 45, de 2019, ressalvados os destaques.",
    "Aprovado o Projeto de Decreto Legislativo nº 745, de 2017.",
    "Aprovada a Medida Provisória nº 1.152 de 2022, na forma do Projeto de Lei de Conversão, ressalvado o destaque.",
    "Aprovada a Redação Final assinada pela Relatora Dep. Jandira Feghali (PCdoB-RJ).",
    "Aprovado o Substitutivo do Senado Federal ao Projeto de Lei nº 6.385-C, de 2016, ressalvados os destaques.",
    "Rejeitado o Destaque.",
    "Aprovado o parecer da Comissão de Constituição e Justiça e de Cidadania à Comunicação de Medida Cautelar nº 1/2024.",
    "Rejeitado o Substitutivo ao Projeto de Lei Complementar nº 223, de 2023, da Comissão de Indústria, Comércio e Serviços.",
    "Aprovado o Projeto de Resolução nº 27, de 2025.",
]

INCERTOS = ["", None, "Resultado.", "Aprovadas.", "Votos:\n\nSra. Fulana:"]


@pytest.mark.parametrize("descricao", PROCEDIMENTAIS)
def test_procedimental(descricao):
    assert classificar(descricao) == "procedimental"


@pytest.mark.parametrize("descricao", MERITO)
def test_merito(descricao):
    assert classificar(descricao) == "merito"


@pytest.mark.parametrize("descricao", INCERTOS)
def test_incerto_vira_merito(descricao):
    assert classificar(descricao) == "merito"


def test_ementa_requerimento_classifica_mesmo_com_descricao_vaga():
    assert classificar("Aprovado.", sigla_tipo="REQ") == "procedimental"
    assert classificar("Aprovado.", sigla_tipo="PL") == "merito"
