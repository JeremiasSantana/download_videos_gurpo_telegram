import asyncio
import pathlib
from types import SimpleNamespace

import pytest

from uteis.funcoes import arquivos
from uteis.funcoes.baixador import OpcoesDownload, baixar_destino, eh_video
from uteis.funcoes.destinos import Destino, TipoDestino


class ArquivoFalso:
    def __init__(self, nome, conteudo, mime="video/mp4"):
        self.name = nome
        self.size = len(conteudo)
        self.mime_type = mime


class MensagemFalsa:
    def __init__(self, id_, nome=None, conteudo=b"12345", top_id=None,
                 comportamento="ok"):
        self.id = id_
        self.video = True
        self.file = (
            ArquivoFalso(nome, conteudo) if nome is not None else None
        )
        if self.file is None:
            self.file = ArquivoFalso(f"video_{id_}.mp4", conteudo)
        self._conteudo = conteudo
        self.comportamento = comportamento
        self.chamadas_download = 0
        self.reply_to = (
            SimpleNamespace(reply_to_top_id=top_id, reply_to_msg_id=None)
            if top_id is not None
            else (SimpleNamespace(reply_to_top_id=None,
                                  reply_to_msg_id=id_)
                  if id_ in (100,) else None)
        )

    async def download_media(self, file=None):
        self.chamadas_download += 1
        caminho = pathlib.Path(file)

        if self.comportamento == "cancelar":
            caminho.write_bytes(b"par")
            raise asyncio.CancelledError()
        if self.comportamento == "erro":
            raise RuntimeError("falha simulada")

        caminho.write_bytes(self._conteudo)
        return str(caminho)


class ClienteFalso:
    def __init__(self, mensagens, topicos=None):
        self.mensagens = mensagens
        self.topicos = topicos or {}
        self.ultimo_reply_to = "não-chamado"

    async def __call__(self, requisicao):
        itens = [
            SimpleNamespace(id=id_, title=titulo, top_message=id_)
            for id_, titulo in self.topicos.items()
        ]
        return SimpleNamespace(
            topics=itens, count=len(itens), messages=[]
        )

    async def iter_messages(self, entidade, limit=None, reply_to=None):
        self.ultimo_reply_to = reply_to
        contador = 0
        for mensagem in self.mensagens:
            if reply_to is not None:
                top = getattr(
                    getattr(mensagem, "reply_to", None),
                    "reply_to_top_id", None,
                )
                if top != reply_to and mensagem.id != reply_to:
                    continue
            if limit is not None and contador >= limit:
                break
            contador += 1
            yield mensagem


def _destino(tipo=TipoDestino.GRUPO_TOPICOS, titulo="Grupo X", id_=777):
    return Destino(
        entidade=SimpleNamespace(id=id_),
        tipo=tipo, titulo=titulo, id_destino=id_,
    )


def _registro(tmp_path):
    return arquivos.RegistroDownloads(tmp_path / ".baixados.json")


def _rodar(cliente, destino, opcoes, registro, topicos=None):
    return asyncio.run(
        baixar_destino(cliente, destino, opcoes, registro,
                       topicos=topicos)
    )


def test_eh_video():
    assert eh_video(MensagemFalsa(1))
    assert eh_video(SimpleNamespace(
        video=None,
        file=SimpleNamespace(mime_type="video/webm", name=None, size=1),
    ))
    assert not eh_video(SimpleNamespace(
        video=None,
        file=SimpleNamespace(mime_type="image/png", name=None, size=1),
    ))
    assert not eh_video(SimpleNamespace(video=None, file=None))


def test_baixa_organizado_por_topico(tmp_path):
    topicos = {1: "Geral", 100: "Aulas"}
    mensagens = [
        MensagemFalsa(100, nome="aula.mp4"),
        MensagemFalsa(101, nome="exercicio.mp4", top_id=100),
        MensagemFalsa(102, nome="geral.mp4"),
        SimpleNamespace(  # mensagem de texto: analisada, não baixada
            id=103, video=None, file=None, reply_to=None,
        ),
    ]
    cliente = ClienteFalso(mensagens, topicos)
    stats = _rodar(
        cliente, _destino(), OpcoesDownload(pasta_base=tmp_path),
        _registro(tmp_path), topicos=topicos,
    )

    assert stats.analisadas == 4
    assert stats.baixados == 3
    assert stats.erros == 0
    base = tmp_path / "Grupo X"
    assert (base / "Aulas" / "aula.mp4").exists()
    assert (base / "Aulas" / "exercicio.mp4").exists()
    assert (base / "Geral" / "geral.mp4").exists()


