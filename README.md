# Monitor do Congresso

Site para acompanhar votações da Câmara dos Deputados: placar por partido, voto de cada deputado, histórico por parlamentar e (em breve) resumo diário por e-mail. Dados oficiais de [dadosabertos.camara.leg.br](https://dadosabertos.camara.leg.br).

- Design: `docs/superpowers/specs/2026-10-28-monitor-congresso-design.md`
- Plano: `docs/superpowers/plans/2026-10-29-monitor-congresso-v1-plano.md`

## Estrutura

| Pasta | O que tem |
|---|---|
| `coletor/` | Python: baixa dados da Câmara e grava em `dados/` |
| `dados/` | JSON gerado pelo coletor (não editar à mão) |
| `site/` | Site em Astro, lê `dados/` e gera páginas estáticas |
| `tests/` | Testes do coletor (`python -m pytest`) |
| `.github/workflows/` | Automação no GitHub Actions |

## Workflows

| Workflow | Quando roda | O que faz |
|---|---|---|
| Testes | todo push | roda os testes do coletor |
| Carga inicial de dados | manual | baixa votações desde 01/02/2023 e deputados |
| Atualizar deputados | todo dia 02:17 e manual | perfis, projetos e situação de cada projeto; depois publica o site |
| Publicar site | push em `site/`, `dados/` ou `coletor/`, ou manual | gera o site e publica no GitHub Pages |
| Spike | manual | teste de disponibilidade de dados (Fase 1) |

## Rodar o site no próprio computador

Precisa de Node.js 22.

```
cd site
npm install
npm run dev
```

Abre em http://localhost:4321/monitor-congresso/
