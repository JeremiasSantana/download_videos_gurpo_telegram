import datetime
import logging

from uteis.funcoes.registro import (
    ManipuladorArquivoDiario,
    configurar_logs,
)


def _registro_de_log(mensagem):
    return logging.LogRecord(
        name="baixador_telegram", level=logging.INFO, pathname=__file__,
        lineno=1, msg=mensagem, args=(), exc_info=None,
    )


def test_arquivo_diario_por_data(tmp_path):
    manipulador = ManipuladorArquivoDiario(tmp_path)
    manipulador.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    manipulador._hoje = lambda: datetime.date(2026, 10, 26)
    manipulador.emit(_registro_de_log("primeiro dia"))

    manipulador._hoje = lambda: datetime.date(2026, 10, 27)
    manipulador.emit(_registro_de_log("segundo dia"))
    manipulador.close()

    dia1 = tmp_path / "2026-10-26" / "app.log"
    dia2 = tmp_path / "2026-10-27" / "app.log"
    assert "primeiro dia" in dia1.read_text(encoding="utf-8")
    assert "segundo dia" not in dia1.read_text(encoding="utf-8")
    assert "segundo dia" in dia2.read_text(encoding="utf-8")


def test_configurar_logs_nao_duplica_handlers(tmp_path):
    logger = configurar_logs(tmp_path)
    quantidade = len(logger.handlers)

    logger2 = configurar_logs(tmp_path)
    assert logger2 is logger
    assert len(logger2.handlers) == quantidade
