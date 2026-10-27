# Versão web — Baixador de Vídeos do Telegram

Páginas web (HTML/CSS/JS) + backend Python com **FastAPI**, reaproveitando
o motor do projeto (`uteis/funcoes`) sem nenhuma alteração nele.

## Como rodar (na raiz do projeto)

Com Poetry:

```bash
poetry add fastapi "uvicorn[standard]"   # só na primeira vez
poetry run uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Sem Poetry:

```bash
pip install -r web/requirements.txt
uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Depois abra <http://127.0.0.1:8000> no navegador.

Pré-requisito: o arquivo `.env` da raiz preenchido com `ID_API` e
`API_HASH` (o mesmo do uso pelo terminal).

## Fluxo na página

1. **Login no Telegram** — telefone → código recebido no Telegram →
   senha, se a conta tiver verificação em duas etapas.
2. **Escolher o que baixar** — destino por título/@/link/ID ou pela
   lista dos seus destinos; se for grupo com tópicos, escolher o
   tópico; limite de mensagens analisadas; pasta de destino.
3. **Progresso** — log ao vivo do motor e resumo final
   (analisadas/baixados/pulados/erros).
4. **Histórico de vídeos baixados** — agrupado por local de origem
   (canal, grupo ou conversa), a partir do registro `.baixados.json`.
   Clicando num local, aparecem os vídeos baixados dele. Para cada
   local dá para **excluir o histórico** (apaga só o registro daquele
   local; os vídeos continuam na pasta, mas podem ser baixados de
   novo no futuro) ou **ocultar** (o histórico fica embaçado, a
   escolha fica salva no navegador).

## Aparência

- Botão **sol/lua** no canto superior direito alterna entre modo
  escuro (fundo preto em degradê) e modo claro (branco com azul em
  degradê); a escolha fica salva no navegador.
- Fundo animado com traços de rede neural se movendo e logos de
  tecnologia flutuando (Python, Git, GitHub, Telegram, JS, HTML,
  CSS, FastAPI, Linux, Docker), no espírito do papel de parede do
  WhatsApp.
- Botões com bordas bem arredondadas.

## Pontos de atenção

- **Uso local e pessoal na v1.** Rode com `--host 127.0.0.1`. A sessão
  do Telegram fica no servidor e vale como senha da conta: expor a
  página na rede/internet sem uma senha de acesso permitiria a outra
  pessoa usar a sua conta.
- O arquivo de sessão `*.session` é criado na pasta de onde o servidor
  é iniciado (rode da raiz do projeto) e já está no `.gitignore`.
- Um download por vez: enquanto um está rodando, outro é recusado.
- Os vídeos ficam no disco do servidor, na mesma estrutura do terminal:
  `<pasta>/<destino>/<tópico>/`, com o mesmo registro `.baixados.json`
  (o que o terminal já baixou não é baixado de novo, e vice-versa).

## Estrutura

- `app.py` — backend FastAPI (API `/api/...` + páginas estáticas).
- `static/` — `index.html`, `style.css`, `app.js` (sem framework JS).
- `requirements.txt` — dependências só da web (alternativa ao Poetry).
