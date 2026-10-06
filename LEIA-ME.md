# EconoIA Brasil

![Testes](https://github.com/Jefestuart/econoia/actions/workflows/testes.yml/badge.svg)

Laboratório de Economia, Dados e IA do Brasil — https://econoia.com.br

## Como funciona
| Parte | Onde fica |
|---|---|
| Site (`index.html`, app PWA) | Cloudflare Pages, publicado sozinho a cada mudança no ramo `main` |
| Chat (`functions/api/chat.js`) | Função do Cloudflare que chama o Gemini. A chave fica no Cloudflare em **Settings → Variables and Secrets** (`GEMINI_API_KEY`, tipo Secret) |
| Notícias (`functions/api/news.js`) | RSS do InfoMoney, G1 e Agência Brasil, só títulos e links |
| Dados (`data/data.json`) | Robô `scripts/update.py` no GitHub Actions, a cada 30 min. O site lê o arquivo direto do GitHub (`functions/data/data.json.js`) |

## Observações
- Os commits do robô levam `[skip ci]`, para não republicar o site a cada atualização de dados (o plano grátis do Cloudflare tem 500 publicações por mês).
- Se o modelo do Gemini sair do ar, crie no Cloudflare a variável `GEMINI_MODEL` com o nome do modelo novo.
- Se uma fonte de dados falhar, o site mantém o último valor bom.
- A pasta `netlify/` e o `netlify.toml` são da hospedagem antiga e podem ser apagados depois da migração.

## Modelos econométricos
`scripts/modelos.py` estima, todo dia, um AR(p) com sazonalidade mensal para IPCA e IGP-M (amostra desde 2003, ordem por AIC, MQO só com numpy), prevê 12 meses com intervalos por bootstrap dos resíduos e faz um backtest de origem móvel (48 previsões fora da amostra) contra previsões ingênuas. Resultado em `data/modelos.json`, exibido na aba **Previsões**. Testes em `tests/test_modelos.py`.

## Testes
- `npm test`: chat (proteção e limites), notícias e entrega de dados
- `python -m unittest discover -s tests -p "test_*.py"`: motor econométrico
