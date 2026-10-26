"""Configurações do programa, lidas do ambiente / arquivo ``.env``.

Nenhuma credencial fica no código-fonte: ``ID_API`` e ``API_HASH`` são
lidos do ambiente (preenchidos a partir do ``.env`` pelo python-dotenv).
Os demais valores são padrões que a interface de terminal pode
sobrescrever a cada execução.
"""

import os
import pathlib
from dataclasses import dataclass, field
from typing import Mapping, Optional

from dotenv import load_dotenv

from .erros import ErroConfiguracao


@dataclass(frozen=True)
class Configuracao:
    """Configuração validada do programa."""

    api_id: int
    api_hash: str
    nome_sessao: str = "captura_videos"
    destino_padrao: Optional[str] = None
    pasta_padrao: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.home() / "Vídeos"
    )
    limite_padrao: Optional[int] = None


def _ler_inteiro_opcional(ambiente, nome):
    """Lê um inteiro opcional do ambiente (vazio/ausente = None)."""
    bruto = (ambiente.get(nome) or "").strip()

    if not bruto:
        return None

    try:
        valor = int(bruto)
    except ValueError:
        raise ErroConfiguracao(
            f"{nome} precisa ser um número inteiro. "
            f"Confira o valor no arquivo .env."
        ) from None

    if valor <= 0:
        raise ErroConfiguracao(
            f"{nome} precisa ser maior que zero (ou ficar vazio)."
        )

    return valor


def carregar_configuracao(ambiente: Optional[Mapping[str, str]] = None):
    """Carrega e valida a configuração.

    ``ambiente`` pode ser informado (útil em testes); por padrão usa o
    ambiente do processo, após carregar o arquivo ``.env``.
    """
    if ambiente is None:
        load_dotenv()
        ambiente = os.environ

    bruto_id = (ambiente.get("ID_API") or "").strip()

    if not bruto_id:
        raise ErroConfiguracao(
            "Configure ID_API no arquivo .env "
            "(veja o arquivo .env.example)."
        )

    try:
        api_id = int(bruto_id)
    except ValueError:
        raise ErroConfiguracao(
            "ID_API precisa ser um número inteiro. "
            "Confira o valor no arquivo .env."
        ) from None

    api_hash = (ambiente.get("API_HASH") or "").strip()

    if not api_hash:
        raise ErroConfiguracao(
            "Configure API_HASH no arquivo .env "
            "(veja o arquivo .env.example)."
        )

    # DESTINO é o nome atual; NOME_GRUPO é aceito por compatibilidade.
    destino = (
        (ambiente.get("DESTINO") or "").strip()
        or (ambiente.get("NOME_GRUPO") or "").strip()
        or None
    )

    pasta_bruta = (ambiente.get("PASTA_VIDEOS") or "").strip()
    pasta_padrao = (
        pathlib.Path(pasta_bruta).expanduser()
        if pasta_bruta
        else pathlib.Path.home() / "Vídeos"
    )

    nome_sessao = (
        (ambiente.get("NOME_SESSAO") or "").strip() or "captura_videos"
    )

    return Configuracao(
        api_id=api_id,
        api_hash=api_hash,
        nome_sessao=nome_sessao,
        destino_padrao=destino,
        pasta_padrao=pasta_padrao,
        limite_padrao=_ler_inteiro_opcional(ambiente, "LIMITE_MENSAGENS"),
    )
