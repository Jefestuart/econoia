# Acessibilidade do EconoIA Brasil

Meta: WCAG 2.1 nível AA. Esta página registra o que foi verificado, o que foi corrigido e o que ainda falta.

## Como foi verificado (6 de outubro de 2026)
- **axe-core** (regras WCAG 2.0/2.1 A e AA e boas práticas) em navegador real (Chromium), em **19 visões** (início, cada ferramenta, cada aba, páginas institucionais), nos **temas escuro e claro**. Sem violações de WCAG A/AA depois das correções abaixo.
- Contraste calculado à mão para todas as cores do tema (texto sobre fundo, fundo suave e dados em vermelho/verde/dourado).
- Navegação por teclado das abas testada (setas, Home, End).

## O que foi corrigido
- **Contraste no tema claro:** o azul, o dourado e o vermelho de destaque ficavam abaixo de 4,5:1 em textos pequenos; foram escurecidos. Textos sobre fundo de destaque passaram a usar branco no tema claro (`--on-accent`). Altas/quedas verdes e vermelhas nas tabelas e o logotipo do rodapé também foram ajustados.
- **Estrutura:** área principal (`<main>`), barra de topo como `banner`, faixas de cotações e atalhos como regiões nomeadas, e link "Pular para o conteúdo".
- **Abas:** `aria-controls`, `role="tabpanel"` e navegação por setas, Home e End.
- **Títulos:** o modo de seção única sempre tem um título de nível 1 (escondido visualmente quando a seção já tem o próprio título).
- **Campos de código editáveis** agora são anunciados como caixas de texto; cabeçalho vazio da tabela de Granger ganhou texto para leitores de tela; seis gráficos principais ganharam descrição.
- Foco visível também em links.

## O que ainda falta (limites conhecidos)
- **Ordem dos títulos** (boa prática, não é critério A/AA): em algumas seções o título salta de nível 1 para 3 e o rodapé usa nível 4. Corrigir exige reorganizar muitos blocos.
- **Gráficos** são imagens em canvas: os seis principais têm descrição curta, mas não têm tabela de dados alternativa nem descrição dos valores. As abas "Tabelas" e "Prever o futuro" trazem os números em texto, o que ajuda, mas não substitui. Os gráficos das lições de LaTeX/séries não têm descrição própria.
- **Planilha** (jspreadsheet, biblioteca de terceiros) e o **Laboratório R** (WebR) não foram auditados por dentro.
- **Não houve teste manual com leitor de tela** (NVDA, VoiceOver) nem com ampliação de 200%. A auditoria automática encontra só parte dos problemas; a conformidade total exige esse teste.
- Cores dos gráficos (Chart.js) não foram verificadas por contraste.

Para reportar uma barreira de acesso: contato@econoia.com.br.
