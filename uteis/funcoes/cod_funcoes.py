"""Ponto de entrada do baixador de vídeos do Telegram.

Execute com:

    python uteis/funcoes/cod_funcoes.py [--destino X] [--limite N]
                                       [--pasta CAMINHO] ...

A lógica fica nos módulos do pacote ``uteis.funcoes``:

- ``configuracao``: credenciais e padrões vindos do ``.env``.
- ``destinos``: resolução e classificação do destino (grupo comum,
  grupo com tópicos, canal, conversa privada).
- ``topicos``: descoberta e identificação de tópicos de fórum.
- ``baixador``: o motor de download (sem dependência do terminal).
- ``arquivos``: pastas, nomes, duplicidade e registro de downloads.
- ``terminal``: perguntas e seleções no terminal.
- ``registro``: logs diários em ``logs/<data>/app.log``.
- ``app``: orquestração de tudo isso.
"""

import pathlib
import sys

# Permite executar este arquivo diretamente (python uteis/funcoes/
# cod_funcoes.py) enxergando o pacote ``uteis`` da raiz do projeto.
_RAIZ = pathlib.Path(__file__).resolve().parents[2]

if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from uteis.funcoes.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
