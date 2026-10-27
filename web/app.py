"""Backend web (FastAPI) do baixador de vídeos do Telegram.

Versão 1 — uso pessoal e local:
- Um único usuário/uma única sessão do Telegram por vez.
- Reaproveita o motor existente em ``uteis.funcoes`` sem alterá-lo:
  ``resolver_destino``, ``listar_destinos``, ``buscar_topicos`` e
  ``baixar_destino``.
- A sessão do Telegram (arquivo ``*.session``) vive no servidor, na
  pasta de onde o servidor é iniciado, e nunca vai para o Git.
- O progresso é acompanhado pelas mensagens de log do motor
  (logger ``baixador_telegram``), consultadas pela página via polling.

Execute a partir da raiz do projeto:

    uvicorn web.app:app --host 127.0.0.1 --port 8000

Manter o host em 127.0.0.1: sem isso, qualquer pessoa da rede poderia
usar a sua sessão do Telegram pelas páginas.
"""

import asyncio
import collections
import logging
import pathlib
import sys

# Permite rodar também a partir de dentro da pasta web/.
_RAIZ = pathlib.Path(__file__).resolve().parents[1]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.errors import SessionPasswordNeededError  # noqa: E402

from uteis.funcoes import arquivos  # noqa: E402
from uteis.funcoes.baixador import OpcoesDownload, baixar_destino  # noqa: E402
from uteis.funcoes.configuracao import carregar_configuracao  # noqa: E402
from uteis.funcoes.destinos import listar_destinos, resolver_destino  # noqa: E402
from uteis.funcoes.erros import (  # noqa: E402
    ErroConfiguracao,
    ErroDestino,
    ErroDestinoAmbiguo,
    ErroPasta,
)
from uteis.funcoes.topicos import buscar_topicos  # noqa: E402

logger = logging.getLogger("baixador_telegram")

_EXTENSOES_VIDEO = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}

# =========================
# ESTADO (usuário único)
# =========================

_cliente = None
_config = None
_erro_config = None
_login_pendente = {"telefone": None, "hash": None}
_cache_destinos = {}  # str(id) -> Destino já resolvido
_cache_topicos = {}   # str(id do destino) -> {id_topico: titulo}

_download = {
    "estado": "parado",  # parado | rodando | concluido | erro | cancelado
    "stats": None,
    "erro": None,
}
_tarefa_download = None  # asyncio.Task do download em andamento

# Conversas (destinos) carregadas logo após o login: a lista fica
# pronta em memória para a seta do campo mostrar tudo na hora.
_cache_conversas = {"lista": None, "tarefa": None}


class _CapturaLogs(logging.Handler):
    """Guarda as últimas mensagens de log do motor para a página."""

    def __init__(self):
        super().__init__()
        self.mensagens = collections.deque(maxlen=300)

    def emit(self, record):
        try:
            self.mensagens.append(self.format(record))
        except Exception:
            pass


_captura = _CapturaLogs()
_captura.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
)
logger.addHandler(_captura)
logger.setLevel(logging.INFO)


# =========================
# AJUDANTES
# =========================


def _obter_config():
    global _config, _erro_config
    if _config is None and _erro_config is None:
        try:
            _config = carregar_configuracao()
        except ErroConfiguracao as erro:
            _erro_config = str(erro)
    if _config is None:
        raise HTTPException(
            status_code=500,
            detail=f"Configuração incompleta: {_erro_config}",
        )
    return _config


async def _obter_cliente():
    """Cria (se preciso) e conecta o cliente do Telethon."""
    global _cliente
    config = _obter_config()
    if _cliente is None:
        _cliente = TelegramClient(
            config.nome_sessao, config.api_id, config.api_hash
        )
    if not _cliente.is_connected():
        try:
            await _cliente.connect()
        except Exception as erro:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Não consegui conectar ao Telegram. Confira a "
                    "internet e as credenciais do .env. "
                    f"Detalhe técnico: {erro}"
                ),
            ) from erro
    return _cliente


async def _cliente_autorizado():
    cliente = await _obter_cliente()
    if not await cliente.is_user_authorized():
        raise HTTPException(
            status_code=401,
            detail="Faça login no Telegram primeiro (passo 1 da página).",
        )
    return cliente


def _resumo_destino(destino):
    return {
        "id": destino.id,
        "titulo": destino.titulo,
        "tipo": destino.tipo.value,
        "tem_topicos": destino.tem_topicos,
        "username": destino.username,
    }


def _guardar_destino(destino):
    _cache_destinos[str(destino.id)] = destino
    return destino


