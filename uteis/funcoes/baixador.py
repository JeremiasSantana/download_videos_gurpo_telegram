"""Motor de download: percorre as mensagens e baixa os vídeos.

Este módulo não conhece o terminal: recebe o destino já resolvido, as
opções e o registro, e devolve as estatísticas. É a mesma lógica que
uma futura interface (desktop/web) poderá chamar.

Regras:
- O limite é de MENSAGENS ANALISADAS, não de vídeos baixados.
- Com um tópico selecionado, a leitura é filtrada naquele tópico e o
  limite conta só as mensagens dele. Com "todos os tópicos" (ou em
  destinos sem tópicos), o limite conta o total varrido no destino.
- A ordem de leitura é a padrão do Telethon: das mensagens mais
  recentes para as mais antigas.
- Um vídeo que falha não interrompe os demais; falta de espaço em
  disco (ENOSPC) é erro crítico e interrompe com segurança.
"""

import asyncio
import dataclasses
import errno
import logging
import pathlib

from telethon.errors import FloodWaitError

from . import arquivos
from .erros import ErroCritico
from .topicos import buscar_topicos, identificar_topico

logger = logging.getLogger("baixador_telegram")

MAX_TENTATIVAS = 3


@dataclasses.dataclass
class OpcoesDownload:
    """Opções de uma execução de download."""

    pasta_base: pathlib.Path
    limite: int = None          # mensagens analisadas; None = todas
    topico_id: int = None       # None = todos os tópicos / sem tópico


@dataclasses.dataclass
class Estatisticas:
    """Resultado de uma execução."""

    analisadas: int = 0
    baixados: int = 0
    pulados: int = 0
    erros: int = 0


def eh_video(mensagem) -> bool:
    """Verifica se a mensagem contém um vídeo."""
    if getattr(mensagem, "video", None):
        return True

    # Vídeos enviados como documento têm tipo MIME de vídeo.
    arquivo = getattr(mensagem, "file", None)

    return bool(
        arquivo
        and getattr(arquivo, "mime_type", None)
        and arquivo.mime_type.startswith("video/")
    )


async def _baixar_um(mensagem, destino: pathlib.Path, esperado):
    """Baixa para o ``.part`` e promove a final só após conferir."""
    parcial = arquivos.caminho_parcial(destino)

    try:
        caminho = await mensagem.download_media(file=str(parcial))
    except asyncio.CancelledError:
        arquivos.remover_parcial(destino)
        raise
    except OSError as erro:
        arquivos.remover_parcial(destino)
        if erro.errno == errno.ENOSPC:
            raise ErroCritico(
                "Falta de espaço em disco. Libere espaço e rode "
                "novamente — o que já foi baixado será aproveitado."
            ) from erro
        raise

    if not caminho or not parcial.exists():
        arquivos.remover_parcial(destino)
        raise RuntimeError("O download não gerou arquivo.")

    if esperado is not None and parcial.stat().st_size != esperado:
        tamanho_baixado = parcial.stat().st_size
        arquivos.remover_parcial(destino)
        raise RuntimeError(
            f"Tamanho divergente: esperado {esperado} bytes, "
            f"baixado {tamanho_baixado} bytes."
        )

    try:
        arquivos.finalizar_download(destino)
    except OSError as erro:
        if erro.errno == errno.ENOSPC:
            raise ErroCritico(
                "Falta de espaço em disco ao gravar o arquivo final."
            ) from erro
        raise

    return destino


async def _baixar_com_tentativas(mensagem, destino: pathlib.Path,
                                 esperado) -> bool:
    """Tenta baixar um vídeo; True se conseguiu, False se desistiu."""
    tentativas = 0

    while tentativas < MAX_TENTATIVAS:
        try:
            await _baixar_um(mensagem, destino, esperado)
            return True
        except FloodWaitError as erro:
            # Limite do Telegram: espera o tempo pedido, sem gastar
            # as tentativas.
            espera = int(getattr(erro, "seconds", 0)) + 1
            logger.warning(
                "Telegram pediu uma pausa de %ss (mensagem %s).",
                espera, mensagem.id,
            )
            await asyncio.sleep(espera)
        except asyncio.CancelledError:
            raise
        except ErroCritico:
            raise
        except Exception as erro:  # este vídeo não pode parar os outros
            tentativas += 1

            if tentativas < MAX_TENTATIVAS:
                espera = 2 ** tentativas
                logger.warning(
                    "Mensagem %s: %s — tentativa %s/%s em %ss.",
                    mensagem.id, erro, tentativas + 1, MAX_TENTATIVAS,
                    espera,
                )
                await asyncio.sleep(espera)
            else:
                logger.error(
                    "Mensagem %s: desisti após %s tentativas. "
                    "Último erro: %s",
                    mensagem.id, MAX_TENTATIVAS, erro,
                )

    return False


