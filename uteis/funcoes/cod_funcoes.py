import asyncio
import mimetypes
import os
import pathlib

from dotenv import load_dotenv
from telethon import TelegramClient, functions

# =========================
# CONFIGURAÇÕES
# =========================

load_dotenv()

id_api = os.getenv("ID_API")
api_hash = os.getenv("API_HASH")

if not id_api or not api_hash:
    raise ValueError(
        "Configure ID_API e API_HASH no arquivo .env."
    )

# id_api = int(id_api)

nome_grupo = "SuperTopicos 25 em 1 - VIP 🍓"

caminho_base = pathlib.Path("/home/jeremias/Vídeos")

# None significa percorrer todo o histórico acessível.
limite = None


# =========================
# TRATAMENTO DO NOME DA PASTA
# =========================

def limpar_nome_pasta(nome):

    caracteres_invalidos = '<>:"/\\|?*'

    for caractere in caracteres_invalidos:
        nome = nome.replace(caractere, "_")

    return nome.strip().rstrip(".") or "Sem nome"


# =========================
# LOCALIZAR O GRUPO
# =========================

async def localizar_grupo(client, nome_grupo):
    """Localiza um grupo pelo nome visível nos diálogos."""

    nome_procurado = nome_grupo.strip().casefold()

    async for dialogo in client.iter_dialogs():

        if (dialogo.name or "").strip().casefold() == nome_procurado:
            return dialogo.entity

    raise ValueError(
        f"O grupo '{nome_grupo}' não foi encontrado "
        "nos diálogos da conta autenticada."
    )


# =========================
# BUSCAR OS TÓPICOS
# =========================

async def buscar_topicos(client, entidade):
    """Obtém os IDs e os nomes dos tópicos do fórum."""

    topicos = {}

    offset_date = 0
    offset_id = 0
    offset_topic = 0

    while True:

        resposta = await client(
            functions.messages.GetForumTopicsRequest(
                peer=entidade,
                q="",
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            )
        )

        pagina = resposta.topics

        if not pagina:
            break

        quantidade_anterior = len(topicos)

        for topico in pagina:
            topicos[topico.id] = topico.title

        # Verifica se todos os tópicos foram consultados.
        if len(topicos) >= resposta.count:
            break

        # Prepara a referência para a próxima página.
        ultimo_topico = pagina[-1]

        mensagem_referencia = next(
            (
                mensagem
                for mensagem in resposta.messages
                if mensagem.id == ultimo_topico.top_message
            ),
            None
        )

        if mensagem_referencia is None:
            raise RuntimeError(
                "Não foi possível obter a mensagem de referência "
                "para continuar a paginação dos tópicos."
            )

        novos_offsets = (
            int(mensagem_referencia.date.timestamp()),
            ultimo_topico.top_message,
            ultimo_topico.id
        )

        offsets_atuais = (
            offset_date,
            offset_id,
            offset_topic
        )

        # Evita repetir indefinidamente a mesma página.
        if novos_offsets == offsets_atuais:
            break

        if len(topicos) == quantidade_anterior:
            break

        offset_date, offset_id, offset_topic = novos_offsets

    return topicos


# =========================
# IDENTIFICAR O TÓPICO
# =========================

def identificar_topico(mensagem, topicos):
    """Identifica o tópico associado à mensagem."""

    # A própria mensagem pode ser a mensagem inicial do tópico.
    if mensagem.id in topicos:
        return topicos[mensagem.id]

    cabecalho_resposta = mensagem.reply_to

    if cabecalho_resposta:

        # Obtém o ID da mensagem que iniciou a conversa.
        id_topico = getattr(
            cabecalho_resposta,
            "reply_to_top_id",
            None
        )

        # Alternativa para respostas diretas à mensagem inicial.
        if id_topico is None:

            id_resposta = getattr(
                cabecalho_resposta,
                "reply_to_msg_id",
                None
            )

            if id_resposta in topicos:
                id_topico = id_resposta

        if id_topico in topicos:
            return topicos[id_topico]

    # Usa o título do tópico Geral, se estiver disponível.
    return topicos.get(1, "Geral")


# =========================
# VERIFICAR SE É UM VÍDEO
# =========================

def mensagem_e_video(mensagem):
    """Verifica se a mensagem contém um vídeo."""

    if mensagem.video:
        return True

    # Também considera arquivos enviados como documentos
    # cujo tipo MIME identifica uma mídia de vídeo.
    arquivo = mensagem.file

    return bool(
        arquivo
        and arquivo.mime_type
        and arquivo.mime_type.startswith("video/")
    )


# =========================
# BAIXAR OS VÍDEOS
# =========================

async def baixar_videos(client, grupo, limite):

    # Localiza o grupo pelo nome visível.
    entidade = await localizar_grupo(client, grupo)

    # Obtém os tópicos disponíveis.
    topicos = await buscar_topicos(client, entidade)

    print(f"Tópicos encontrados: {len(topicos)}")

    total = 0

    # None mantém a leitura de todo o histórico acessível.
    async for mensagem in client.iter_messages(
        entidade,
        limit=limite
    ):

        # Ignora mensagens que não contêm vídeos.
        if not mensagem_e_video(mensagem):
            continue

        # Identifica a pasta correspondente ao tópico.
        nome_topico = identificar_topico(
            mensagem,
            topicos
        )

        # Cria a pasta do tópico.
        pasta = (
            caminho_base
            / limpar_nome_pasta(nome_topico)
        )

        pasta.mkdir(
            parents=True,
            exist_ok=True
        )

        # Obtém o nome original do arquivo, quando disponível.
        if mensagem.file and mensagem.file.name:

            nome_arquivo = pathlib.Path(
                mensagem.file.name
            ).name

        else:
            # Tenta determinar a extensão pelo tipo MIME.
            tipo_mime = (
                mensagem.file.mime_type
                if mensagem.file
                else None
            )

            extensao = (
                mimetypes.guess_extension(tipo_mime)
                if tipo_mime
                else None
            )

            if not extensao:
                extensao = ".mp4"

            nome_arquivo = (
                f"video_{mensagem.id}{extensao}"
            )

        # Adiciona o ID da mensagem ao nome do arquivo.
        destino = pasta / (
            f"{mensagem.id}_{nome_arquivo}"
        )

        # Baixa o vídeo para o destino definido.
        caminho = await mensagem.download_media(
            file=str(destino)
        )

        if caminho:

            total += 1

            print(
                f"[OK] {nome_topico}: {caminho}"
            )

    print(
        f"\nDownload concluído! "
        f"Total de vídeos: {total}"
    )


# =========================
# EXECUÇÃO PRINCIPAL
# =========================

async def main():

    async with TelegramClient(
        session="captura_videos-sessão",
        api_id=id_api,
        api_hash=api_hash
    ) as client:

        await baixar_videos(
            client,
            nome_grupo,
            limite=limite
        )


if __name__ == "__main__":
    asyncio.run(main())