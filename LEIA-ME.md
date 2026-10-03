# EconoIA Brasil · JesseCorp 2026

Site de economia brasileira que se atualiza sozinho. Tudo é configurado pelo navegador, sem instalar nada.

## O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `index.html` | O site |
| `data/data.json` | Os dados que o site mostra. O robô reescreve esse arquivo a cada 30 minutos |
| `data/local.json` | Cópia de reserva, usada se o `data.json` falhar |
| `scripts/update.py` | O robô: busca Selic, IPCA e câmbio PTAX no Banco Central, IGP-M (FGV, via BC), desemprego e PIB no IBGE (SIDRA) e cotações da bolsa (Yahoo Finance) |
| `.github/workflows/update.yml` | Diz ao GitHub para rodar o robô a cada 30 minutos, de graça |
| `netlify/functions/chat.mjs` | Liga o chat ao Gemini, com a chave escondida no servidor |
| `netlify.toml` | Configuração do Netlify |

## Passo a passo

### 1. GitHub: guardar o projeto e ligar o robô
1. Crie uma conta em **github.com**.
2. Clique em **New repository**. Dê o nome `econoia`, marque **Public** e clique em **Create repository**.
3. Clique em **uploading an existing file**. Arraste **tudo** o que está dentro da pasta `econoia-site`.
   - A pasta `.github` fica escondida no Finder do Mac. Para ela aparecer, aperte **Cmd + Shift + .** (ponto). Arraste ela também.
4. Clique em **Commit changes**.
5. Vá em **Settings → Actions → General**. Em *Workflow permissions*, marque **Read and write permissions** e salve.
6. Vá na aba **Actions**, entre em **Atualizar dados da EconoIA**, clique em **Run workflow** e confirme no **Run workflow** verde.
   - Em cerca de 1 minuto aparece um ✅. Clique no robô para ver o relatório: cada fonte aparece como `OK` ou `FALHA`.

### 2. Chave grátis do Gemini (para o chat)
1. Entre em **aistudio.google.com** com sua conta Google.
2. Clique em **Get API key → Create API key** e copie a chave. Não mostre essa chave para ninguém.

### 3. Netlify: colocar o site no ar
1. Abra o arquivo `netlify.toml` no GitHub, clique no lápis ✏️ e troque `SEU_USUARIO` pelo seu nome de usuário do GitHub. Clique em **Commit changes**.
2. Entre em **app.netlify.com** e escolha **Add new project → Import an existing project → GitHub**. Autorize e escolha o repositório `econoia`. Clique em **Deploy**, sem mudar nada.
3. Vá em **Project configuration → Environment variables → Add a variable**:
   - Key: `GEMINI_API_KEY`
   - Value: cole a chave do Gemini.
4. Vá em **Deploys → Trigger deploy → Deploy project**, para o chat pegar a chave.
5. Vá em **Project configuration → Change project name**, digite `econoia` (ou outro nome livre) e salve.

Pronto. O site fica em `https://econoia.netlify.app`.

## Como funciona depois de pronto
- A cada 30 minutos, o GitHub roda o robô e salva os dados novos. O site busca esses dados sozinho, e quem estiver com a página aberta vê a atualização em até 5 minutos.
- O chat usa o Gemini, que é gratuito até um limite diário. Se o modelo `gemini-3.8-flash` deixar de existir, crie no Netlify a variável `GEMINI_MODEL` com o nome do modelo novo.
- Se uma fonte falhar, o site mantém o último valor bom.
- O GitHub pode atrasar o robô alguns minutos quando está sobrecarregado. Isso é normal.

## Domínio próprio (opcional)
Depois de comprar um domínio, por exemplo `econoia.com.br` no registro.br: no Netlify, vá em **Domain management → Add a domain** e siga as instruções de DNS.
