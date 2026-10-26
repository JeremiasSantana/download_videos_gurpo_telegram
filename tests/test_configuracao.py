import pathlib

import pytest

from uteis.funcoes.configuracao import carregar_configuracao
from uteis.funcoes.erros import ErroConfiguracao

BASE = {"ID_API": "123456", "API_HASH": "hash-de-teste"}


def test_configuracao_valida():
    config = carregar_configuracao(dict(BASE))

    assert config.api_id == 123456
    assert isinstance(config.api_id, int)
    assert config.api_hash == "hash-de-teste"
    assert config.nome_sessao == "captura_videos"
    assert config.destino_padrao is None
    assert config.limite_padrao is None
    assert config.pasta_padrao == pathlib.Path.home() / "Vídeos"


def test_id_api_ausente():
    ambiente = dict(BASE)
    del ambiente["ID_API"]

    with pytest.raises(ErroConfiguracao):
        carregar_configuracao(ambiente)


def test_id_api_nao_numerico():
    with pytest.raises(ErroConfiguracao):
        carregar_configuracao({**BASE, "ID_API": "abc"})


def test_api_hash_ausente():
    ambiente = dict(BASE)
    ambiente["API_HASH"] = "  "

    with pytest.raises(ErroConfiguracao):
        carregar_configuracao(ambiente)


def test_destino_padrao_e_alias_antigo():
    config = carregar_configuracao({**BASE, "NOME_GRUPO": "Grupo Antigo"})
    assert config.destino_padrao == "Grupo Antigo"

    config = carregar_configuracao(
        {**BASE, "NOME_GRUPO": "Antigo", "DESTINO": "Novo"}
    )
    assert config.destino_padrao == "Novo"


def test_limite_padrao():
    config = carregar_configuracao({**BASE, "LIMITE_MENSAGENS": "50"})
    assert config.limite_padrao == 50

    with pytest.raises(ErroConfiguracao):
        carregar_configuracao({**BASE, "LIMITE_MENSAGENS": "dez"})

    with pytest.raises(ErroConfiguracao):
        carregar_configuracao({**BASE, "LIMITE_MENSAGENS": "-3"})


def test_pasta_e_sessao_personalizadas():
    config = carregar_configuracao(
        {**BASE, "PASTA_VIDEOS": "/tmp/videos-x", "NOME_SESSAO": "s1"}
    )
    assert config.pasta_padrao == pathlib.Path("/tmp/videos-x")
    assert config.nome_sessao == "s1"
