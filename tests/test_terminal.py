import pathlib

import pytest

from uteis.funcoes.destinos import Destino, TipoDestino
from uteis.funcoes.terminal import (
    InterfaceTerminal,
    interpretar_escolha,
    interpretar_limite,
)


def test_interpretar_limite():
    assert interpretar_limite("") is None
    assert interpretar_limite("   ") is None
    assert interpretar_limite("250") == 250

    for invalido in ("abc", "0", "-5", "3.5", "10 vídeos"):
        with pytest.raises(ValueError):
            interpretar_limite(invalido)


def test_interpretar_escolha():
    assert interpretar_escolha("1", 3) == 0
    assert interpretar_escolha("3", 3) == 2

    for invalido in ("0", "4", "x", ""):
        with pytest.raises(ValueError):
            interpretar_escolha(invalido, 3)


class InterfaceFalsa(InterfaceTerminal):
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.mensagens = []
        super().__init__(ler=self._ler, mostrar=self.mensagens.append)

    def _ler(self, prompt=""):
        return self.respostas.pop(0)


def test_escolher_limite_com_erro_e_correcao():
    interface = InterfaceFalsa(["abc", "25"])
    assert interface.escolher_limite() == 25
    assert any("número inteiro" in m for m in interface.mensagens)


def test_escolher_limite_vazio_usa_padrao():
    interface = InterfaceFalsa([""])
    assert interface.escolher_limite(padrao=100) == 100

    interface = InterfaceFalsa([""])
    assert interface.escolher_limite() is None


def test_escolher_pasta_cria_e_depois_do_erro(tmp_path):
    arquivo = tmp_path / "ocupa.txt"
    arquivo.write_text("x")
    destino = tmp_path / "nova-pasta"

    interface = InterfaceFalsa([str(arquivo), str(destino)])
    resultado = interface.escolher_pasta(padrao=tmp_path)

    assert resultado == destino
    assert destino.is_dir()
    assert any("pasta" in m for m in interface.mensagens)


def test_escolher_topico_por_nome_numero_e_todos():
    destino = Destino(
        entidade=None, tipo=TipoDestino.GRUPO_TOPICOS,
        titulo="Grupo", id_destino=1,
    )
    topicos = {1: "Geral", 100: "Aulas"}

    assert InterfaceFalsa(["Aulas"]).escolher_topico(
        destino, topicos) == 100
    assert InterfaceFalsa(["0"]).escolher_topico(destino, topicos) is None
    # Nome inexistente avisa e pede de novo; depois aceita pelo número.
    interface = InterfaceFalsa(["Não Existe", "1"])
    assert interface.escolher_topico(destino, topicos) == 100
    assert any("não pertence" in m for m in interface.mensagens)
