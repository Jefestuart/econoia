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
- A pasta `netlify/` e o `netlify.toml` são da hospedagem antiga e podem ser apagados depois da migração. **Atenção:** apagar os arquivos aqui não desliga o que já está publicado no Netlify. A função antiga de lá (`/api/chat` em `econoia-br.netlify.app`) não tem as proteções do chat novo. Apague o site no Netlify, ou ao menos a variável `GEMINI_API_KEY` de lá.

## Como o chat é protegido (`functions/api/chat.js`)
- **As regras da IA ficam no servidor** (`functions/_lib/instrucoes.js`). O navegador só manda a pergunta, os dados de referência (tratados como texto, não como ordem) e, no LaTeX, o nome da tarefa. Ninguém consegue trocar as instruções para usar a chave do Gemini como IA genérica.
- **Respostas assinadas** (`functions/_lib/assinatura.js`, HMAC-SHA256): cada resposta sai com uma assinatura, e o servidor descarta qualquer resposta "da IA" no histórico que ele não escreveu. A chave de assinatura é derivada da `GEMINI_API_KEY`, sem segredo novo.
- **Limites:** só aceita pedidos vindos do próprio site, até 8 perguntas por minuto e 120 por dia por IP (`functions/_lib/protecao.js`), pedido de até 100 mil caracteres, histórico de até 12 mensagens, resposta de até 1.200 tokens.
- **Erros técnicos não vão para o navegador**; ficam só nos logs do Cloudflare (`console.error`).
- **Cache:** a primeira pergunta de uma conversa, se repetida, é respondida do cache por 10 minutos, sem gastar a cota do Gemini.
- **Ferramentas de leitura** (`functions/_lib/ferramentas.js`): a IA pode consultar `data/series.json` e `data/modelos.json` (séries do catálogo, previsões SARIMA/VAR). Só lê arquivos fixos deste repositório e só ids do catálogo; no máximo 3 rodadas por pergunta. Se o Gemini recusar as ferramentas, o chat responde sem elas.
- Os limites por IP usam o cache de cada data center do Cloudflare, então são uma barreira contra abuso, não uma contagem exata. Para um limite firme, crie uma regra em **Security → WAF → Rate limiting rules** para `/api/chat`.

## Modelos econométricos (aba "VAR e SARIMA")
`scripts/modelos.py` roda todo dia no GitHub Actions, com numpy e scipy:
- **SARIMA(p,0,q)(P,0,Q)12** para IPCA e IGP-M, estimado por soma condicional de quadrados, ordens pelo AIC;
- **VAR** com dólar, IGP-M, IPCA e Selic (MQO, defasagens pelo AIC), com impulso-resposta (Cholesky, faixa de 90% por bootstrap) e causalidade de Granger (teste F);
- intervalos de previsão por bootstrap dos resíduos e **backtest** de origem móvel (48 previsões fora da amostra, janela de 15 anos) contra previsões ingênuas. O modelo com menor erro ganha o selo de melhor histórico e aparece no cartão da página inicial.

Resultado em `data/modelos.json`. Testes com dados simulados em `tests/test_modelos.py`.

## Testes
- `npm test`: chat (proteção e limites), notícias e entrega de dados
- `python -m unittest discover -s tests -p "test_*.py"`: SARIMA, VAR, impulso-resposta, Granger e backtest

## Catálogo de indicadores e "Prever o futuro"
`scripts/series.py` baixa cerca de 40 séries mensais (Banco Central/SGS e FRED) desde 2003 e, para cada uma, mede a sazonalidade (efeito médio de cada mês e teste F) e faz uma previsão SARIMA de 12 meses com faixa de 80%. O resultado (`data/series.json`) alimenta o módulo **Prever o futuro** da página inicial, que também gera o código equivalente em **R** e **Python**, executável no navegador (WebR e Pyodide). Testes em `tests/test_series.py`.

## Aprenda LaTeX
Área com quatro ferramentas (montador de fórmulas por cliques ou por descrição em português, tabela do Excel → LaTeX, tradutor de erros do LaTeX para o português e gerador de trabalho ABNT com abnTeX2) e seis lições com prévia ao vivo (KaTeX). Tudo abre no Overleaf com um clique. Os resultados de **Prever o futuro**, **VAR e SARIMA** e do **Laboratório R** têm botão **Copiar em LaTeX**. Os códigos gerados foram compilados com pdflatex.