def test_segunda_execucao_nao_baixa_de_novo(tmp_path):
    topicos = {1: "Geral"}
    mensagens = [MensagemFalsa(1, nome="v.mp4")]
    cliente = ClienteFalso(mensagens, topicos)
    destino = _destino(tipo=TipoDestino.GRUPO_COMUM, titulo="Comum", id_=5)

    _rodar(cliente, destino, OpcoesDownload(pasta_base=tmp_path),
           _registro(tmp_path))
    assert mensagens[0].chamadas_download == 1

    stats = _rodar(cliente, destino, OpcoesDownload(pasta_base=tmp_path),
                   _registro(tmp_path))
    assert stats.pulados == 1
    assert mensagens[0].chamadas_download == 1


def test_duplicidade_por_nome_e_colisao(tmp_path):
    destino = _destino(tipo=TipoDestino.GRUPO_COMUM, titulo="G", id_=9)
    mensagens = [
        MensagemFalsa(1, nome="video.mp4", conteudo=b"12345"),
        # Mesmo nome e tamanho -> duplicado, pula.
        MensagemFalsa(2, nome="video.mp4", conteudo=b"ABCDE"),
        # Mesmo nome, tamanho diferente -> outro vídeo, com sufixo.
        MensagemFalsa(3, nome="video.mp4", conteudo=b"1234567"),
    ]
    cliente = ClienteFalso(mensagens)
    stats = _rodar(cliente, destino, OpcoesDownload(pasta_base=tmp_path),
                   _registro(tmp_path))

    assert stats.baixados == 2
    assert stats.pulados == 1
    pasta = tmp_path / "G"
    assert (pasta / "video.mp4").read_bytes() == b"12345"
    assert (pasta / "video_3.mp4").read_bytes() == b"1234567"
    assert mensagens[1].chamadas_download == 0


def test_topico_selecionado_filtra_a_leitura(tmp_path):
    topicos = {1: "Geral", 100: "Aulas"}
    mensagens = [
        MensagemFalsa(100, nome="a.mp4"),
        MensagemFalsa(101, nome="b.mp4", top_id=100),
        MensagemFalsa(102, nome="c.mp4"),
    ]
    cliente = ClienteFalso(mensagens, topicos)
    stats = _rodar(
        cliente, _destino(),
        OpcoesDownload(pasta_base=tmp_path, topico_id=100),
        _registro(tmp_path), topicos=topicos,
    )

    assert cliente.ultimo_reply_to == 100
    assert stats.analisadas == 2
    assert stats.baixados == 2
    assert (tmp_path / "Grupo X" / "Aulas" / "b.mp4").exists()
    assert not (tmp_path / "Grupo X" / "Geral" / "c.mp4").exists()


def test_erro_num_video_nao_para_os_outros(tmp_path):
    destino = _destino(tipo=TipoDestino.GRUPO_COMUM, titulo="G", id_=3)
    mensagens = [
        MensagemFalsa(1, nome="falha.mp4", comportamento="erro"),
        MensagemFalsa(2, nome="ok.mp4"),
    ]
    cliente = ClienteFalso(mensagens)
    stats = _rodar(cliente, destino, OpcoesDownload(pasta_base=tmp_path),
                   _registro(tmp_path))

    assert stats.erros == 1
    assert stats.baixados == 1
    assert mensagens[0].chamadas_download == 3  # 3 tentativas
    assert not list(tmp_path.rglob("*.part"))


def test_cancelamento_limpa_parcial_e_preserva_anteriores(tmp_path):
    destino = _destino(tipo=TipoDestino.GRUPO_COMUM, titulo="G", id_=4)
    mensagens = [
        MensagemFalsa(1, nome="ok.mp4"),
        MensagemFalsa(2, nome="cancela.mp4", comportamento="cancelar"),
    ]
    cliente = ClienteFalso(mensagens)
    registro = _registro(tmp_path)

    with pytest.raises(asyncio.CancelledError):
        _rodar(cliente, destino, OpcoesDownload(pasta_base=tmp_path),
               registro)

    assert (tmp_path / "G" / "ok.mp4").exists()
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "G" / "cancela.mp4").exists()
    assert registro.ja_registrado(4, 1)
    assert not registro.ja_registrado(4, 2)
