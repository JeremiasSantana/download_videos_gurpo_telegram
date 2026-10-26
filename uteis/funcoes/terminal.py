"""Interface de terminal: perguntas e seleções do usuário.

Toda a interação (input/print) fica aqui. A lógica do downloader
recebe as escolhas já validadas — nada neste módulo baixa vídeos.
As funções de interpretação são puras e testáveis isoladamente.
"""

import logging
import pathlib

from . import arquivos
from .destinos import listar_destinos, resolver_destino
from .erros import (
    CanceladoPeloUsuario,
    ErroDestino,
    ErroDestinoAmbiguo,
    ErroPasta,
)

logger = logging.getLogger("baixador_telegram")


# =========================
# INTERPRETAÇÃO (funções puras)
# =========================


def interpretar_limite(texto: str):
    """Interpreta o limite de mensagens.

    Vazio -> None (todas). Número positivo -> esse número.
    Qualquer outra coisa -> ValueError com mensagem clara.
    """
    bruto = (texto or "").strip()

    if not bruto:
        return None

    try:
        valor = int(bruto)
    except ValueError:
        raise ValueError(
            "Digite um número inteiro (ex.: 500) ou deixe vazio "
            "para analisar todas as mensagens."
        ) from None

    if valor <= 0:
        raise ValueError("O limite precisa ser um número maior que zero.")

    return valor


def interpretar_escolha(texto: str, quantidade: int) -> int:
    """Interpreta uma escolha numerada (1..quantidade). Devolve o índice."""
    bruto = (texto or "").strip()

    try:
        valor = int(bruto)
    except ValueError:
        raise ValueError("Digite o número de uma das opções.") from None

    if valor < 1 or valor > quantidade:
        raise ValueError(
            f"Digite um número entre 1 e {quantidade}."
        )

    return valor - 1


# =========================
# INTERFACE
# =========================


