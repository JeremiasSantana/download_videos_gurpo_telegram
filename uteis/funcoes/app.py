"""Orquestração do programa: configuração, conexão e execução.

Fluxo: carrega a configuração -> configura os logs -> conecta no
Telegram -> resolve o destino (com ajuda do usuário, se preciso) ->
seleciona tópico/limite/pasta -> executa o motor de download ->
apresenta o resumo.

Erros críticos (configuração, autenticação) encerram de forma
controlada, com código de saída diferente de zero. Erros de um vídeo
específico ficam no motor e não encerram o programa.
"""

import argparse
import asyncio
import logging
import pathlib
import sys

from telethon import TelegramClient

from . import arquivos
from .baixador import OpcoesDownload, baixar_destino
from .configuracao import carregar_configuracao
from .destinos import resolver_destino
from .erros import (
    CanceladoPeloUsuario,
    ErroConfiguracao,
    ErroCritico,
    ErroDestino,
    ErroDestinoAmbiguo,
    ErroDoPrograma,
)
from .registro import configurar_logs
from .terminal import InterfaceTerminal, interpretar_limite
from .topicos import buscar_topicos

logger = logging.getLogger("baixador_telegram")

_PASTA_LOGS = pathlib.Path(__file__).resolve().parents[2] / "logs"


def analisar_argumentos(argv=None):
    """Argumentos opcionais de linha de comando.

    Tudo que for informado aqui (ou no .env) não é perguntado no
    terminal; o que faltar, a interface pergunta com validação.
    """
    parser = argparse.ArgumentParser(
        description="Baixa vídeos de um grupo, canal ou conversa "
                    "do Telegram."
    )
    parser.add_argument(
        "--destino",
        help="nome/título, @usuário, link ou ID do destino",
    )
    parser.add_argument(
        "--topico",
        help="nome ou ID do tópico (apenas grupos com tópicos)",
    )
    parser.add_argument(
        "--todos-topicos",
        action="store_true",
        help="percorrer todos os tópicos, sem perguntar",
    )
    parser.add_argument(
        "--limite",
        help="quantidade de mensagens a analisar "
             "(vazio no terminal = todas)",
    )
    parser.add_argument(
        "--pasta",
        help="pasta onde salvar os vídeos",
    )
    return parser.parse_args(argv)


async def _resolver_com_interface(client, interface, texto):
    """Resolve um destino vindo de argumento/.env, com seleção se ambíguo."""
    try:
        return await resolver_destino(client, texto)
    except ErroDestinoAmbiguo as erro:
        print(str(erro))
        return interface._selecionar(
            erro.candidatos,
            "Opções encontradas:",
            lambda d: f"{d.titulo} ({d.tipo.value}, ID {d.id})",
        )


