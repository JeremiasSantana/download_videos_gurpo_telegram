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
4. **Vídeos baixados** — lista dos arquivos da pasta, com link para
   baixar/abrir pelo navegador.

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
