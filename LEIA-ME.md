# EconoIA Brasil

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
