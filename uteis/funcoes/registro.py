"""Configuração de logs do programa.

Estrutura de arquivos, um por dia (a data é a do dia em que o registro
é gravado — se a execução atravessar a meia-noite, os registros novos
vão automaticamente para a pasta do novo dia):

    logs/
    ├── 2026-10-26/
    │   └── app.log
    └── 2026-10-27/
        └── app.log

Níveis: DEBUG (detalhes técnicos, só no arquivo), INFO (andamento e
resultados), WARNING (situações contornáveis, como arquivo já
existente), ERROR (falha numa operação específica) e CRITICAL (erro
que impede o programa de continuar).

Nunca registre credenciais, códigos de login ou conteúdo de sessão.
"""

import datetime
import logging
import pathlib
import sys

NOME_LOGGER = "baixador_telegram"

_FORMATO_ARQUIVO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FORMATO_CONSOLE = "%(message)s"


class ManipuladorArquivoDiario(logging.Handler):
    """Grava em ``<pasta>/<AAAA-MM-DD>/app.log``, trocando na virada do dia."""

    def __init__(self, pasta_logs: pathlib.Path):
        super().__init__(level=logging.DEBUG)
        self.pasta_logs = pathlib.Path(pasta_logs)
        self._fluxo = None
        self._data_atual = None

    def _hoje(self):
        """Data atual (método separado para facilitar testes)."""
        return datetime.date.today()

    def _caminho_do_dia(self, data):
        return self.pasta_logs / data.strftime("%Y-%m-%d") / "app.log"

    def _garantir_fluxo(self):
        hoje = self._hoje()

        if self._fluxo is not None and hoje == self._data_atual:
            return

        self._fechar_fluxo()
        caminho = self._caminho_do_dia(hoje)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._fluxo = caminho.open("a", encoding="utf-8")
        self._data_atual = hoje

    def _fechar_fluxo(self):
        if self._fluxo is not None:
            try:
                self._fluxo.close()
            except OSError:
                pass
            self._fluxo = None
            self._data_atual = None

    def emit(self, record):
        try:
            self._garantir_fluxo()
            self._fluxo.write(self.format(record) + "\n")
            self._fluxo.flush()
        except Exception:  # log nunca pode derrubar o programa
            self.handleError(record)

    def close(self):
        self._fechar_fluxo()
        super().close()


def configurar_logs(pasta_logs: pathlib.Path) -> logging.Logger:
    """Configura (uma única vez) e devolve o logger principal."""
    logger = logging.getLogger(NOME_LOGGER)

    if getattr(logger, "_baixador_configurado", False):
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formato_arquivo = logging.Formatter(
        _FORMATO_ARQUIVO, datefmt="%Y-%m-%d %H:%M:%S"
    )

    manipulador_arquivo = ManipuladorArquivoDiario(pathlib.Path(pasta_logs))
    manipulador_arquivo.setFormatter(formato_arquivo)
    logger.addHandler(manipulador_arquivo)

    manipulador_console = logging.StreamHandler(sys.stdout)
    manipulador_console.setLevel(logging.INFO)
    manipulador_console.setFormatter(logging.Formatter(_FORMATO_CONSOLE))
    logger.addHandler(manipulador_console)

    logger._baixador_configurado = True
    return logger


def obter_logger() -> logging.Logger:
    """Devolve o logger principal (configurar antes com configurar_logs)."""
    return logging.getLogger(NOME_LOGGER)
