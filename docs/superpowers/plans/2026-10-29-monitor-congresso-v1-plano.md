# Monitor do Congresso v1 — Plano de implementação

Spec: `docs/superpowers/specs/2026-10-28-monitor-congresso-design.md`
Data: 2026-10-29

## Pré-requisitos (feitos pela Stella, uma vez)

- [ ] Conta no GitHub
- [ ] Repositório `monitor-congresso` criado (público, exigência do GitHub Pages gratuito)
- [ ] Senha de app do Gmail gerada (Conta Google > Segurança > Verificação em 2 etapas > Senhas de app)
- [ ] Secrets no repositório: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_DESTINO`

Observação: o ambiente onde o código é escrito não alcança a API da Câmara. Tudo que precisa da API roda no GitHub Actions (ou no computador da Stella).

## Estrutura final do repositório

```
monitor-congresso/
├── coletor/
│   ├── camara.py            # cliente HTTP: retries, 429, paginação
│   ├── classificador.py     # mérito × procedimental
│   ├── modelos.py           # conversão resposta da API → JSON do projeto
│   ├── armazenamento.py     # leitura/escrita em dados/, idempotente
│   ├── coletar.py           # ponto de entrada: --inicial | --incremental | --deputados
│   └── spike.py             # tarefa 1, removido depois
├── email_resumo/
│   ├── montar.py            # monta HTML/texto do resumo
│   └── enviar.py            # SMTP Gmail
├── tests/
│   ├── fixtures/            # respostas reais da API salvas
│   ├── test_classificador.py
│   ├── test_modelos.py
│   ├── test_armazenamento.py
│   └── test_montar_email.py
├── dados/                   # gerado pelo coletor
├── site/                    # projeto Astro
├── .github/workflows/
│   ├── spike.yml
│   ├── testes.yml           # pytest + build do site em todo push
│   ├── coleta.yml           # de hora em hora
│   ├── deputados.yml        # diário
│   ├── email.yml            # 21h BRT
│   └── publicar.yml         # build Astro + deploy Pages
├── requirements.txt
└── README.md
```

---

## Fase 1 — Spike de disponibilidade de dados

**Tarefa 1.1 — Script de spike** (`coletor/spike.py`)
- Para 2023, 2024, 2025 e 2026: buscar 5 votações nominais via `GET /api/v2/votacoes` (filtro por data).
- Para cada uma: chamar `/votacoes/{id}`, `/votacoes/{id}/votos`, `/votacoes/{id}/orientacoes`; registrar contagem de votos e orientações.
- Baixar o arquivo anual de votos em massa de cada ano (`arquivos/votacoesVotos/json/votacoesVotos-<ano>.json`) e contar votos das mesmas votações.
- Saída: `relatorio-spike.md` com tabela ano × fonte × votos encontrados; salvar também amostras brutas em `tests/fixtures/`.

**Tarefa 1.2 — Workflow** (`.github/workflows/spike.yml`)
- Disparo manual (`workflow_dispatch`); publica relatório e amostras como *artifact* da execução.

**Tarefa 1.3 — Decisão**
- Ler relatório; registrar no spec a fonte escolhida para votos individuais (API, arquivo anual ou combinação).
- **Ponto de parada:** Stella valida a decisão antes da Fase 2.

Pronto quando: relatório mostra, por ano, de onde vêm votos individuais.

## Fase 2 — Coletor

**Tarefa 2.1 — Cliente HTTP** (`camara.py`)
- `requests` com timeout, até 3 novas tentativas com espera crescente em erro de rede e HTTP 429/5xx, paginação via links `next`.
- Pausa curta entre requisições.

**Tarefa 2.2 — Classificador** (`classificador.py`) — testes primeiro
- Montar `test_classificador.py` com 20+ descrições reais das fixtures, metade de cada tipo.
- Lista explícita de padrões procedimentais (requerimento de urgência, adiamento, retirada de pauta, encerramento de discussão, preferência, destaque etc.).
- Padrão: `merito` quando incerto.

**Tarefa 2.3 — Modelos** (`modelos.py`) — testes primeiro
- Funções puras: resposta da API (ou linha do arquivo anual) → formato do spec (índice, detalhe da votação, deputado).
- Campo ausente: valor `null` + aviso no log, sem quebrar.

**Tarefa 2.4 — Armazenamento** (`armazenamento.py`) — testes primeiro
- Grava JSON ordenado e com indentação estável (diffs limpos no git).
- Nunca apaga; atualiza só se conteúdo mudou.
- Mantém `estado-coleta.json` (última data, votações sem votos pendentes).
- Teste: rodar gravação duas vezes não altera arquivos.

**Tarefa 2.5 — Ponto de entrada** (`coletar.py`)
- `--inicial`: desde 01/02/2023, usando fonte decidida na Fase 1.
- `--incremental`: desde última data do estado + reprocesso das pendentes.
- `--deputados`: atualiza `deputados.json` e `deputados/<id>.json` (projetos apresentados).
- Gera `deputados/<id>.json` com histórico de votos a partir das votações salvas.

**Tarefa 2.6 — Carga inicial**
- Workflow manual roda `--inicial` e faz commit de `dados/`.
- Conferir: total de votações por ano plausível, 513 deputados em exercício, amostra de 3 votações comparada à página oficial.

Pronto quando: `dados/` completo desde fev/2023 no repositório; testes passando.

## Fase 3 — Site: páginas de dados

**Tarefa 3.1 — Projeto Astro** em `site/`, lendo `../dados/` em tempo de build; layout base, cabeçalho, navegação, rodapé com fonte dos dados.

**Tarefa 3.2 — `/votacoes`**
- Lista paginada (ex.: 50 por página), etiqueta mérito/procedimental, link "ver votação" em todos os itens.
- Filtros e busca no navegador sobre `indice.json` (JS leve).

**Tarefa 3.3 — `/votacao/[id]`**
- Cabeçalho, totais, gráfico de barras empilhadas por partido, orientações, tabela de votos com busca/filtro, link oficial, aviso quando sem votos.

**Tarefa 3.4 — `/deputados`** — busca, filtro por partido e UF.

**Tarefa 3.5 — `/deputado/[id]`** — foto, dados, histórico de votos, projetos apresentados.

**Tarefa 3.6 — Verificação**
- Build sem erros; checagem de links internos; abrir páginas em navegador e conferir 3 votações contra o site da Câmara.
- **Ponto de parada:** Stella navega na prévia e aprova.

## Fase 4 — Página inicial

**Tarefa 4.1 — Conteúdo**: textos de "Como o site funciona", "Política no Brasil", "Câmara", "Senado". Fatos institucionais checados em fonte oficial (Constituição, sites da Câmara e do Senado).
- **Ponto de parada:** Stella revisa textos.

**Tarefa 4.2 — Direção de arte** com a skill `design-taste-frontend`: proposta visual, paleta, tipografia, efeitos (entrada animada, contadores, transições na rolagem, linha do tempo do processo legislativo). Respeitar `prefers-reduced-motion`.
- **Ponto de parada:** Stella escolhe direção.

**Tarefa 4.3 — Implementação** + revisão visual por screenshot (desktop e celular).

## Fase 5 — Resumo diário por e-mail

**Tarefa 5.1 — `montar.py`** — testes primeiro: dia com votações, dia sem votação (retorna nada), ordenação mérito antes de procedimental, links corretos.

**Tarefa 5.2 — `enviar.py`** — SMTP Gmail com secrets; nenhuma credencial no código.

**Tarefa 5.3 — `email.yml`** — cron `0 0 * * *` (00:00 UTC = 21h BRT) + disparo manual para teste.
- Teste real: disparo manual com data de um dia com votações.

## Fase 6 — Automação e publicação

**Tarefa 6.1 — `testes.yml`**: pytest + build do site em todo push.

**Tarefa 6.2 — `coleta.yml`**: cron de hora em hora, `--incremental`, commit só se `dados/` mudou.

**Tarefa 6.3 — `deputados.yml`**: diário, `--deputados`.

**Tarefa 6.4 — `publicar.yml`**: build Astro + deploy GitHub Pages após commit em `dados/` ou `site/`; build com falha não publica.

**Tarefa 6.5 — README**: o que é, como rodar local, como funciona a automação, onde estão os secrets.

**Tarefa 6.6 — Verificação final**
- Acompanhar 24h de execuções automáticas; conferir uma votação nova aparecendo no site e no e-mail.

## Backlog pós-v1

1. **Página do partido** (prioridade alta)
2. Senado Federal
3. Proposições e tramitação
4. Abertura ao público
