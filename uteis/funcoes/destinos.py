"""Identificação de destinos do Telegram.

O tipo de um destino (grupo comum, grupo com tópicos/fórum, canal ou
conversa privada) é determinado pela ENTIDADE que o Telethon devolve —
nunca apenas pelo nome que o usuário digitou.

Formas de informar o destino:
- Título exato do grupo/canal/conversa (buscado nos diálogos da conta;
  se houver mais de um com o mesmo título, nada é escolhido sozinho:
  levanta ErroDestinoAmbiguo com os candidatos).
- Nome de usuário: ``@nome`` ou só ``nome``.
- Link: ``https://t.me/nome``, ``t.me/nome`` ou link interno
  ``https://t.me/c/<id>/...``.
- ID numérico (aceita o ID "marcado" do Telethon, ex.: ``-100123...``).
"""

import enum
import logging
import re

from .erros import ErroDestino, ErroDestinoAmbiguo

logger = logging.getLogger("baixador_telegram")


class TipoDestino(enum.Enum):
    """Tipos de destino reconhecidos."""

    GRUPO_TOPICOS = "grupo com tópicos"
    GRUPO_COMUM = "grupo"
    CANAL = "canal"
    CONVERSA_PRIVADA = "conversa privada"
    DESCONHECIDO = "destino"


class Destino:
    """Um destino já resolvido e classificado."""

    def __init__(self, entidade, tipo, titulo, id_destino, username=None):
        self.entidade = entidade
        self.tipo = tipo
        self.titulo = titulo
        self.id = id_destino
        self.username = username

    @property
    def tem_topicos(self):
        return self.tipo is TipoDestino.GRUPO_TOPICOS

    def __repr__(self):
        return (
            f"Destino(titulo={self.titulo!r}, tipo={self.tipo.value!r}, "
            f"id={self.id!r})"
        )


def titulo_da_entidade(entidade) -> str:
    """Título visível: título do grupo/canal ou nome da pessoa."""
    titulo = getattr(entidade, "title", None)

    if titulo:
        return str(titulo)

    partes = [
        getattr(entidade, "first_name", None),
        getattr(entidade, "last_name", None),
    ]
    nome = " ".join(parte for parte in partes if parte)

    if nome:
        return nome

    username = getattr(entidade, "username", None)
    return str(username) if username else "Sem nome"


def classificar(entidade) -> TipoDestino:
    """Classifica a entidade do Telethon pelo tipo real dela."""
    try:
        from telethon.tl.types import Channel, Chat, User

        if isinstance(entidade, User):
            return TipoDestino.CONVERSA_PRIVADA

        if isinstance(entidade, Chat):
            return TipoDestino.GRUPO_COMUM

        if isinstance(entidade, Channel):
            if getattr(entidade, "broadcast", False):
                return TipoDestino.CANAL
            if getattr(entidade, "megagroup", False):
                if getattr(entidade, "forum", False):
                    return TipoDestino.GRUPO_TOPICOS
                return TipoDestino.GRUPO_COMUM
            return TipoDestino.CANAL
    except Exception:  # pragma: no cover - telethon sempre presente
        logger.debug("Falha ao classificar por tipos do Telethon",
                     exc_info=True)

    # Alternativa por atributos (útil para objetos equivalentes).
    if getattr(entidade, "broadcast", False):
        return TipoDestino.CANAL
    if getattr(entidade, "megagroup", False):
        if getattr(entidade, "forum", False):
            return TipoDestino.GRUPO_TOPICOS
        return TipoDestino.GRUPO_COMUM
    if hasattr(entidade, "title"):
        return TipoDestino.GRUPO_COMUM
    if hasattr(entidade, "first_name"):
        return TipoDestino.CONVERSA_PRIVADA

    return TipoDestino.DESCONHECIDO


def montar_destino(entidade) -> Destino:
    """Monta o Destino a partir de uma entidade resolvida."""
    return Destino(
        entidade=entidade,
        tipo=classificar(entidade),
        titulo=titulo_da_entidade(entidade),
        id_destino=getattr(entidade, "id", None),
        username=getattr(entidade, "username", None),
    )


# =========================
# RESOLUÇÃO DO QUE O USUÁRIO DIGITOU
# =========================

_RE_ID = re.compile(r"-?\d+")
_RE_LINK_INTERNO = re.compile(r"(?:https?://)?t\.me/c/(\d+)")
_RE_LINK_OU_USERNAME = re.compile(
    r"(?:https?://)?t\.me/([A-Za-z0-9_]+)|@([A-Za-z0-9_]+)"
)


def _extrair_username(texto: str):
    """Extrai o nome de usuário de um link/@, ou None se não for o caso."""
    correspondencia = _RE_LINK_OU_USERNAME.fullmatch(texto.strip())

    if not correspondencia:
        return None

    return correspondencia.group(1) or correspondencia.group(2)


