"""Pastas, nomes de arquivo, duplicidade e registro de downloads.

Regra de duplicidade (critério principal: o NOME do arquivo dentro da
pasta do destino/tópico):

- Mesmo nome e mesmo tamanho do vídeo esperado -> já baixado, pula.
- Mesmo nome, mas tamanho diferente -> é OUTRO vídeo com nome igual:
  salva com o ID da mensagem como sufixo (exceção documentada no
  README, apenas para resolver a colisão).
- Arquivo existente vazio ou com tamanho diferente do esperado nunca
  é considerado um download válido/concluído.

Limitação conhecida: dois vídeos diferentes com exatamente o mesmo
nome E o mesmo tamanho serão tratados como o mesmo arquivo. Nome
igual não garante conteúdo idêntico — é o preço da regra por nome.

Downloads são feitos para um temporário ``.part`` e só viram o arquivo
final (renomeação) depois de concluídos e conferidos.
"""

import json
import logging
import mimetypes
import os
import pathlib
import tempfile

from .erros import ErroPasta

logger = logging.getLogger("baixador_telegram")


# =========================
# NOMES E CAMINHOS
# =========================


def limpar_nome(nome: str) -> str:
    """Remove caracteres inválidos para nome de pasta/arquivo."""
    caracteres_invalidos = '<>:"/\\|?*'

    for caractere in caracteres_invalidos:
        nome = nome.replace(caractere, "_")

    return nome.strip().rstrip(".") or "Sem nome"


def resolver_caminho(texto: str) -> pathlib.Path:
    """Converte o texto informado em caminho absoluto.

    Aceita ``~``, caminhos absolutos e relativos (ao diretório atual).
    """
    caminho = pathlib.Path(texto.strip()).expanduser()

    if not caminho.is_absolute():
        caminho = pathlib.Path.cwd() / caminho

    return caminho


def garantir_pasta(caminho: pathlib.Path) -> pathlib.Path:
    """Cria a pasta (e as pais) e confirma que dá para gravar nela."""
    try:
        caminho.mkdir(parents=True, exist_ok=True)
    except OSError as erro:
        raise ErroPasta(
            f"Não consegui criar a pasta {caminho}: {erro.strerror or erro}"
        ) from erro

    if not caminho.is_dir():
        raise ErroPasta(f"O caminho {caminho} existe, mas não é uma pasta.")

    try:
        with tempfile.NamedTemporaryFile(
            dir=caminho, prefix=".teste-", delete=True
        ):
            pass
    except OSError as erro:
        raise ErroPasta(
            f"A pasta {caminho} não aceita gravação: "
            f"{erro.strerror or erro}"
        ) from erro

    return caminho


# =========================
# VALIDADE E DUPLICIDADE
# =========================


def arquivo_valido(caminho: pathlib.Path, tamanho_esperado=None) -> bool:
    """True se o arquivo existe, não está vazio e (se o tamanho esperado
    for conhecido) tem exatamente esse tamanho."""
    try:
        if not caminho.exists() or not caminho.is_file():
            return False

        tamanho = caminho.stat().st_size

        if tamanho <= 0:
            return False

        if tamanho_esperado is not None and tamanho != tamanho_esperado:
            return False

        return True
    except OSError:
        return False


def _variante_com_id(pasta: pathlib.Path, nome: str, id_mensagem: int):
    base = pathlib.Path(nome)
    return pasta / f"{base.stem}_{id_mensagem}{base.suffix}"


def decidir_destino(pasta: pathlib.Path, nome: str, id_mensagem: int,
                    tamanho_esperado=None):
    """Decide o caminho final de um vídeo dentro da pasta.

    Retorna ``(caminho, ja_baixado)``:

    - ``ja_baixado=True``: já existe um arquivo válido com esse nome
      (e tamanho, quando conhecido) — não baixar de novo.
    - ``ja_baixado=False``: baixar para ``caminho``. Se já existia um
      arquivo com o mesmo nome mas de outro vídeo (tamanho diferente),
      ``caminho`` é a variante com o ID da mensagem como sufixo.
    """
    candidato = pasta / nome

    if not candidato.exists():
        return candidato, False

    if candidato.stat().st_size == 0:
        # Arquivo vazio é sobra de falha, não um download:
        # baixa por cima dele, no mesmo nome.
        return candidato, False

    if arquivo_valido(candidato, tamanho_esperado):
        # Nome igual + válido (tamanho confere, quando conhecido).
        return candidato, True

    if tamanho_esperado is None and candidato.stat().st_size > 0:
        # Sem tamanho de referência, vale a regra por nome:
        # arquivo não vazio com esse nome é tratado como já baixado.
        return candidato, True

    # Existe, mas não corresponde a este vídeo (vazio ou tamanho
    # diferente): é uma colisão de nomes -> variante com o ID.
    variante = _variante_com_id(pasta, nome, id_mensagem)

    if not variante.exists():
        return variante, False

    if arquivo_valido(variante, tamanho_esperado):
        return variante, True

    if tamanho_esperado is None and variante.stat().st_size > 0:
        return variante, True

    contador = 2
    while True:
        base = pathlib.Path(nome)
        extra = pasta / f"{base.stem}_{id_mensagem}_{contador}{base.suffix}"
        if not extra.exists():
            return extra, False
        if arquivo_valido(extra, tamanho_esperado):
            return extra, True
        contador += 1


