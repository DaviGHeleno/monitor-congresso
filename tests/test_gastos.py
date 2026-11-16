from coletor import gastos as g


def test_despesa_camara_sem_cpf():
    d = g.despesa_camara({"nuDeputadoId": "204554", "numAno": 2025, "numMes": 3, "dataEmissao": "2025-03-10T00:00:00",
                          "descricao": "COMBUSTÍVEIS E LUBRIFICANTES.", "fornecedor": "Posto  X", "cnpjCPF": "123.456.789-01",
                          "valorLiquido": "250.5", "urlDocumento": "https://x/nota.pdf"})
    assert d["id"] == 204554 and d["data"] == "2025-03-10" and d["valor"] == 250.5
    assert d["cnpj"] is None and d["fornecedor"] == "Posto X" and d["categoria"] == "Combustíveis e lubrificantes."


def test_despesa_senado_csv_por_nome():
    linha = {"ANO": "2025", "MES": "4", "SENADOR": "ALAN RICK", "TIPO_DESPESA": "Locomoção, hospedagem",
             "CNPJ_CPF": "12.345.678/0001-90", "FORNECEDOR": "Hotel", "DATA": "05/04/2025", "VALOR_REEMBOLSADO": "1.234,56"}
    d = g.despesa_senado(linha, {"alan rick": 5672})
    assert d["id"] == 5672 and d["valor"] == 1234.56 and d["data"] == "2025-04-05" and d["cnpj"] == "12345678000190"


def test_resumir():
    base = {"id": 1, "categoria": "A", "fornecedor": "F", "cnpj": None, "url": None}
    r = g.resumir([{**base, "ano": 2023, "mes": 1, "data": "2023-01-15", "valor": 999.0},  # antes da legislatura
                   {**base, "ano": 2023, "mes": 3, "data": "2023-03-01", "valor": 100.0},
                   {**base, "ano": 2024, "mes": 5, "data": "2024-05-01", "valor": 50.0, "categoria": "B"}])
    assert r["total"] == 150.0 and r["por_ano"] == {"2023": 100.0, "2024": 50.0}
    assert r["por_categoria"][0]["categoria"] == "A" and r["fornecedores"][0]["n"] == 2
    assert r["ultimas"][0]["data"] == "2024-05-01"


def test_detalhe_compacto():
    base = {"id": 1, "ano": 2025, "mes": 3, "categoria": "A", "fornecedor": "Loja", "cnpj": "12345678000190"}
    x = g.detalhe([{**base, "data": "2025-03-01", "valor": 10.0, "url": g.URL_CAMARA + "doc/1.pdf"},
                   {**base, "data": "2025-04-01", "valor": 20.0, "url": None, "categoria": "B"},
                   {**base, "data": "2022-12-01", "valor": 99.0, "url": None}])
    assert x["categorias"] == ["B", "A"] and x["fornecedores"] == [["Loja", "12345678000190"]]
    assert x["d"] == [["2025-04-01", 0, 0, 20.0, ""], ["2025-03-01", 1, 0, 10.0, "doc/1.pdf"]]
