# Monitor do Congresso — Design (v1)

Data: 2026-10-28
Status: aprovado em brainstorming, aguardando revisão do spec

## 1. Objetivo

Site para acompanhar a atividade legislativa brasileira de forma organizada: ver cada votação nominal, o placar por partido, o voto de cada parlamentar e o histórico de cada um, com um resumo diário por e-mail. A página inicial também explica, de forma didática, como funciona a política no Brasil, a Câmara e o Senado.

Uso inicial pessoal; a arquitetura deve permitir abrir ao público depois sem reescrita.

## 2. Escopo

### Dentro da v1
- Somente **Câmara dos Deputados**.
- Dados desde o início da legislatura atual (**01/02/2023**) em diante.
- Telas: página inicial, lista de votações, página da votação, lista de deputados, página do deputado.
- Resumo diário por e-mail, enviado só para a dona do projeto.

### Fora da v1 (backlog, em ordem de prioridade)
1. **Página do partido** — como a bancada votou ao longo do tempo. Prioridade alta, pedida explicitamente.
2. Senado Federal (coleta + telas equivalentes).
3. Navegação de proposições (andamento/tramitação de projetos).
4. Abertura ao público (domínio próprio, e-mail para outros destinatários).

### Princípio de neutralidade
O site mostra **somente fatos** publicados pela Câmara: partido, estado, votos, orientações de bancada, projetos apresentados. Não há rótulos ideológicos, notas, rankings ou índices calculados sobre parlamentares ou partidos. Textos explicativos descrevem regras institucionais, sem opinião.

## 3. Arquitetura

```
API e arquivos de dados abertos da Câmara
        │
        ▼
coletor/ (Python, roda no GitHub Actions)
   • carga inicial: desde 01/02/2023 (executada uma vez)
   • incremental: de hora em hora
        │
        ▼
dados/ (JSON versionado no repositório)
        │
        ├──▶ site/ (Astro) → build estático → GitHub Pages
        └──▶ email/ (Python, diário às 21h BRT) → Gmail
```

Custo zero: GitHub (repositório, Actions, Pages) e Gmail.

### Unidades e responsabilidades

| Unidade | Faz | Depende de | Não faz |
|---|---|---|---|
| `coletor/` | Busca dados na Câmara e grava JSON em `dados/` | API/arquivos da Câmara | Não gera HTML, não envia e-mail |
| `coletor/classificador.py` | Marca cada votação como `merito` ou `procedimental` | Campos da votação | Não acessa rede |
| `site/` | Lê `dados/` e gera páginas estáticas | `dados/` | Não chama a API |
| `email/` | Monta e envia resumo do dia | `dados/votacoes/indice.json`, secret do Gmail | Não altera `dados/` |

### Estrutura de dados (`dados/`)

```
dados/
├── deputados.json                 # todos os deputados da legislatura: id, nome, partido, UF, foto
├── deputados/<id>.json            # projetos apresentados (histórico de votos é calculado no build do site)
├── votacoes/indice.json           # lista resumida de todas as votações
├── votacoes/<id>.json             # detalhe de uma votação
└── estado-coleta.json             # última data coletada, votações pendentes de votos
```

Campos mínimos de `votacoes/indice.json` (por item): `id`, `data`, `proposicao` (sigla/número/ano), `descricao`, `resultado`, `tipo` (`merito`|`procedimental`), `votos_disponiveis` (bool).

Campos mínimos de `votacoes/<id>.json`: os do índice + `totais` (contagem por tipo de voto: Sim, Não, Abstenção, Obstrução, Artigo 17), `orientacoes` (lista: sigla, tipo de liderança, orientação), `votos` (lista `[deputado_id, partido, UF, voto]`, com partido e UF na data do voto), `url_api`; `proposicao.url` aponta para a ficha oficial na Câmara. Esquema detalhado em `coletor/modelos.py`.

Ajustes feitos na Fase 2:
- Só votações **nominais do Plenário** entram (as simbólicas não têm voto individual).
- "Ausentes" saiu dos totais: os dados não dizem quem estava em exercício e não votou.
- Histórico de votos do deputado não é gravado em arquivo próprio; o site calcula a partir das votações (evita duplicar ~60 MB no repositório).

## 4. Coleta de dados

- **Carga inicial:** baixa votações, votos e orientações desde 01/02/2023, preferindo os arquivos anuais de download em massa da Câmara quando existirem (menos requisições).
- **Incremental (de hora em hora):** consulta votações a partir da última data em `estado-coleta.json`; grava novas; tenta de novo as votações marcadas como sem votos individuais.
- **Deputados:** atualiza `deputados.json` uma vez por dia (mudanças de partido, suplentes).
- **Idempotência:** rodar duas vezes seguidas não duplica nem altera dados.
- **Nunca apaga** dado já salvo; só adiciona ou atualiza.
- **Commit automático:** se `dados/` mudou, o Action faz commit, o que dispara o build do site.