class InterfaceTerminal:
    """Perguntas ao usuário, com validação e chance de corrigir."""

    def __init__(self, ler=input, mostrar=print):
        self._ler = ler
        self._mostrar = mostrar

    # ---------- utilidades ----------

    def _perguntar(self, texto: str) -> str:
        try:
            return self._ler(texto)
        except (EOFError, KeyboardInterrupt):
            raise CanceladoPeloUsuario(
                "Operação cancelada pelo usuário."
            ) from None

    def _selecionar(self, itens, titulo, rotulo):
        """Mostra uma lista numerada e devolve o item escolhido."""
        self._mostrar(titulo)

        for indice, item in enumerate(itens, start=1):
            self._mostrar(f"  {indice}. {rotulo(item)}")

        while True:
            resposta = self._perguntar("Digite o número da opção: ")

            try:
                return itens[interpretar_escolha(resposta, len(itens))]
            except ValueError as erro:
                self._mostrar(str(erro))

    # ---------- destino ----------

    async def escolher_destino(self, client, padrao=None):
        """Pede o destino até resolver um válido (ou o usuário sair)."""
        while True:
            dica = f" [{padrao}]" if padrao else ""
            texto = self._perguntar(
                "De onde você quer baixar os vídeos?\n"
                "Digite o nome/título, @usuário, link ou ID do grupo, "
                "canal ou conversa\n"
                "(ou 'listar' para ver suas conversas, 'sair' para "
                f"encerrar){dica}: "
            ).strip()

            if not texto and padrao:
                texto = padrao

            if texto.casefold() == "sair":
                raise CanceladoPeloUsuario("Saindo a pedido do usuário.")

            if texto.casefold() in ("listar", "lista"):
                destino = await self._escolher_da_lista(client)
                if destino is not None:
                    return destino
                continue

            if not texto:
                self._mostrar("Digite um destino ou 'listar'.")
                continue

            try:
                return await resolver_destino(client, texto)
            except ErroDestinoAmbiguo as erro:
                self._mostrar(str(erro))
                return self._selecionar(
                    erro.candidatos,
                    "Opções encontradas:",
                    lambda d: (
                        f"{d.titulo} ({d.tipo.value}, ID {d.id})"
                    ),
                )
            except ErroDestino as erro:
                # Não encerra o programa: avisa e pergunta de novo.
                self._mostrar(f"Não consegui: {erro}")
                logger.warning("Destino não resolvido: '%s' — %s",
                               texto, erro)

    async def _escolher_da_lista(self, client):
        destinos = await listar_destinos(client)

        if not destinos:
            self._mostrar(
                "Não encontrei conversas na sua conta."
            )
            return None

        self._mostrar("Suas conversas (0 = voltar):")

        for indice, destino in enumerate(destinos, start=1):
            usuario = (
                f" @{destino.username}" if destino.username else ""
            )
            self._mostrar(
                f"  {indice}. {destino.titulo} "
                f"({destino.tipo.value}){usuario}"
            )

        while True:
            resposta = self._perguntar("Digite o número da opção: ")

            if resposta.strip() == "0":
                return None

            try:
                return destinos[
                    interpretar_escolha(resposta, len(destinos))
                ]
            except ValueError as erro:
                self._mostrar(str(erro))

    # ---------- tópico ----------

    def escolher_topico(self, destino, topicos):
        """Escolhe um tópico (ou todos). Devolve o ID ou None (todos)."""
        itens = sorted(topicos.items(), key=lambda par: par[1].casefold())

        self._mostrar(f"O grupo '{destino.titulo}' tem tópicos:")
        self._mostrar("  0. Todos os tópicos")

        for indice, (id_topico, titulo) in enumerate(itens, start=1):
            self._mostrar(f"  {indice}. {titulo}")

        while True:
            resposta = self._perguntar(
                "Escolha pelo número ou pelo nome do tópico: "
            ).strip()

            if resposta == "0":
                return None

            # Pelo número.
            try:
                indice = interpretar_escolha(resposta, len(itens))
                return itens[indice][0]
            except ValueError:
                pass

            # Pelo nome (tem que pertencer ao grupo).
            correspondentes = [
                id_topico
                for id_topico, titulo in itens
                if titulo.strip().casefold() == resposta.casefold()
            ]

            if len(correspondentes) == 1:
                return correspondentes[0]

            if len(correspondentes) > 1:
                self._mostrar(
                    "Há mais de um tópico com esse nome — "
                    "escolha pelo número."
                )
                continue

            self._mostrar(
                "Esse tópico não pertence a este grupo. "
                "Escolha um da lista, pelo número ou pelo nome exato."
            )

    # ---------- limite ----------

    def escolher_limite(self, padrao=None, contexto="o destino"):
        """Pede o limite de mensagens analisadas, com validação."""
        padrao_texto = (
            f" [{padrao}]" if padrao is not None else " [todas]"
        )
        self._mostrar(
            "O limite é o número de MENSAGENS ANALISADAS em "
            f"{contexto} — não a quantidade de vídeos baixados."
        )

        while True:
            resposta = self._perguntar(
                "Quantas mensagens devo analisar? "
                f"(vazio = {padrao_texto.strip(' []')}) "
            )

            if not resposta.strip():
                return padrao

            try:
                return interpretar_limite(resposta)
            except ValueError as erro:
                self._mostrar(str(erro))

    # ---------- pasta ----------

    def escolher_pasta(self, padrao: pathlib.Path):
        """Pede a pasta de destino, criando-a e testando a gravação."""
        while True:
            resposta = self._perguntar(
                f"Pasta onde salvar os vídeos [{padrao}]: "
            ).strip()

            caminho = (
                arquivos.resolver_caminho(resposta)
                if resposta
                else pathlib.Path(padrao)
            )

            try:
                return arquivos.garantir_pasta(caminho)
            except ErroPasta as erro:
                self._mostrar(str(erro))
                self._mostrar("Informe outro caminho.")
                logger.warning("Pasta recusada: %s — %s", caminho, erro)
