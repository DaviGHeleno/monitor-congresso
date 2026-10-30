"""Ponto de entrada do coletor.

    python -m coletor.coletar --inicial        carga desde 01/02/2023 (arquivos anuais + detalhes da API)
    python -m coletor.coletar --incremental    novas votações via API desde a última coleta
    python -m coletor.coletar --reconciliar    confere o arquivo anual do ano corrente e completa o que faltar
    python -m coletor.coletar --deputados      cadastro, perfil público e projetos (com situação) dos deputados

Opções: --dados <pasta> (padrão: dados), --desde AAAA-MM-DD (só --inicial).
Somente votações do Plenário.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from coletor import modelos, projetos
from coletor.armazenamento import Armazem
from coletor.camara import ID_PLENARIO, Cliente, ErroCamara

INICIO_LEGISLATURA = "2023-02-01"
ID_LEGISLATURA = 57
log = logging.getLogger("coletor")


def hoje() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


# ------------------------------------------------------------------ peças


def completar_da_api(cliente: Cliente, base: dict, linhas_votos: list[dict] | None) -> tuple[dict, list, list]:
    """Busca detalhe e orientações (e votos, se não vieram do arquivo). Falha de um item não derruba a carga."""
    vid = str(base["id"])
    detalhe, orient = None, []
    try:
        detalhe = cliente.dados(f"/votacoes/{vid}")
        orient = cliente.dados(f"/votacoes/{vid}/orientacoes") or []
        if linhas_votos is None:
            linhas_votos = cliente.dados(f"/votacoes/{vid}/votos") or []
    except ErroCamara as e:
        log.warning("detalhe indisponível para %s: %s", vid, e)
    return detalhe, orient, linhas_votos or []


def precisa_revisitar(v: dict | None) -> bool:
    if not v:
        return True
    if v.get("secreta"):
        return False  # voto secreto nunca terá votos individuais
    return not v["votos_disponiveis"] or not v["orientacoes"] or not (v.get("proposicao") or {}).get("id")


def ainda_pendentes(armazem: Armazem, ids) -> list[str]:
    return sorted(vid for vid in set(ids) if precisa_revisitar(armazem.votacao(vid)))


def processar_ano_arquivo(cliente: Cliente, armazem: Armazem, ano: int, desde: str, pasta_tmp: Path) -> tuple[int, set[str], str | None]:
    """Processa um ano a partir dos arquivos anuais. Retorna (gravadas, pendentes, data_mais_recente)."""
    log.info("[%s] baixando arquivos anuais", ano)
    votacoes = cliente.baixar_arquivo("votacoes", ano, pasta_tmp) or []
    linhas_votos = cliente.baixar_arquivo("votacoesVotos", ano, pasta_tmp) or []

    votos_por_id: dict[str, list[dict]] = defaultdict(list)
    for linha in linhas_votos:
        votos_por_id[str(linha.get("idVotacao"))].append(linha)

    gravadas, pendentes, mais_recente = 0, set(), None
    candidatas = [
        v for v in votacoes
        if v.get("siglaOrgao") == "PLEN" and (v.get("data") or "") >= desde
        and modelos.eh_nominal(v.get("descricao"), len(votos_por_id.get(str(v.get("id")), [])))
    ]
    log.info("[%s] %s votações nominais do Plenário", ano, len(candidatas))

    for n, base in enumerate(candidatas, 1):
        vid = str(base["id"])
        existente = armazem.votacao(vid)
        if existente and not precisa_revisitar(existente):
            mais_recente = max(mais_recente or "", existente["data"] or "")
            continue
        linhas = votos_por_id.get(vid, [])
        detalhe, orient, linhas = completar_da_api(cliente, base, linhas or None)
        votacao = modelos.montar_votacao(detalhe or base, linhas, orient, detalhe)
        if armazem.gravar_votacao(votacao):
            gravadas += 1
        armazem.mesclar_deputados(modelos.deputados_dos_votos(linhas, base.get("data") or ""))
        if precisa_revisitar(armazem.votacao(vid)):
            pendentes.add(vid)
        mais_recente = max(mais_recente or "", votacao["data"] or "")
        if n % 50 == 0:
            log.info("[%s] %s/%s", ano, n, len(candidatas))
    return gravadas, pendentes, mais_recente


def processar_votacao_api(cliente: Cliente, armazem: Armazem, base: dict) -> tuple[bool, bool]:
    """Uma votação vinda da API. Retorna (era_nominal, ficou_pendente)."""
    detalhe, orient, linhas = completar_da_api(cliente, base, None)
    origem = detalhe or base
    if not modelos.eh_nominal(origem.get("descricao"), len(linhas)):
        return False, False
    votacao = modelos.montar_votacao(origem, linhas, orient, detalhe)
    armazem.gravar_votacao(votacao)
    armazem.mesclar_deputados(modelos.deputados_dos_votos(linhas, votacao["data"] or ""))
    return True, precisa_revisitar(armazem.votacao(votacao["id"]))


# ------------------------------------------------------------------ modos


def carga_inicial(cliente: Cliente, armazem: Armazem, desde: str) -> None:
    estado = armazem.estado()
    pendentes = set(estado.get("pendentes", []))
    mais_recente = estado.get("ultima_data")
    with tempfile.TemporaryDirectory() as tmp:
        for ano in range(int(desde[:4]), hoje().year + 1):
            gravadas, pend, recente = processar_ano_arquivo(cliente, armazem, ano, desde, Path(tmp))
            pendentes = set(ainda_pendentes(armazem, pendentes | pend))
            if recente:
                mais_recente = max(mais_recente or "", recente)
            log.info("[%s] %s votações gravadas, %s pendentes", ano, gravadas, len(pend))
            armazem.gravar_estado({"ultima_data": mais_recente, "pendentes": sorted(pendentes)})
            armazem.reconstruir_indice()


def reconciliar(cliente: Cliente, armazem: Armazem) -> None:
    estado = armazem.estado()
    with tempfile.TemporaryDirectory() as tmp:
        ano = hoje().year
        _, pend, recente = processar_ano_arquivo(cliente, armazem, ano, f"{ano}-01-01", Path(tmp))
    ultima = max(estado.get("ultima_data") or "", recente or "") or None
    armazem.gravar_estado({"ultima_data": ultima, "pendentes": ainda_pendentes(armazem, set(estado.get("pendentes", [])) | pend)})
    armazem.reconstruir_indice()


def incremental(cliente: Cliente, armazem: Armazem) -> None:
    estado = armazem.estado()
    fim = hoje()
    inicio = date.fromisoformat(estado["ultima_data"]) - timedelta(days=1) if estado.get("ultima_data") else fim - timedelta(days=3)
    log.info("buscando votações de %s a %s", inicio, fim)

    lista = cliente.paginar(
        "/votacoes",
        {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat(), "idOrgao": ID_PLENARIO,
         "ordem": "ASC", "ordenarPor": "dataHoraRegistro"},
    )
    lista = [v for v in lista if v.get("siglaOrgao") in (None, "PLEN")]
    pendentes = set(estado.get("pendentes", []))
    ultima = estado.get("ultima_data")
    novas = 0
    for base in lista:
        vid = str(base["id"])
        existente = armazem.votacao(vid)
        if existente and not precisa_revisitar(existente):
            continue
        nominal, pendente = processar_votacao_api(cliente, armazem, base)
        if not nominal:
            continue
        novas += existente is None
        (pendentes.add if pendente else pendentes.discard)(vid)
        ultima = max(ultima or "", base.get("data") or "")

    # Revisita pendentes antigas (votos ou orientações publicados depois).
    for vid in sorted(pendentes - {str(v["id"]) for v in lista}):
        nominal, pendente = processar_votacao_api(cliente, armazem, {"id": vid})
        if nominal and not pendente:
            pendentes.discard(vid)

    armazem.gravar_estado({"ultima_data": ultima, "pendentes": sorted(pendentes)})
    armazem.reconstruir_indice()
    log.info("%s votações novas; %s pendentes", novas, len(pendentes))


def atualizar_deputados(cliente: Cliente, armazem: Armazem) -> None:
    # Sem idLegislatura a API devolve só quem está em exercício hoje (513).
    # Com idLegislatura devolve todos que passaram pela legislatura (titulares e suplentes).
    em_exercicio = cliente.paginar("/deputados", {"ordem": "ASC", "ordenarPor": "nome"})
    ids_exercicio = {int(d["id"]) for d in em_exercicio}
    da_legislatura = cliente.paginar("/deputados", {"idLegislatura": ID_LEGISLATURA, "ordem": "ASC", "ordenarPor": "nome"})
    cadastro = armazem.deputados()
    vistos = {int(d["id"]): d for d in da_legislatura}
    vistos.update({int(d["id"]): d for d in em_exercicio})  # dados de quem está em exercício prevalecem
    for d in vistos.values():
        did = int(d["id"])
        cadastro[did] = {
            **cadastro.get(did, {}),
            "id": did,
            "nome": d.get("nome"),
            "partido": d.get("siglaPartido"),
            "uf": d.get("siglaUf"),
            "foto": d.get("urlFoto"),
            "email": d.get("email"),
            "visto_em": hoje().isoformat() if did in ids_exercicio else cadastro.get(did, {}).get("visto_em"),
        }
    for did, d in cadastro.items():
        d["em_exercicio"] = did in ids_exercicio
        d["url"] = f"https://www.camara.leg.br/deputados/{did}"
    armazem.gravar_deputados(cadastro)
    log.info("%s deputados no cadastro, %s em exercício", len(cadastro), len(ids_exercicio))

    atualizar_perfis(cliente, armazem, cadastro)
    atualizar_projetos(cliente, armazem, sorted(cadastro))


def atualizar_perfis(cliente: Cliente, armazem: Armazem, cadastro: dict[int, dict]) -> None:
    """Dados públicos de cada deputado (nascimento, escolaridade, profissões, redes, gabinete)."""
    for n, did in enumerate(sorted(cadastro), 1):
        try:
            detalhe = cliente.dados(f"/deputados/{did}")
            profissoes = cliente.dados(f"/deputados/{did}/profissoes") or []
        except ErroCamara as e:
            log.warning("perfil de %s indisponível: %s", did, e)
            continue
        if detalhe:
            cadastro[did]["perfil"] = projetos.perfil(detalhe, profissoes)
        if n % 100 == 0:
            log.info("perfis: %s/%s", n, len(cadastro))
    armazem.gravar_deputados(cadastro)


def atualizar_projetos(cliente: Cliente, armazem: Armazem, ids: list[int]) -> None:
    """Projetos e situação via arquivos anuais (proposicoes + proposicoesAutores)."""
    todas, autores = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for ano in range(int(INICIO_LEGISLATURA[:4]), hoje().year + 1):
            props = cliente.baixar_arquivo("proposicoes", ano, Path(tmp)) or []
            auts = cliente.baixar_arquivo("proposicoesAutores", ano, Path(tmp)) or []
            if props:
                log.info("[%s] proposicoes: %s registros; campos: %s", ano, len(props), sorted(props[0].keys()))
            if auts:
                log.info("[%s] autores: %s registros; campos: %s", ano, len(auts), sorted(auts[0].keys()))
            todas += props
            autores += auts

    por_deputado = projetos.projetos_por_deputado(todas, autores, INICIO_LEGISLATURA)
    total_projetos = sum(len(v) for v in por_deputado.values())
    if total_projetos == 0:
        # Formato dos arquivos mudou ou ficou indisponível: não apaga o que já existe.
        log.error("nenhum projeto extraído dos arquivos anuais; projetos mantidos como estavam")
        return
    contagem = projetos.resumo([p for ps in por_deputado.values() for p in ps])
    sem_situacao = sum(1 for ps in por_deputado.values() for p in ps if not p["situacao"])
    log.info("%s autorias de projetos; por categoria: %s; sem situação: %s", total_projetos, contagem, sem_situacao)
    for did in ids:
        armazem.gravar_projetos(did, por_deputado.get(did, []))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--inicial", action="store_true")
    modo.add_argument("--incremental", action="store_true")
    modo.add_argument("--reconciliar", action="store_true")
    modo.add_argument("--deputados", action="store_true")
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--desde", default=INICIO_LEGISLATURA)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    cliente, armazem = Cliente(), Armazem(args.dados)
    migradas = armazem.migrar()
    if migradas:
        log.info("%s votações atualizadas para o formato novo", migradas)
        armazem.reconstruir_indice()
    try:
        if args.inicial:
            carga_inicial(cliente, armazem, args.desde)
        elif args.incremental:
            incremental(cliente, armazem)
        elif args.reconciliar:
            reconciliar(cliente, armazem)
        else:
            atualizar_deputados(cliente, armazem)
    except ErroCamara as e:
        log.error("Câmara indisponível: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