async def _resolver(cliente, entrada):
    """Resolve reaproveitando a cache quando a entrada é um ID já visto."""
    texto = (entrada or "").strip()
    if texto in _cache_destinos:
        return _cache_destinos[texto]
    try:
        destino = await resolver_destino(cliente, texto)
    except ErroDestinoAmbiguo as erro:
        raise HTTPException(
            status_code=409,
            detail={
                "mensagem": str(erro),
                "candidatos": [
                    _resumo_destino(_guardar_destino(c))
                    for c in erro.candidatos
                ],
            },
        ) from erro
    except ErroDestino as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    return _guardar_destino(destino)


async def _percorrer_conversas():
    """Percorre todo o histórico de conversas do Telegram e guarda
    a lista de destinos em memória.

    Roda em segundo plano assim que o login é autorizado: quando o
    usuário clica na seta do campo, a lista já está pronta — sem
    espera e sem risco de vir vazia por uma busca feita na pressa.
    """
    try:
        cliente = await _cliente_autorizado()
        lista = await listar_destinos(cliente)
        _cache_conversas["lista"] = lista
        for destino in lista:
            _guardar_destino(destino)
        logger.info(
            "Conversas carregadas após o login: %d destinos.",
            len(lista),
        )
    except Exception as erro:  # não derruba o login por causa disso
        logger.warning("Não consegui carregar as conversas: %s", erro)
    finally:
        _cache_conversas["tarefa"] = None


def _agendar_carga_conversas():
    """Dispara a carga das conversas se ainda não foi feita."""
    if (
        _cache_conversas["lista"] is None
        and _cache_conversas["tarefa"] is None
    ):
        _cache_conversas["tarefa"] = asyncio.create_task(
            _percorrer_conversas()
        )


# =========================
# API
# =========================

app = FastAPI(title="Baixador de Vídeos do Telegram")


@app.get("/api/status")
async def status():
    resultado = {
        "configurado": True,
        "erro_config": None,
        "conectado": False,
        "autorizado": False,
        "usuario": None,
        "pasta_padrao": None,
        "download": _download["estado"],
    }
    try:
        config = _obter_config()
        resultado["pasta_padrao"] = str(config.pasta_padrao)
    except HTTPException as erro:
        resultado["configurado"] = False
        resultado["erro_config"] = erro.detail
        return resultado

    if _cliente is not None and _cliente.is_connected():
        resultado["conectado"] = True
        if await _cliente.is_user_authorized():
            resultado["autorizado"] = True
            _agendar_carga_conversas()
            eu = await _cliente.get_me()
            resultado["usuario"] = {
                "nome": getattr(eu, "first_name", None),
                "username": getattr(eu, "username", None),
            }
    return resultado


class PedidoCodigo(BaseModel):
    telefone: str


@app.post("/api/login/codigo")
async def login_codigo(pedido: PedidoCodigo):
    cliente = await _obter_cliente()
    if await cliente.is_user_authorized():
        _agendar_carga_conversas()
        return {"autorizado": True}
    telefone = pedido.telefone.strip()
    if not telefone:
        raise HTTPException(status_code=400, detail="Informe o telefone.")
    try:
        enviado = await cliente.send_code_request(telefone)
    except Exception as erro:
        raise HTTPException(
            status_code=400,
            detail=f"Não consegui enviar o código: {erro}",
        ) from erro
    _login_pendente["telefone"] = telefone
    _login_pendente["hash"] = enviado.phone_code_hash
    return {"autorizado": False, "codigo_enviado": True}


class PedidoConfirmar(BaseModel):
    codigo: str
    senha: str | None = None


@app.post("/api/login/confirmar")
async def login_confirmar(pedido: PedidoConfirmar):
    cliente = await _obter_cliente()
    if await cliente.is_user_authorized():
        _agendar_carga_conversas()
        return {"autorizado": True}
    if not _login_pendente["telefone"]:
        raise HTTPException(
            status_code=400,
            detail="Peça o código primeiro (passo 1).",
        )
    try:
        await cliente.sign_in(
            _login_pendente["telefone"],
            pedido.codigo.strip(),
            phone_code_hash=_login_pendente["hash"],
        )
    except SessionPasswordNeededError:
        if not pedido.senha:
            return {"autorizado": False, "precisa_senha": True}
        try:
            await cliente.sign_in(password=pedido.senha)
        except Exception as erro:
            raise HTTPException(
                status_code=400, detail=f"Senha não aceita: {erro}"
            ) from erro
    except Exception as erro:
        raise HTTPException(
            status_code=400, detail=f"Código não aceito: {erro}"
        ) from erro
    _login_pendente["telefone"] = None
    _login_pendente["hash"] = None
    # Login verificado e autorizado: já percorre todas as conversas
    # e deixa a lista pronta para quando a seta for clicada.
    _agendar_carga_conversas()
    return {"autorizado": True}


