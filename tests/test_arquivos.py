import json
import pathlib
from types import SimpleNamespace

import pytest

from uteis.funcoes import arquivos
from uteis.funcoes.erros import ErroPasta


def test_limpar_nome():
    assert arquivos.limpar_nome('a<b>c:d') == "a_b_c_d"
    assert arquivos.limpar_nome("  nome.  ") == "nome"
    assert arquivos.limpar_nome("") == "Sem nome"
    assert arquivos.limpar_nome("pasta/valida") == "pasta_valida"


def test_resolver_caminho(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert arquivos.resolver_caminho("videos") == tmp_path / "videos"
    assert arquivos.resolver_caminho("/abs/videos") == pathlib.Path(
        "/abs/videos"
    )


def test_garantir_pasta_cria_e_reusa(tmp_path):
    alvo = tmp_path / "a" / "b"
    assert arquivos.garantir_pasta(alvo) == alvo
    assert alvo.is_dir()
    # Segunda vez, já existindo, continua ok.
    assert arquivos.garantir_pasta(alvo) == alvo


def test_garantir_pasta_sobre_arquivo(tmp_path):
    arquivo = tmp_path / "arquivo.txt"
    arquivo.write_text("x")

    with pytest.raises(ErroPasta):
        arquivos.garantir_pasta(arquivo)


def test_arquivo_valido(tmp_path):
    caminho = tmp_path / "v.mp4"

    assert not arquivos.arquivo_valido(caminho)

    caminho.write_bytes(b"")
    assert not arquivos.arquivo_valido(caminho)

    caminho.write_bytes(b"12345")
    assert arquivos.arquivo_valido(caminho)
    assert arquivos.arquivo_valido(caminho, 5)
    assert not arquivos.arquivo_valido(caminho, 4)


def test_decidir_destino_novo(tmp_path):
    destino, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 10, 5)
    assert destino == tmp_path / "v.mp4"
    assert not duplicado


def test_decidir_destino_mesmo_nome_e_tamanho(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"12345")

    destino, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 99, 5)
    assert destino == tmp_path / "v.mp4"
    assert duplicado


def test_decidir_destino_mesmo_nome_tamanho_diferente(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"12345")

    # Outro vídeo (7 bytes) com o mesmo nome: variante com o ID.
    destino, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 99, 7)
    assert destino == tmp_path / "v_99.mp4"
    assert not duplicado

    # Se a variante já existe válida com o tamanho certo, é duplicado.
    (tmp_path / "v_99.mp4").write_bytes(b"1234567")
    destino, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 99, 7)
    assert destino == tmp_path / "v_99.mp4"
    assert duplicado


def test_decidir_destino_sem_tamanho_vale_o_nome(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"qualquer")

    _, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 1, None)
    assert duplicado


def test_decidir_destino_arquivo_vazio_nao_e_duplicado(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"")

    destino, duplicado = arquivos.decidir_destino(tmp_path, "v.mp4", 1, 5)
    assert destino == tmp_path / "v.mp4"
    assert not duplicado


def test_parcial_finalizar_e_remover(tmp_path):
    destino = tmp_path / "v.mp4"
    parcial = arquivos.caminho_parcial(destino)
    assert parcial.name == "v.mp4.part"

    parcial.write_bytes(b"123")
    arquivos.finalizar_download(destino)
    assert destino.read_bytes() == b"123"
    assert not parcial.exists()

    parcial.write_bytes(b"x")
    arquivos.remover_parcial(destino)
    assert not parcial.exists()
    # Remover de novo não pode falhar.
    arquivos.remover_parcial(destino)


def _mensagem(id_, nome=None, mime="video/mp4", tamanho=None):
    arquivo = SimpleNamespace(name=nome, mime_type=mime, size=tamanho)
    return SimpleNamespace(id=id_, file=arquivo, video=True)


def test_nome_da_mensagem():
    assert arquivos.nome_da_mensagem(
        _mensagem(1, nome="aula 1.mp4")
    ) == "aula 1.mp4"
    assert arquivos.nome_da_mensagem(
        _mensagem(2, nome="pasta/video.mp4")
    ) == "video.mp4"
    assert arquivos.nome_da_mensagem(
        _mensagem(3, nome=None, mime="video/mp4")
    ) == "video_3.mp4"
    mensagem = SimpleNamespace(id=4, file=None, video=True)
    assert arquivos.nome_da_mensagem(mensagem) == "video_4.mp4"


def test_tamanho_da_mensagem():
    assert arquivos.tamanho_da_mensagem(_mensagem(1, tamanho=42)) == 42
    assert arquivos.tamanho_da_mensagem(_mensagem(1, tamanho=None)) is None
    assert arquivos.tamanho_da_mensagem(_mensagem(1, tamanho=0)) is None


def test_registro_downloads(tmp_path):
    caminho = tmp_path / ".baixados.json"
    registro = arquivos.RegistroDownloads(caminho)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"12345")

    assert not registro.ja_registrado(777, 10)

    registro.registrar(777, 10, video, "Grupo X", "Geral")
    assert registro.ja_registrado(777, 10)
    # Mesmo ID de mensagem, outro destino: não confunde.
    assert not registro.ja_registrado(888, 10)

    # Recarrega do disco e continua reconhecendo.
    registro2 = arquivos.RegistroDownloads(caminho)
    assert registro2.ja_registrado(777, 10)

    # Se o arquivo sumiu, o registro sozinho não vale.
    video.unlink()
    assert not registro2.ja_registrado(777, 10)


def test_registro_formato_antigo(tmp_path):
    caminho = tmp_path / ".baixados.json"
    video = tmp_path / "antigo.mp4"
    video.write_bytes(b"123")
    caminho.write_text(
        json.dumps({"55": {"arquivo": str(video), "tamanho": 3}}),
        encoding="utf-8",
    )

    registro = arquivos.RegistroDownloads(caminho)
    assert registro.ja_registrado(777, 55)