async def _executar(argumentos) -> int:
    try:
        config = carregar_configuracao()
    except ErroConfiguracao as erro:
        print(f"Erro de configuração: {erro}")
        return 2

    configurar_logs(_PASTA_LOGS)
    logger.info("Iniciando o baixador de vídeos do Telegram.")

    interface = InterfaceTerminal()

    try:
        async with TelegramClient(
            config.nome_sessao, config.api_id, config.api_hash
        ) as client:
            # ----- destino -----
            texto_destino = argumentos.destino or config.destino_padrao

            if texto_destino:
                destino = await _resolver_com_interface(
                    client, interface, texto_destino
                )
            else:
                destino = await interface.escolher_destino(
                    client, padrao=config.destino_padrao
                )

            logger.info(
                "Destino selecionado: %s (%s, ID %s)",
                destino.titulo, destino.tipo.value, destino.id,
            )
            print(
                f"\nDestino: {destino.titulo} "
                f"({destino.tipo.value})"
            )

            # ----- tópicos -----
            topicos = None
            topico_id = None

            if destino.tem_topicos:
                topicos = await buscar_topicos(client, destino.entidade)

                if argumentos.todos_topicos:
                    topico_id = None
                elif argumentos.topico:
                    topico_id = _resolver_topico_argumento(
                        argumentos.topico, topicos
                    )
                else:
                    topico_id = interface.escolher_topico(
                        destino, topicos
                    )

                if topico_id is not None:
                    print(f"Tópico: {topicos.get(topico_id)}")
                    contexto_limite = "o tópico escolhido"
                else:
                    print("Tópicos: todos")
                    contexto_limite = "o destino inteiro"
            else:
                contexto_limite = "o destino"

            # ----- limite -----
            if argumentos.limite:
                try:
                    limite = interpretar_limite(argumentos.limite)
                except ValueError as erro:
                    print(f"Limite inválido: {erro}")
                    return 2
            else:
                limite = interface.escolher_limite(
                    padrao=config.limite_padrao,
                    contexto=contexto_limite,
                )

            # ----- pasta -----
            if argumentos.pasta:
                pasta_base = arquivos.garantir_pasta(
                    arquivos.resolver_caminho(argumentos.pasta)
                )
            else:
                pasta_base = interface.escolher_pasta(config.pasta_padrao)

            print(f"Pasta de destino: {pasta_base}")
            print(
                "Limite: "
                + (
                    f"{limite} mensagens analisadas"
                    if limite is not None
                    else "todas as mensagens acessíveis"
                )
            )
            logger.info(
                "Pasta base: %s | Limite: %s | Tópico: %s",
                pasta_base, limite, topico_id,
            )

            # ----- download -----
            registro = arquivos.RegistroDownloads(
                pasta_base / ".baixados.json"
            )
            opcoes = OpcoesDownload(
                pasta_base=pasta_base, limite=limite,
                topico_id=topico_id,
            )
            stats = await baixar_destino(
                client, destino, opcoes, registro, topicos=topicos
            )

            print("\nResumo:")
            print(f"  Mensagens analisadas: {stats.analisadas}")
            print(f"  Vídeos baixados: {stats.baixados}")
            print(f"  Já existentes (pulados): {stats.pulados}")
            print(f"  Com erro: {stats.erros}")
            logger.info(
                "Concluído. Analisadas=%s baixados=%s pulados=%s "
                "erros=%s",
                stats.analisadas, stats.baixados, stats.pulados,
                stats.erros,
            )
            return 0
    except CanceladoPeloUsuario as erro:
        print(str(erro))
        logger.info("Execução cancelada pelo usuário.")
        return 0
    except (ErroDestino, ErroDoPrograma) as erro:
        # ErroCritico é um ErroDoPrograma: cai aqui.
        print(f"Erro: {erro}")
        logger.critical("%s", erro)
        return 1
    except Exception as erro:  # conexão/autenticação e imprevistos
        # Não expõe detalhes sensíveis: registra o tipo e a mensagem
        # técnica no log, sem credenciais.
        print(
            "Algo deu errado ao conectar/executar. "
            "Detalhes técnicos foram registrados no log."
        )
        logger.critical(
            "Falha inesperada: %s: %s", type(erro).__name__, erro,
            exc_info=True,
        )
        return 1


def _resolver_topico_argumento(texto, topicos):
    """Resolve --topico (ID numérico ou nome) validando que ele existe."""
    bruto = str(texto).strip()

    if bruto.isdigit() and int(bruto) in topicos:
        return int(bruto)

    correspondentes = [
        id_topico
        for id_topico, titulo in topicos.items()
        if titulo.strip().casefold() == bruto.casefold()
    ]

    if len(correspondentes) == 1:
        return correspondentes[0]

    raise ErroDestino(
        f"O tópico '{texto}' não pertence a este grupo. "
        f"Tópicos disponíveis: {', '.join(topicos.values())}"
    )


def main(argv=None) -> int:
    """Ponto de entrada síncrono (trata o Ctrl+C sem traceback)."""
    argumentos = analisar_argumentos(argv)

    try:
        return asyncio.run(_executar(argumentos))
    except KeyboardInterrupt:
        print(
            "\nInterrompido por você (Ctrl+C). "
            "O que já foi baixado está salvo."
        )
        print("Rode de novo para continuar de onde parou.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
