import datetime
from types import SimpleNamespace

import pytest
from telethon.tl.types import Channel, Chat, ChatPhotoEmpty, User

_FOTO = ChatPhotoEmpty()
_DATA = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

from uteis.funcoes.destinos import (
    TipoDestino,
    classificar,
    resolver_destino,
)
from uteis.funcoes.erros import ErroDestino, ErroDestinoAmbiguo


# ---------- classificação pela entidade ----------


def test_classificar_conversa_privada():
    entidade = User(id=1, first_name="Ana")
    assert classificar(entidade) is TipoDestino.CONVERSA_PRIVADA


def test_classificar_grupo_comum():
    entidade = Chat(id=2, title="Família", photo=_FOTO, date=_DATA, participants_count=3, version=1)
    assert classificar(entidade) is TipoDestino.GRUPO_COMUM


def test_classificar_canal():
    entidade = Channel(id=3, title="Notícias", broadcast=True, photo=_FOTO, date=_DATA)
    assert classificar(entidade) is TipoDestino.CANAL


def test_classificar_supergrupo_sem_topicos():
    entidade = Channel(id=4, title="Super", megagroup=True, photo=_FOTO, date=_DATA)
    assert classificar(entidade) is TipoDestino.GRUPO_COMUM


def test_classificar_grupo_com_topicos():
    entidade = Channel(id=5, title="Fórum", megagroup=True, forum=True, photo=_FOTO, date=_DATA)
    assert classificar(entidade) is TipoDestino.GRUPO_TOPICOS


# ---------- resolução ----------


def _entidade(titulo=None, id_=1, username=None, first_name=None):
    return SimpleNamespace(
        title=titulo, id=id_, username=username, first_name=first_name,
        broadcast=False, megagroup=False, forum=False,
    )


class ClienteFalso:
    def __init__(self, entidades_por_username=None, dialogos=None):
        self._por_username = entidades_por_username or {}
        self._dialogos = dialogos or []

    async def get_entity(self, referencia):
        if referencia in self._por_username:
            return self._por_username[referencia]
        for dialogo in self._dialogos:
            if getattr(dialogo.entity, "id", None) == referencia:
                return dialogo.entity
        raise ValueError("entidade não encontrada")

    async def iter_dialogs(self):
        for dialogo in self._dialogos:
            yield dialogo


def _dialogo(entidade):
    nome = entidade.title or entidade.first_name
    return SimpleNamespace(name=nome, entity=entidade)


async def _resolver(cliente, texto):
    return await resolver_destino(cliente, texto)


def test_resolver_por_username_e_link():
    import asyncio

    entidade = _entidade("Canal X", id_=10, username="canalx")
    cliente = ClienteFalso({"canalx": entidade})

    destino = asyncio.run(_resolver(cliente, "@canalx"))
    assert destino.titulo == "Canal X"
    assert destino.id == 10

    destino = asyncio.run(_resolver(cliente, "https://t.me/canalx"))
    assert destino.id == 10


def test_resolver_por_id():
    import asyncio

    entidade = _entidade("Grupo", id_=123)
    cliente = ClienteFalso(dialogos=[_dialogo(entidade)])

    destino = asyncio.run(_resolver(cliente, "123"))
    assert destino.titulo == "Grupo"


def test_resolver_por_titulo_exato():
    import asyncio

    entidade = _entidade("Grupo da Família", id_=7)
    cliente = ClienteFalso(dialogos=[_dialogo(entidade)])

    destino = asyncio.run(_resolver(cliente, "grupo da família"))
    assert destino.id == 7


def test_resolver_titulo_repetido_e_ambiguo():
    import asyncio

    cliente = ClienteFalso(dialogos=[
        _dialogo(_entidade("Trabalho", id_=1)),
        _dialogo(_entidade("Trabalho", id_=2)),
    ])

    with pytest.raises(ErroDestinoAmbiguo) as info:
        asyncio.run(_resolver(cliente, "Trabalho"))

    assert len(info.value.candidatos) == 2


def test_resolver_inexistente():
    import asyncio

    cliente = ClienteFalso()

    with pytest.raises(ErroDestino):
        asyncio.run(_resolver(cliente, "Nada Aqui"))

    with pytest.raises(ErroDestino):
        asyncio.run(_resolver(cliente, "   "))
