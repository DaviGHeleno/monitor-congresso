"""Resumo diário por e-mail: votações nominais da Câmara e do Senado nas últimas 24 horas.

    python -m coletor.email_diario            # monta e envia
    python -m coletor.email_diario --previa   # só grava previa-email.html, sem enviar

Janela: das 18h de ontem até agora (horário de Brasília). Votações sem hora (comum no Senado)
entram pelo dia: as de hoje.

Variáveis de ambiente (segredos do GitHub):
  GMAIL_USER          conta Gmail que envia (ex.: fulana@gmail.com)
  GMAIL_APP_PASSWORD  senha de app do Gmail (16 letras), não a senha normal
  EMAIL_DESTINO       quem sempre recebe; vários separados por vírgula (padrão: o próprio GMAIL_USER)
  INSCRICOES_CSV      (opcional) link CSV da planilha do Google Forms de inscrição
  CANCELAMENTOS_CSV   (opcional) link CSV da planilha do Google Forms de cancelamento
  FORM_CANCELAR       (opcional) link do formulário de cancelamento, posto no rodapé do e-mail

Inscritos: quem aparece na planilha de inscrição, menos quem cancelou depois da última inscrição.
Os inscritos vão em cópia oculta (ninguém vê o e-mail dos outros), em lotes de 90.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

SITE = "https://davigheleno.github.io/monitor-congresso"
BRASILIA = timezone(timedelta(hours=-3))
RESULTADO = {"aprovada": "Aprovada", "rejeitada": "Rejeitada", "mantido": "Texto mantido", "suprimido": "Texto suprimido"}
ORDEM = ["Sim", "Não", "Abstenção", "Obstrução", "Presidente", "Artigo 17"]


def agora() -> datetime:
    return datetime.now(BRASILIA)


def na_janela(item: dict, fim: datetime) -> bool:
    """Das 18h de ontem até `fim`. Sem hora: só as do dia de `fim`."""
    inicio = (fim - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    dh = item.get("data_hora") or ""
    if len(dh) > 10:
        try:
            momento = datetime.fromisoformat(dh[:19]).replace(tzinfo=BRASILIA)
        except ValueError:
            momento = None
        if momento:
            return inicio <= momento <= fim
    return item.get("data") == fim.date().isoformat()


def _ler(arquivo: Path) -> list[dict]:
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else []


def _prop(p: dict | None) -> str:
    return f"{p['sigla']} {p['numero']}/{p['ano']}" if p else ""


def _placar(totais: dict) -> str:
    itens = sorted(totais.items(), key=lambda kv: (ORDEM.index(kv[0]) if kv[0] in ORDEM else 99, kv[0]))
    return " · ".join(f"{k} {v}" for k, v in itens) or "placar não informado"


def _curta(texto: str | None) -> str:
    t = " ".join((texto or "Votação sem descrição").split())
    corte = t.find(" Sim:")
    return t[:corte].strip() if corte > 0 else t


EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _momento(texto: str) -> datetime:
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto.strip(), fmt)
        except ValueError:
            pass
    return datetime.min


def respostas(texto_csv: str) -> dict[str, datetime]:
    """E-mail -> momento mais recente, a partir do CSV de um Google Forms (qualquer coluna com e-mail)."""
    saida: dict[str, datetime] = {}
    linhas = list(csv.reader(io.StringIO(texto_csv)))
    for linha in linhas[1:]:
        quando = _momento(linha[0]) if linha else datetime.min
        for celula in linha:
            e = celula.strip().lower()
            if EMAIL.match(e):
                saida[e] = max(saida.get(e, datetime.min), quando)
    return saida


def inscritos(texto_inscricoes: str, texto_cancelamentos: str = "") -> list[str]:
    entrou, saiu = respostas(texto_inscricoes), respostas(texto_cancelamentos)
    return sorted(e for e, quando in entrou.items() if e not in saiu or quando > saiu[e])


def _baixar(url: str | None) -> str:
    if not url:
        return ""
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def montar(camara: list[dict], senado: list[dict], fim: datetime, cancelar: str | None = None) -> tuple[str, str, str]:
    """Devolve (assunto, texto simples, html)."""
    casas = [("Câmara dos Deputados", "votacao", [i for i in camara if na_janela(i, fim)]),
             ("Senado Federal", "votacao-senado", [i for i in senado if na_janela(i, fim)])]
    total = sum(len(c[2]) for c in casas)
    dia = fim.strftime("%d/%m/%Y")
    assunto = f"Monitor do Congresso · {dia} · " + (
        "nenhuma votação nominal" if total == 0 else f"{total} votaç{'ão' if total == 1 else 'ões'}")

    texto = [f"Votações nominais das 18h de ontem até {fim:%H:%M} de {dia}.", ""]
    partes = [f'<p style="margin:0 0 20px;color:#555">Votações nominais das 18h de ontem até {fim:%H:%M} de {dia}.</p>']
    for nome, rota, itens in casas:
        partes.append(f'<h2 style="font-size:18px;margin:24px 0 8px;border-bottom:2px solid #191919;padding-bottom:4px">{nome}</h2>')
        texto.append(nome.upper())
        if not itens:
            partes.append('<p style="color:#555;margin:0">Nenhuma votação nominal no período.</p>')
            texto += ["  Nenhuma votação nominal no período.", ""]
            continue
        merito = [i for i in itens if i.get("tipo") != "procedimental"]
        proc = len(itens) - len(merito)
        for i in sorted(merito, key=lambda x: x.get("data_hora") or x["data"]):
            link = f"{SITE}/{rota}/{i['id']}/"
            res = RESULTADO.get(i.get("resultado"), "Resultado não informado")
            cor = {"aprovada": "#0c7866", "rejeitada": "#c0392b"}.get(i.get("resultado"), "#555")
            prop = _prop(i.get("proposicao"))
            ementa = (i.get("proposicao") or {}).get("ementa") or ""
            partes.append(
                '<div style="padding:12px 0;border-bottom:1px solid #ddd">'
                f'<div style="font-size:13px;color:#555">{html.escape(prop)}{" · voto secreto" if i.get("secreta") else ""}</div>'
                f'<div style="font-weight:600;margin:2px 0">{html.escape(_curta(i.get("descricao")))}</div>'
                + (f'<div style="font-size:14px;color:#444;margin:2px 0">{html.escape(ementa[:280])}</div>' if ementa else "")
                + f'<div style="font-size:14px;margin-top:4px"><b style="color:{cor}">{res}</b> · {html.escape(_placar(i.get("totais") or {}))}'
                f' · <a href="{link}" style="color:#1e4bd7">ver votos</a></div></div>')
            texto += [f"- {prop + ': ' if prop else ''}{_curta(i.get('descricao'))}",
                      f"  {res} · {_placar(i.get('totais') or {})}", f"  {link}"]
        if proc:
            frase = f"Mais {proc} votaç{'ão' if proc == 1 else 'ões'} de procedimento (requerimentos, adiamentos e afins)."
            partes.append(f'<p style="font-size:14px;color:#555">{frase} <a href="{SITE}/{"votacoes" if rota == "votacao" else "votacoes-senado"}/" style="color:#1e4bd7">Ver todas</a></p>')
            texto.append(f"  {frase}")
        texto.append("")
    rodape = f'Dados oficiais da Câmara e do Senado. <a href="{SITE}/" style="color:#1e4bd7">Abrir o Monitor do Congresso</a>'
    if cancelar:
        rodape += f'<br>Não quer mais receber? <a href="{cancelar}" style="color:#1e4bd7">Cancelar inscrição</a>'
        texto.append(f"Cancelar inscrição: {cancelar}")
    corpo = ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:0 auto;color:#191919;line-height:1.45">'
             f'<h1 style="font-size:22px;margin:0 0 4px">Como votou o Congresso hoje</h1>{"".join(partes)}'
             f'<p style="font-size:12px;color:#777;margin-top:28px">{rodape}</p></div>')
    texto.append(f"Site: {SITE}/")
    return assunto, "\n".join(texto), corpo


def enviar(assunto: str, texto: str, corpo_html: str) -> int:
    usuario = os.environ["GMAIL_USER"].strip()
    senha = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
    fixos = [d.strip().lower() for d in (os.environ.get("EMAIL_DESTINO") or usuario).split(",") if d.strip()]
    try:
        publico = inscritos(_baixar(os.environ.get("INSCRICOES_CSV")), _baixar(os.environ.get("CANCELAMENTOS_CSV")))
    except requests.RequestException as e:  # planilha fora do ar: manda só para os fixos
        print(f"aviso: não consegui ler as planilhas de inscrição ({e})")
        publico = []
    todos = list(dict.fromkeys(fixos + publico))
    print(f"Destinatários: {len(fixos)} fixos + {len([e for e in publico if e not in fixos])} inscritos")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(usuario, senha)
        for n in range(0, len(todos), 90):
            msg = EmailMessage()
            msg["Subject"], msg["From"], msg["To"] = assunto, f"Monitor do Congresso <{usuario}>", usuario
            msg["Bcc"] = ", ".join(todos[n:n + 90])
            msg.set_content(texto)
            msg.add_alternative(corpo_html, subtype="html")
            s.send_message(msg)
    return len(todos)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--previa", action="store_true")
    args = ap.parse_args(argv)
    d = Path(args.dados)
    assunto, texto, corpo = montar(_ler(d / "votacoes/indice.json"), _ler(d / "senado/votacoes/indice.json"), agora(),
                                  os.environ.get("FORM_CANCELAR") or None)
    print(assunto)
    print(texto)
    if args.previa:
        Path("previa-email.html").write_text(corpo, encoding="utf-8")
        return 0
    print(f"E-mail enviado para {enviar(assunto, texto, corpo)} endereço(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
