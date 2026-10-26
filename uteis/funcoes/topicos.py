"""Tópicos de grupos de fórum.

Só deve ser usado em destinos classificados como GRUPO_TOPICOS —
nunca tente consultar tópicos em grupos comuns, canais ou conversas.
"""

import logging

from telethon import functions

logger = logging.getLogger("baixador_telegram")


async def buscar_topicos(client, entidade):
    """Obtém {id: título} dos tópicos do fórum, paginando a consulta."""
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
                limit=100,
            )
        )

        pagina = resposta.topics

        if not pagina:
            break

        quantidade_anterior = len(topicos)

        for topico in pagina:
            topicos[topico.id] = topico.title

        if len(topicos) >= resposta.count:
            break

        ultimo_topico = pagina[-1]

        mensagem_referencia = next(
            (
                mensagem
                for mensagem in resposta.messages
                if mensagem.id == ultimo_topico.top_message
            ),
            None,
        )

        if mensagem_referencia is None:
            raise RuntimeError(
                "Não foi possível obter a mensagem de referência "
                "para continuar a paginação dos tópicos."
            )

        novos_offsets = (
            int(mensagem_referencia.date.timestamp()),
            ultimo_topico.top_message,
            ultimo_topico.id,
        )

        offsets_atuais = (offset_date, offset_id, offset_topic)

        if novos_offsets == offsets_atuais:
            break

        if len(topicos) == quantidade_anterior:
            break

        offset_date, offset_id, offset_topic = novos_offsets

    return topicos


def identificar_topico(mensagem, topicos):
    """Identifica o nome do tópico ao qual a mensagem pertence."""
    # A própria mensagem pode ser a mensagem inicial do tópico.
    if mensagem.id in topicos:
        return topicos[mensagem.id]

    cabecalho_resposta = getattr(mensagem, "reply_to", None)

    if cabecalho_resposta:
        id_topico = getattr(cabecalho_resposta, "reply_to_top_id", None)

        if id_topico is None:
            id_resposta = getattr(
                cabecalho_resposta, "reply_to_msg_id", None
            )

            if id_resposta in topicos:
                id_topico = id_resposta

        if id_topico in topicos:
            return topicos[id_topico]

    # Sem identificação, cai no tópico Geral, quando ele existe.
    return topicos.get(1, "Geral")


def identificar_id_topico(mensagem, topicos):
    """Como identificar_topico, mas devolvendo o ID do tópico."""
    nome = identificar_topico(mensagem, topicos)

    for id_topico, titulo in topicos.items():
        if titulo == nome:
            return id_topico

    return None
