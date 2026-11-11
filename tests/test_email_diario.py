from datetime import datetime

from coletor.email_diario import BRASILIA, montar, na_janela

FIM = datetime(2026, 10, 14, 18, 0, tzinfo=BRASILIA)


def item(id, data_hora, tipo="merito", resultado="aprovada"):
    return {"id": id, "data": data_hora[:10], "data_hora": data_hora, "descricao": "Aprovado o projeto. Sim: 10; Não: 2",
            "resultado": resultado, "tipo": tipo, "proposicao": {"sigla": "PL", "numero": 1, "ano": 2026, "ementa": "Ementa"},
            "totais": {"Não": 2, "Sim": 10}}


def test_janela():
    assert na_janela(item("a", "2026-10-13T20:00:00"), FIM)      # ontem à noite
    assert not na_janela(item("b", "2026-10-13T17:59:00"), FIM)  # antes das 18h de ontem
    assert na_janela(item("c", "2026-10-14T11:00:00"), FIM)
    assert na_janela({"data": "2026-10-14", "data_hora": "2026-10-14"}, FIM)  # Senado, sem hora
    assert not na_janela({"data": "2026-10-13", "data_hora": "2026-10-13"}, FIM)


def test_montar():
    camara = [item("1", "2026-10-14T10:00:00"), item("2", "2026-10-14T11:00:00", tipo="procedimental"), item("x", "2026-09-01T10:00:00")]
    senado = [{**item("9", "2026-10-14"), "data_hora": "2026-10-14"}]
    assunto, texto, corpo = montar(camara, senado, FIM)
    assert "3 votações" in assunto
    assert "/votacao/1/" in corpo and "/votacao-senado/9/" in corpo and "/votacao/x/" not in corpo
    assert "Mais 1 votação de procedimento" in texto
    assert "Sim 10 · Não 2" in texto


def test_sem_votacoes():
    assunto, texto, _ = montar([], [], FIM)
    assert "nenhuma votação" in assunto and "Nenhuma votação nominal" in texto