async def baixar_destino(client, destino, opcoes: OpcoesDownload,
                         registro, topicos=None) -> Estatisticas:
    """Baixa os vídeos de um destino já resolvido.

    ``topicos`` pode ser passado pronto (quando a interface já os
    buscou para a seleção); senão, é buscado aqui — só para grupos
    com tópicos.
    """
    stats = Estatisticas()

    if destino.tem_topicos:
        if topicos is None:
            topicos = await buscar_topicos(client, destino.entidade)
        logger.info("Tópicos encontrados: %s", len(topicos))
    else:
        topicos = {}

    pasta_destino = opcoes.pasta_base / arquivos.limpar_nome(destino.titulo)
    pastas_criadas = set()

    def pasta_de(nome_topico):
        pasta = (
            pasta_destino / arquivos.limpar_nome(nome_topico)
            if nome_topico
            else pasta_destino
        )
        if pasta not in pastas_criadas:
            pasta.mkdir(parents=True, exist_ok=True)
            pastas_criadas.add(pasta)
        return pasta

    argumentos = {}
    if destino.tem_topicos and opcoes.topico_id is not None:
        argumentos["reply_to"] = opcoes.topico_id
        nome_topico_selecionado = topicos.get(
            opcoes.topico_id, "Tópico"
        )
    else:
        nome_topico_selecionado = None

    try:
        async for mensagem in client.iter_messages(
            destino.entidade, limit=opcoes.limite, **argumentos
        ):
            stats.analisadas += 1

            if not eh_video(mensagem):
                continue

            if destino.tem_topicos and opcoes.topico_id is None:
                nome_topico = identificar_topico(mensagem, topicos)
            else:
                nome_topico = nome_topico_selecionado

            try:
                pasta = pasta_de(nome_topico)
            except OSError as erro:
                if erro.errno == errno.ENOSPC:
                    raise ErroCritico(
                        "Falta de espaço em disco ao criar pastas."
                    ) from erro
                stats.erros += 1
                logger.error(
                    "Não consegui criar a pasta do destino/tópico: %s",
                    erro,
                )
                continue

            esperado = arquivos.tamanho_da_mensagem(mensagem)
            nome = arquivos.nome_da_mensagem(mensagem)

            # Registro primeiro: vídeo já concluído (mesmo que a
            # pasta atual seja outra, ex.: estrutura antiga) não
            # é baixado de novo.
            if registro.ja_registrado(destino.id, mensagem.id):
                stats.pulados += 1
                logger.warning(
                    "Já baixado (registro): %s — mensagem %s.",
                    nome, mensagem.id,
                )
                continue

            destino_arquivo, ja_baixado = arquivos.decidir_destino(
                pasta, nome, mensagem.id, esperado
            )

            if ja_baixado:
                stats.pulados += 1
                logger.warning(
                    "Já existe na pasta: %s — pulando.", destino_arquivo,
                )
                # Alimenta o registro para as próximas execuções.
                registro.registrar(
                    destino.id, mensagem.id, destino_arquivo,
                    destino.titulo, nome_topico,
                )
                continue

            sucesso = await _baixar_com_tentativas(
                mensagem, destino_arquivo, esperado
            )

            if sucesso:
                stats.baixados += 1
                registro.registrar(
                    destino.id, mensagem.id, destino_arquivo,
                    destino.titulo, nome_topico,
                )
                logger.info("[OK] %s: %s", nome_topico or destino.titulo,
                            destino_arquivo)
            else:
                stats.erros += 1
    except asyncio.CancelledError:
        # Interrupção: o registro já foi salvo a cada vídeo; garante
        # uma última gravação antes de propagar o cancelamento.
        registro.salvar()
        raise

    return stats