@app.get("/api/destinos")
async def destinos():
    # Lista pronta do pós-login: responde na hora.
    if _cache_conversas["lista"] is not None:
        return [_resumo_destino(d) for d in _cache_conversas["lista"]]
    # Carga do pós-login ainda rodando: espera ela terminar.
    tarefa = _cache_conversas["tarefa"]
    if tarefa is not None:
        await tarefa
        if _cache_conversas["lista"] is not None:
            return [
                _resumo_destino(d) for d in _cache_conversas["lista"]
            ]
    # Sem carga (ex.: login feito antes desta versão): busca agora
    # e guarda para as próximas vezes.
    cliente = await _cliente_autorizado()
    lista = await listar_destinos(cliente)
    _cache_conversas["lista"] = lista
    return [_resumo_destino(_guardar_destino(d)) for d in lista]


class PedidoDestino(BaseModel):
    entrada: str


@app.post("/api/preparar")
async def preparar(pedido: PedidoDestino):
    """Resolve o destino e, se for grupo com tópicos, lista os tópicos."""
    cliente = await _cliente_autorizado()
    destino = await _resolver(cliente, pedido.entrada)
    topicos = []
    if destino.tem_topicos:
        mapa = await buscar_topicos(cliente, destino.entidade)
        _cache_topicos[str(destino.id)] = mapa
        topicos = [
            {"id": id_topico, "titulo": titulo}
            for id_topico, titulo in mapa.items()
        ]
    return {"destino": _resumo_destino(destino), "topicos": topicos}


class PedidoBaixar(BaseModel):
    entrada: str
    topico_id: int | None = None
    limite: int | None = None
    pasta: str | None = None


async def _executar_download(pedido: PedidoBaixar):
    _download["estado"] = "rodando"
    _download["stats"] = None
    _download["erro"] = None
    _captura.mensagens.clear()
    try:
        config = _obter_config()
        cliente = await _cliente_autorizado()
        destino = await _resolver(cliente, pedido.entrada)

        if pedido.pasta:
            pasta_base = arquivos.garantir_pasta(
                arquivos.resolver_caminho(pedido.pasta)
            )
        else:
            pasta_base = arquivos.garantir_pasta(config.pasta_padrao)

        topicos = _cache_topicos.get(str(destino.id))
        registro = arquivos.RegistroDownloads(pasta_base / ".baixados.json")
        opcoes = OpcoesDownload(
            pasta_base=pasta_base,
            limite=pedido.limite,
            topico_id=pedido.topico_id,
        )
        stats = await baixar_destino(
            cliente, destino, opcoes, registro, topicos=topicos
        )
        registro.salvar()
        _download["stats"] = {
            "analisadas": stats.analisadas,
            "baixados": stats.baixados,
            "pulados": stats.pulados,
            "erros": stats.erros,
        }
        _download["estado"] = "concluido"
    except asyncio.CancelledError:
        # Cancelado pelo botão da página: o motor já salvou o
        # registro e removeu o arquivo parcial do vídeo interrompido;
        # o que foi baixado antes continua valendo.
        _download["estado"] = "cancelado"
        logger.info("Download cancelado pelo usuário.")
    except Exception as erro:  # devolve o erro para a página, sem derrubar
        _download["estado"] = "erro"
        _download["erro"] = getattr(erro, "detail", None) or str(erro)
        logger.error("Download pela web falhou: %s", erro)


@app.post("/api/baixar")
async def baixar(pedido: PedidoBaixar):
    global _tarefa_download
    if _download["estado"] == "rodando":
        raise HTTPException(
            status_code=409, detail="Já há um download em andamento."
        )
    if pedido.limite is not None and pedido.limite <= 0:
        raise HTTPException(
            status_code=400, detail="O limite precisa ser maior que zero."
        )
    await _cliente_autorizado()
    _tarefa_download = asyncio.create_task(_executar_download(pedido))
    return {"iniciado": True}


@app.post("/api/cancelar")
async def cancelar():
    """Cancela o download em andamento (botão Cancelar da página)."""
    if (
        _download["estado"] != "rodando"
        or _tarefa_download is None
        or _tarefa_download.done()
    ):
        raise HTTPException(
            status_code=409,
            detail="Não há download em andamento para cancelar.",
        )
    _tarefa_download.cancel()
    return {"cancelando": True}


@app.get("/api/progresso")
async def progresso():
    return {
        "estado": _download["estado"],
        "stats": _download["stats"],
        "erro": _download["erro"],
        "log": list(_captura.mensagens),
    }


