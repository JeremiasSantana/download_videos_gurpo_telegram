from types import SimpleNamespace

from uteis.funcoes.topicos import identificar_topico

TOPICOS = {1: "Geral", 100: "Aulas", 200: "Avisos"}


def _mensagem(id_, top_id=None, reply_id=None):
    reply_to = None
    if top_id is not None or reply_id is not None:
        reply_to = SimpleNamespace(
            reply_to_top_id=top_id, reply_to_msg_id=reply_id
        )
    return SimpleNamespace(id=id_, reply_to=reply_to)


def test_mensagem_inicial_do_topico():
    assert identificar_topico(_mensagem(100), TOPICOS) == "Aulas"


def test_resposta_no_topico():
    assert identificar_topico(_mensagem(555, top_id=200), TOPICOS) == "Avisos"


def test_resposta_direta_a_inicial():
    assert identificar_topico(
        _mensagem(556, reply_id=100), TOPICOS
    ) == "Aulas"


def test_sem_identificacao_cai_no_geral():
    assert identificar_topico(_mensagem(557), TOPICOS) == "Geral"
    assert identificar_topico(_mensagem(558, top_id=999), TOPICOS) == "Geral"