async def _tentar_entidade(client, referencia, descricao):
    """Chama client.get_entity convertendo falhas em ErroDestino."""
    try:
        return await client.get_entity(referencia)
    except Exception as erro:
        logger.debug("get_entity falhou para %s: %s", descricao, erro)
        return None


async def _buscar_por_titulo(client, titulo: str):
    """Procura destinos cujo título visível é exatamente o informado."""
    procurado = titulo.strip().casefold()
    encontrados = []

    async for dialogo in client.iter_dialogs():
        entidade = getattr(dialogo, "entity", None)

        if entidade is None:
            continue

        nome = (getattr(dialogo, "name", None)
                or titulo_da_entidade(entidade))

        if (nome or "").strip().casefold() == procurado:
            encontrados.append(montar_destino(entidade))

    return encontrados


async def _buscar_por_id(client, id_informado: int):
    """Resolve um ID numérico (direto ou procurando nos diálogos)."""
    entidade = await _tentar_entidade(client, id_informado, "id numérico")

    if entidade is not None:
        return montar_destino(entidade)

    try:
        from telethon import utils

        def id_marcado(entidade):
            try:
                return utils.get_peer_id(entidade)
            except Exception:
                return None
    except Exception:  # pragma: no cover
        id_marcado = lambda entidade: None  # noqa: E731

    async for dialogo in client.iter_dialogs():
        entidade = getattr(dialogo, "entity", None)

        if entidade is None:
            continue

        if getattr(entidade, "id", None) == id_informado:
            return montar_destino(entidade)

        marcado = id_marcado(entidade)

        if marcado is not None and (
            marcado == id_informado or abs(marcado) == abs(id_informado)
        ):
            return montar_destino(entidade)

    return None


async def resolver_destino(client, entrada: str) -> Destino:
    """Resolve o texto do usuário para um Destino classificado.

    Levanta ErroDestino (não encontrado/inacessível) ou
    ErroDestinoAmbiguo (vários com o mesmo título).
    """
    texto = (entrada or "").strip()

    if not texto:
        raise ErroDestino("Nenhum destino foi informado.")

    # ID numérico.
    if _RE_ID.fullmatch(texto):
        destino = await _buscar_por_id(client, int(texto))

        if destino is not None:
            return destino

        raise ErroDestino(
            f"Não encontrei nenhum destino acessível com o ID {texto}. "
            "Confira o ID ou escolha o destino pela lista (digite "
            "'listar')."
        )

    # Link interno t.me/c/<id>/...
    correspondencia = _RE_LINK_INTERNO.match(texto)

    if correspondencia:
        destino = await _buscar_por_id(client, int(correspondencia.group(1)))

        if destino is not None:
            return destino

        raise ErroDestino(
            "Não consegui acessar o destino desse link interno. "
            "Ele só funciona se a sua conta participa do grupo/canal."
        )

    # Título exato nos diálogos (tem prioridade sobre nome de usuário).
    if " " in texto or _extrair_username(texto) is None:
        encontrados = await _buscar_por_titulo(client, texto)

        if len(encontrados) == 1:
            return encontrados[0]

        if len(encontrados) > 1:
            raise ErroDestinoAmbiguo(
                f"Encontrei {len(encontrados)} destinos chamados "
                f"'{texto}'. Escolha um deles:",
                encontrados,
            )

    # Nome de usuário / link público.
    username = _extrair_username(texto) or (
        texto if re.fullmatch(r"[A-Za-z0-9_]{4,}", texto) else None
    )

    if username:
        entidade = await _tentar_entidade(client, username, "username")

        if entidade is not None:
            return montar_destino(entidade)

    # Última tentativa como título, mesmo sem espaços.
    if " " not in texto and _extrair_username(texto) is None:
        encontrados = await _buscar_por_titulo(client, texto)

        if len(encontrados) == 1:
            return encontrados[0]

        if len(encontrados) > 1:
            raise ErroDestinoAmbiguo(
                f"Encontrei {len(encontrados)} destinos chamados "
                f"'{texto}'. Escolha um deles:",
                encontrados,
            )

    raise ErroDestino(
        f"Não encontrei o destino '{texto}'. Ele pode não existir, "
        "ser privado ou a sua conta não ter acesso. Confira o nome/"
        "link/ID ou digite 'listar' para escolher entre os seus "
        "grupos, canais e conversas."
    )


async def listar_destinos(client):
    """Lista os destinos dos diálogos da conta, já classificados."""
    destinos = []

    async for dialogo in client.iter_dialogs():
        entidade = getattr(dialogo, "entity", None)

        if entidade is not None:
            destinos.append(montar_destino(entidade))

    return destinos