def _pasta_base_segura(pasta: str | None):
    if pasta:
        return arquivos.resolver_caminho(pasta).resolve()
    config = _obter_config()
    return pathlib.Path(config.pasta_padrao).expanduser().resolve()


@app.get("/api/arquivos")
async def listar_arquivos(pasta: str | None = Query(default=None)):
    base = _pasta_base_segura(pasta)
    if not base.exists():
        return {"pasta": str(base), "arquivos": []}
    encontrados = []
    for caminho in sorted(base.rglob("*")):
        if (
            caminho.is_file()
            and caminho.suffix.lower() in _EXTENSOES_VIDEO
            and not caminho.name.endswith(".part")
        ):
            encontrados.append(
                {
                    "caminho": str(caminho.relative_to(base)),
                    "tamanho": caminho.stat().st_size,
                }
            )
    return {"pasta": str(base), "arquivos": encontrados}


@app.get("/api/arquivos/baixar")
async def baixar_arquivo(
    caminho: str = Query(...), pasta: str | None = Query(default=None)
):
    base = _pasta_base_segura(pasta)
    alvo = (base / caminho).resolve()
    if base not in alvo.parents and alvo != base:
        raise HTTPException(status_code=403, detail="Caminho não permitido.")
    if not alvo.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(alvo, filename=alvo.name)


# =========================
# HISTÓRICO DE VÍDEOS BAIXADOS
# =========================
# O histórico vem do registro ``.baixados.json`` da pasta de vídeos
# (o mesmo que o motor usa para não baixar de novo). Agrupa por local
# de origem (canal, grupo ou conversa). Excluir o histórico apaga só
# os registros daquele local — os arquivos continuam na pasta, mas,
# sem o registro, podem ser baixados de novo no futuro.


def _grupos_historico(base: pathlib.Path):
    registro = arquivos.RegistroDownloads(base / ".baixados.json")
    grupos = {}

    for chave_registro, entrada in registro.dados.items():
        if not isinstance(entrada, dict):
            continue

        caminho_bruto = entrada.get("arquivo")
        if not caminho_bruto:
            continue

        caminho = pathlib.Path(caminho_bruto)
        if not arquivos.arquivo_valido(caminho, entrada.get("tamanho")):
            continue

        titulo = entrada.get("destino") or "Sem origem definida"
        id_destino = (
            chave_registro.split(":", 1)[0]
            if ":" in chave_registro
            else ""
        )
        chave_grupo = f"{id_destino}|{titulo}"

        grupo = grupos.setdefault(
            chave_grupo,
            {
                "chave": chave_grupo,
                "destino": titulo,
                "videos": [],
                "_chaves": [],
            },
        )
        grupo["_chaves"].append(chave_registro)

        try:
            relativo = str(caminho.relative_to(base))
        except ValueError:
            relativo = None

        grupo["videos"].append(
            {
                "nome": caminho.name,
                "topico": entrada.get("topico"),
                "tamanho": entrada.get("tamanho")
                or caminho.stat().st_size,
                "caminho": relativo,
            }
        )

    resultado = []
    for grupo in grupos.values():
        grupo["videos"].sort(key=lambda v: v["nome"].casefold())
        grupo["total"] = len(grupo["videos"])
        grupo["tamanho_total"] = sum(
            v["tamanho"] or 0 for v in grupo["videos"]
        )
        resultado.append(grupo)

    resultado.sort(key=lambda g: g["destino"].casefold())
    return resultado


@app.get("/api/historico")
async def historico(pasta: str | None = Query(default=None)):
    base = _pasta_base_segura(pasta)
    grupos = [
        {k: v for k, v in grupo.items() if not k.startswith("_")}
        for grupo in _grupos_historico(base)
    ]
    return {"pasta": str(base), "grupos": grupos}


@app.delete("/api/historico")
async def excluir_historico(
    chave: str = Query(...), pasta: str | None = Query(default=None)
):
    base = _pasta_base_segura(pasta)
    alvo = next(
        (g for g in _grupos_historico(base) if g["chave"] == chave), None
    )
    if alvo is None:
        raise HTTPException(
            status_code=404, detail="Histórico desse local não encontrado."
        )
    registro = arquivos.RegistroDownloads(base / ".baixados.json")
    for chave_registro in alvo["_chaves"]:
        registro.dados.pop(chave_registro, None)
    registro.salvar()
    return {"removidos": len(alvo["_chaves"]), "destino": alvo["destino"]}


# Páginas (HTML/CSS/JS) — montado por último para não sombrear a API.
app.mount(
    "/",
    StaticFiles(
        directory=pathlib.Path(__file__).parent / "static", html=True
    ),
    name="static",
)