def caminho_parcial(destino: pathlib.Path) -> pathlib.Path:
    """Caminho do arquivo temporário de um download em andamento."""
    return destino.with_name(destino.name + ".part")


def remover_parcial(destino: pathlib.Path) -> None:
    """Remove o ``.part`` de um destino, sem falhar se não der."""
    parcial = caminho_parcial(destino)
    try:
        parcial.unlink(missing_ok=True)
    except OSError as erro:
        logger.warning("Não consegui remover o temporário %s: %s",
                       parcial, erro)


def finalizar_download(destino: pathlib.Path) -> pathlib.Path:
    """Promove o ``.part`` conferido a arquivo final."""
    parcial = caminho_parcial(destino)
    os.replace(parcial, destino)
    return destino


def nome_da_mensagem(mensagem) -> str:
    """Nome de arquivo de um vídeo: o original, quando houver.

    Sem nome original, gera ``video_<id da mensagem><extensão>`` a
    partir do tipo MIME (``.mp4`` se nem isso for conhecido).
    """
    arquivo = getattr(mensagem, "file", None)

    if arquivo is not None and getattr(arquivo, "name", None):
        return limpar_nome(pathlib.Path(arquivo.name).name)

    tipo_mime = getattr(arquivo, "mime_type", None) if arquivo else None
    extensao = mimetypes.guess_extension(tipo_mime) if tipo_mime else None

    if not extensao:
        extensao = ".mp4"

    return f"video_{mensagem.id}{extensao}"


def tamanho_da_mensagem(mensagem):
    """Tamanho em bytes esperado do vídeo, quando o Telegram informa."""
    arquivo = getattr(mensagem, "file", None)

    if arquivo is not None:
        tamanho = getattr(arquivo, "size", None)

        if isinstance(tamanho, int) and tamanho > 0:
            return tamanho

    return None


# =========================
# REGISTRO DE DOWNLOADS
# =========================


class RegistroDownloads:
    """Registro dos vídeos já baixados, em arquivo JSON.

    Fica na pasta raiz escolhida para os vídeos (fora do Git), com a
    chave ``"<id do destino>:<id da mensagem>"`` — o ID da mensagem
    sozinho se repete entre destinos diferentes. Registros antigos,
    só com o ID da mensagem, continuam sendo reconhecidos.

    É um reforço ao critério por nome: mesmo que o usuário reorganize
    as pastas por destino/tópico, um vídeo registrado cujo arquivo
    continua válido não é baixado outra vez.
    """

    def __init__(self, caminho_arquivo: pathlib.Path):
        self.caminho_arquivo = pathlib.Path(caminho_arquivo)
        self.dados = self._carregar()

    def _carregar(self):
        if not self.caminho_arquivo.exists():
            return {}

        try:
            dados = json.loads(
                self.caminho_arquivo.read_text(encoding="utf-8")
            )
            return dados if isinstance(dados, dict) else {}
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Não consegui ler o registro %s; vou reconstruir "
                "pelo que existe no disco.",
                self.caminho_arquivo,
            )
            return {}

    @staticmethod
    def _chave(id_destino, id_mensagem):
        return f"{id_destino}:{id_mensagem}"

    def _entrada(self, id_destino, id_mensagem):
        entrada = self.dados.get(self._chave(id_destino, id_mensagem))

        if entrada is None:
            # Formato antigo: só o ID da mensagem.
            entrada = self.dados.get(str(id_mensagem))

        return entrada if isinstance(entrada, dict) else None

    def ja_registrado(self, id_destino, id_mensagem) -> bool:
        """True se há registro cujo arquivo continua válido no disco."""
        entrada = self._entrada(id_destino, id_mensagem)

        if not entrada:
            return False

        caminho = entrada.get("arquivo")
        tamanho = entrada.get("tamanho")

        if not caminho:
            return False

        return arquivo_valido(pathlib.Path(caminho), tamanho)

    def registrar(self, id_destino, id_mensagem, caminho: pathlib.Path,
                  titulo_destino="", nome_topico=None):
        """Anota um download concluído e salva o registro."""
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            tamanho = None

        self.dados[self._chave(id_destino, id_mensagem)] = {
            "arquivo": str(caminho),
            "tamanho": tamanho,
            "destino": titulo_destino,
            "topico": nome_topico,
        }
        self.salvar()

    def salvar(self):
        """Salva o registro de forma atômica (escreve e substitui)."""
        try:
            self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
            temporario = self.caminho_arquivo.with_suffix(".json.tmp")
            temporario.write_text(
                json.dumps(self.dados, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporario, self.caminho_arquivo)
        except OSError as erro:
            logger.warning("Não consegui salvar o registro: %s", erro)