### Decisão após o spike (2026-10-29)
O spike (Fase 1) não confirmou o problema relatado: a API v2 e os arquivos anuais trazem votos individuais e orientações de fev/2023 a out/2026, e coincidem nas amostras. Fontes adotadas:
- **Carga inicial:** arquivos anuais (`votacoes`, `votacoesVotos`, `votacoesOrientacoes`).
- **Incremental de hora em hora:** API v2.
- **Reconciliação diária:** comparar com o arquivo anual do ano corrente e completar o que faltar.

A queda de votações nominais em jul–out/2026 deve ser conferida contra o site da Câmara na carga inicial (hipótese: ano eleitoral).

### Risco conhecido (histórico)
Há relato de terceiros de que o endpoint de votos individuais por votação da API v2 devolve lista vazia para votações posteriores a maio de 2024. **Primeira tarefa da implementação:** teste de disponibilidade (spike) comparando API v2 e arquivos de download em massa para votações de 2023, 2024, 2025 e 2026. A fonte de votos individuais é decidida com base nesse resultado. Se nenhuma fonte trouxer votos recentes, a v1 segue mostrando totais e orientações, com aviso na página.

## 5. Classificação mérito × procedimental

- `procedimental`: votações cuja proposição ou descrição indica requerimento (urgência, adiamento, retirada de pauta, encerramento de discussão, destaque de preferência etc.).
- `merito`: todo o resto.
- Em caso de dúvida: `merito` (não esconder nada importante).
- Regras em lista explícita no código, cobertas por testes com exemplos reais.

## 6. Telas

### Página inicial `/`
- Abertura visual com efeitos: animação de entrada, contadores animados (deputados em exercício, total de votações desde 2023), transições ao rolar. Direção de arte definida na fase de construção.
- **Como o site funciona:** fonte dos dados, frequência de atualização, o que cada tela mostra, resumo por e-mail.
- **Como funciona a política no Brasil:** três Poderes; papel do Legislativo; caminho de um projeto até virar lei (linha do tempo animada).
- **Câmara dos Deputados:** 513 deputados; representam a população; eleição proporcional; mandato de 4 anos; funções (legislar, fiscalizar o Executivo, votar o orçamento).
- **Senado Federal:** 81 senadores, 3 por estado; representam os estados; eleição majoritária; mandato de 8 anos; funções. Aviso: dados do Senado chegam em versão futura.
- Atalho para as votações mais recentes.

### Lista de votações `/votacoes`
- Ordem: mais recente primeiro; paginada.
- Cada item: data, proposição, descrição curta, resultado, etiqueta `mérito`/`procedimental`, link **"ver votação"** (para todas, inclusive procedimentais).
- Filtros: período, esconder procedimentais, busca por texto.

### Página da votação `/votacao/<id>`
- Cabeçalho: proposição, o que estava em votação, data, resultado, totais.
- Gráfico de barras empilhadas: votos por partido.
- Orientação de cada partido.
- Tabela de voto individual: nome (link para página do deputado), partido, UF, voto; busca e filtro por partido/UF.
- Link para a página oficial da Câmara.
- Sem votos individuais disponíveis: totais + aviso "votos individuais ainda não publicados pela Câmara".

### Lista de deputados `/deputados`
- Busca por nome; filtro por partido e UF; link para a página de cada um.

### Página do deputado `/deputado/<id>`
- Foto oficial, nome, partido, UF.
- Histórico de votos: data, votação (link), voto dado.
- Projetos apresentados, com link oficial.
- Somente fatos.

## 7. Resumo diário por e-mail

- Agendamento: todo dia às 21h (BRT), via GitHub Actions.
- Dia sem votação: não envia.
- Conteúdo: votações do dia; mérito primeiro, procedimentais agrupadas ao final; cada item com resultado e link para a página da votação.
- Envio: Gmail com senha de app guardada como secret do GitHub. Nunca no código.
- Destinatário v1: apenas a dona do projeto.

## 8. Tratamento de erros

- Falha de rede ou HTTP 429: até 3 novas tentativas com espera crescente; se persistir, encerra sem alterar `dados/` e tenta na próxima execução.
- Execução com falha: notificação automática do GitHub por e-mail.
- Build do site com falha: não publica; versão anterior continua no ar.
- Dado inesperado (campo ausente): registra no log e segue com as demais votações.

## 9. Testes

- `coletor/` e `classificador`: testes automáticos (pytest) com respostas reais da Câmara salvas em arquivo, sem internet.
- `site/`: build completo a cada mudança; checagem de links internos quebrados.
- `email/`: teste do montador da mensagem com dados de exemplo (sem envio real).

## 10. Stack

- Python 3 (coletor, e-mail)
- Astro (site estático), Node.js
- GitHub Actions, GitHub Pages
- Gmail (SMTP com senha de app)

## 11. Ordem sugerida de implementação

1. Spike de disponibilidade de dados (seção 4).
2. Coletor + classificador + carga inicial.
3. Site: páginas de dados (votações, votação, deputados, deputado).
4. Página inicial com conteúdo e efeitos.
5. Resumo diário por e-mail.
6. Automação completa no GitHub Actions + publicação no Pages.
7. Backlog: página do partido.
