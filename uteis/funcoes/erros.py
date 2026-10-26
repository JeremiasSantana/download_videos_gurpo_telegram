"""Exceções próprias do programa.

Usar tipos específicos (em vez de ``Exception`` genérica) permite que a
interface trate cada classe de problema da forma certa: erro de
configuração encerra o programa, erro num vídeo específico não.
"""


class ErroDoPrograma(Exception):
    """Erro base do programa, com mensagem apresentável ao usuário."""


class ErroConfiguracao(ErroDoPrograma):
    """Credenciais ou configurações ausentes/inválidas (erro crítico)."""


class ErroDestino(ErroDoPrograma):
    """Destino não encontrado, inacessível ou inválido."""


class ErroDestinoAmbiguo(ErroDestino):
    """Vários destinos com o mesmo nome/título.

    Carrega ``candidatos`` (lista de Destino) para a interface
    apresentar as opções e o usuário escolher — nunca escolhemos
    um arbitrariamente.
    """

    def __init__(self, mensagem, candidatos):
        super().__init__(mensagem)
        self.candidatos = list(candidatos)


class ErroPasta(ErroDoPrograma):
    """A pasta de destino não pôde ser criada ou não aceita gravação."""


class ErroCritico(ErroDoPrograma):
    """Falha que impede continuar (ex.: falta de espaço em disco)."""


class CanceladoPeloUsuario(ErroDoPrograma):
    """O usuário desistiu de uma pergunta/seleção no terminal."""
