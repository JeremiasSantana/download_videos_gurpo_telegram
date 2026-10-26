"""
Robô que baixa os vídeos de um grupo do Telegram, organizados por tópico.

Melhorias desta versão:
- Não baixa de novo o que já foi baixado: antes de baixar, confere o arquivo
  no disco (existência + tamanho) e um registro de progresso salvo em disco.
- Download é feito primeiro para um arquivo temporário ".part" e só vira o
  arquivo final depois de concluir e conferir o tamanho. Se o processo for
  interrompido no meio, nenhum vídeo fica "meio baixado" marcado como pronto.
- Ctrl+C (ou outro cancelamento) encerra de forma limpa, sem traceback:
  o parcial é apagado, o progresso é salvo e, ao rodar de novo, o robô
  continua de onde parou.
- Um vídeo que falha não derruba o robô: ele tenta de novo algumas vezes
  (respeitando o FloodWait do Telegram) e, se mesmo assim falhar, registra
  o erro e segue para o próximo vídeo.
- ID_API é convertido para número (o Telethon exige int) e todas as
  configurações podem vir do .env, sem precisar mexer no código.

SEGURANÇA:
- ID_API e API_HASH ficam SOMENTE no arquivo .env (nunca no código e
  nunca no Git — o .env está no .gitignore).
- O arquivo de sessão (*.session) funciona como uma senha da sua conta:
  nunca compartilhe esse arquivo nem suba ele para o GitHub.
  Ele também está coberto pelo .gitignore ("*.session").
"""

import asyncio
import json
import mimetypes
import os
import pathlib
import sys

from dotenv import load_dotenv
from telethon import TelegramClient, functions
from telethon.errors import FloodWaitError


# =========================
# CONFIGURAÇÕES
# =========================

load_dotenv()


def _ler_id_api():
    """Lê e valida o ID_API do .env, convertendo para int."""
    bruto = (os.getenv("ID_API") or "").strip()

    if not bruto:
        raise ValueError("Configure ID_API no arquivo .env.")

    try:
        return int(bruto)
    except ValueError:
        raise ValueError(
            "ID_API precisa ser um número inteiro. "
            "Confira o valor no arquivo .env."
        ) from None


def _ler_limite():
    """Lê o limite opcional de mensagens do .env (vazio = sem limite)."""
    bruto = (os.getenv("LIMITE_MENSAGENS") or "").strip()

    if not bruto:
        return None

    try:
        valor = int(bruto)
    except ValueError:
        raise ValueError(
            "LIMITE_MENSAGENS precisa ser um número inteiro "
            "(ou ficar vazio para baixar todo o histórico)."
        ) from None

    return valor if valor > 0 else None


ID_API = _ler_id_api()

API_HASH = (os.getenv("API_HASH") or "").strip()

if not API_HASH:
    raise ValueError("Configure API_HASH no arquivo .env.")

# Nome visível do grupo. Pode ser trocado no .env (NOME_GRUPO), sem mexer aqui.
NOME_GRUPO = os.getenv("NOME_GRUPO", "SuperTopicos 25 em 1 - VIP 🍓")

# Pasta onde os vídeos são salvos. Padrão: ~/Vídeos. Pode ser trocada
# no .env (PASTA_VIDEOS), sem depender de um caminho fixo de uma máquina.
CAMINHO_BASE = pathlib.Path(
    os.getenv("PASTA_VIDEOS", str(pathlib.Path.home() / "Vídeos"))
).expanduser()

# None significa percorrer todo o histórico acessível.
LIMITE = _ler_limite()

# Nome da sessão do Telethon (gera o arquivo "<nome>.session" na pasta
# onde o script é executado). Nome simples, sem acentos, para evitar
# problemas de codificação — e coberto pelo .gitignore.
NOME_SESSAO = os.getenv("NOME_SESSAO", "captura_videos")

# Quantas vezes tentar baixar o mesmo vídeo antes de desistir dele
# (o robô continua nos próximos vídeos mesmo se um falhar).
MAX_TENTATIVAS = 3

# Registro de progresso: fica junto dos vídeos (fora do repositório),
# mapeando o ID da mensagem para o arquivo baixado e o seu tamanho.
ARQUIVO_ESTADO = CAMINHO_BASE / ".baixados.json"


# =========================
# REGISTRO DE PROGRESSO
# =========================


def carregar_estado():
    """Carrega o registro de vídeos já baixados."""
    if not ARQUIVO_ESTADO.exists():
        return {}

    try:
        dados = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        print(
            "[AVISO] Não consegui ler o registro de progresso "
            f"({ARQUIVO_ESTADO}). Vou reconstruir pelo que já "
            "existe no disco."
        )
        return {}


def salvar_estado(estado):
    """Salva o registro de forma atômica (escreve e substitui)."""
    try:
        CAMINHO_BASE.mkdir(parents=True, exist_ok=True)
        temporario = ARQUIVO_ESTADO.with_suffix(".json.tmp")
        temporario.write_text(
            json.dumps(estado, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporario, ARQUIVO_ESTADO)
    except OSError as erro:
        print(f"[AVISO] Não consegui salvar o progresso: {erro}")


def arquivo_completo(caminho, tamanho_esperado=None):
    """Confere se o arquivo existe e parece completo."""
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


def ja_foi_baixado(estado, id_mensagem, destino, tamanho_esperado):
    """
    Decide se o vídeo já foi baixado, por duas vias:
    1. O arquivo final existe no destino com o tamanho esperado;
    2. O registro de progresso aponta para um arquivo completo.
    """
    if arquivo_completo(destino, tamanho_esperado):
        return True

    registro = estado.get(str(id_mensagem))

    if isinstance(registro, dict):
        caminho_registrado = registro.get("arquivo")
        tamanho_registrado = registro.get("tamanho")

        if caminho_registrado and arquivo_completo(
            pathlib.Path(caminho_registrado), tamanho_registrado
        ):
            return True

    return False


# =========================
# TRATAMENTO DE NOMES
# =========================


def limpar_nome(nome):
    """Remove caracteres inválidos para nome de pasta/arquivo."""
    caracteres_invalidos = '<>:"/\\|?*'

    for caractere in caracteres_invalidos:
        nome = nome.replace(caractere, "_")

    return nome.strip().rstrip(".") or "Sem nome"


# =========================
# LOCALIZAR O GRUPO
# =========================


async def localizar_grupo(client, nome_grupo):
    """Localiza um grupo pelo nome visível nos diálogos."""
    nome_procurado = nome_grupo.strip().casefold()

    async for dialogo in client.iter_dialogs():
        if (dialogo.name or "").strip().casefold() == nome_procurado:
            return dialogo.entity

    raise ValueError(
        f"O grupo '{nome_grupo}' não foi encontrado "
        "nos diálogos da conta autenticada."
    )


# =========================
# BUSCAR OS TÓPICOS
# =========================


async def buscar_topicos(client, entidade):
    """Obtém os IDs e os nomes dos tópicos do fórum."""
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

        # Verifica se todos os tópicos foram consultados.
        if len(topicos) >= resposta.count:
            break

        # Prepara a referência para a próxima página.
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

        # Evita repetir indefinidamente a mesma página.
        if novos_offsets == offsets_atuais:
            break

        if len(topicos) == quantidade_anterior:
            break

        offset_date, offset_id, offset_topic = novos_offsets

    return topicos


# =========================
# IDENTIFICAR O TÓPICO
# =========================


def identificar_topico(mensagem, topicos):
    """Identifica o tópico associado à mensagem."""
    # A própria mensagem pode ser a mensagem inicial do tópico.
    if mensagem.id in topicos:
        return topicos[mensagem.id]

    cabecalho_resposta = mensagem.reply_to

    if cabecalho_resposta:
        # Obtém o ID da mensagem que iniciou a conversa.
        id_topico = getattr(cabecalho_resposta, "reply_to_top_id", None)

        # Alternativa para respostas diretas à mensagem inicial.
        if id_topico is None:
            id_resposta = getattr(
                cabecalho_resposta, "reply_to_msg_id", None
            )

            if id_resposta in topicos:
                id_topico = id_resposta

        if id_topico in topicos:
            return topicos[id_topico]

    # Usa o título do tópico Geral, se estiver disponível.
    return topicos.get(1, "Geral")


# =========================
# VERIFICAR SE É UM VÍDEO
# =========================


def mensagem_e_video(mensagem):
    """Verifica se a mensagem contém um vídeo."""
    if mensagem.video:
        return True

    # Também considera arquivos enviados como documentos
    # cujo tipo MIME identifica uma mídia de vídeo.
    arquivo = mensagem.file

    return bool(
        arquivo
        and arquivo.mime_type
        and arquivo.mime_type.startswith("video/")
    )


def nome_destino(mensagem, pasta):
    """Monta o caminho final do vídeo (pasta + nome do arquivo)."""
    # Obtém o nome original do arquivo, quando disponível.
    if mensagem.file and mensagem.file.name:
        nome_arquivo = pathlib.Path(mensagem.file.name).name
    else:
        # Tenta determinar a extensão pelo tipo MIME.
        tipo_mime = mensagem.file.mime_type if mensagem.file else None
        extensao = (
            mimetypes.guess_extension(tipo_mime) if tipo_mime else None
        )

        if not extensao:
            extensao = ".mp4"

        nome_arquivo = f"video_{mensagem.id}{extensao}"

    nome_arquivo = limpar_nome(nome_arquivo)

    # Adiciona o ID da mensagem ao nome do arquivo.
    return pasta / f"{mensagem.id}_{nome_arquivo}"


def tamanho_esperado(mensagem):
    """Tamanho em bytes que o vídeo deve ter, quando o Telegram informa."""
    arquivo = mensagem.file

    if arquivo is not None:
        tamanho = getattr(arquivo, "size", None)

        if isinstance(tamanho, int) and tamanho > 0:
            return tamanho

    return None


# =========================
# BAIXAR UM VÍDEO
# =========================


async def baixar_um_video(mensagem, destino, esperado):
    """
    Baixa um vídeo para um arquivo temporário ".part" e, somente após
    concluir e conferir o tamanho, renomeia para o destino final.

    Levanta a exceção em caso de falha (quem chama decide tentar de
    novo ou passar para o próximo). Em caso de cancelamento, apaga o
    parcial antes de propagar, para nada ficar marcado como pronto.
    """
    parcial = destino.with_name(destino.name + ".part")

    try:
        caminho = await mensagem.download_media(file=str(parcial))
    except asyncio.CancelledError:
        parcial.unlink(missing_ok=True)
        raise

    if not caminho or not parcial.exists():
        parcial.unlink(missing_ok=True)
        raise RuntimeError("O download não gerou arquivo.")

    if esperado is not None and parcial.stat().st_size != esperado:
        tamanho_baixado = parcial.stat().st_size
        parcial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Tamanho divergente: esperado {esperado} bytes, "
            f"baixado {tamanho_baixado} bytes."
        )

    # Download conferido: agora sim vira o arquivo final.
    os.replace(parcial, destino)
    return destino


async def baixar_com_tentativas(mensagem, destino, esperado):
    """
    Tenta baixar um vídeo até MAX_TENTATIVAS vezes.

    - FloodWait (limite do Telegram): espera o tempo pedido e tenta de
      novo, sem gastar as tentativas.
    - Outros erros: espera um pouco (backoff) e tenta de novo.
    Retorna True se baixou, False se desistiu desse vídeo.
    """
    tentativas = 0

    while tentativas < MAX_TENTATIVAS:
        try:
            await baixar_um_video(mensagem, destino, esperado)
            return True
        except FloodWaitError as erro:
            espera = int(getattr(erro, "seconds", 0)) + 1
            print(
                f"[AGUARDANDO] Telegram pediu pausa de {espera}s "
                f"(mensagem {mensagem.id})."
            )
            await asyncio.sleep(espera)
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # noqa: BLE001 - um vídeo não pode parar os demais
            tentativas += 1

            if tentativas < MAX_TENTATIVAS:
                espera = 2**tentativas
                print(
                    f"[RETRY] Mensagem {mensagem.id}: {erro} "
                    f"Tentativa {tentativas + 1}/{MAX_TENTATIVAS} "
                    f"em {espera}s."
                )
                await asyncio.sleep(espera)
            else:
                print(
                    f"[ERRO] Mensagem {mensagem.id}: desisti após "
                    f"{MAX_TENTATIVAS} tentativas. Último erro: {erro}"
                )

    return False


# =========================
# BAIXAR OS VÍDEOS
# =========================


async def baixar_videos(client, grupo, limite, estado):
    """Percorre o grupo e baixa os vídeos que ainda faltam."""
    # Localiza o grupo pelo nome visível.
    entidade = await localizar_grupo(client, grupo)

    # Obtém os tópicos disponíveis.
    topicos = await buscar_topicos(client, entidade)

    print(f"Tópicos encontrados: {len(topicos)}")

    baixados = 0
    pulados = 0
    erros = 0

    try:
        # None mantém a leitura de todo o histórico acessível.
        async for mensagem in client.iter_messages(entidade, limit=limite):
            # Ignora mensagens que não contêm vídeos.
            if not mensagem_e_video(mensagem):
                continue

            # Identifica a pasta correspondente ao tópico.
            nome_topico = identificar_topico(mensagem, topicos)

            pasta = CAMINHO_BASE / limpar_nome(nome_topico)
            pasta.mkdir(parents=True, exist_ok=True)

            destino = nome_destino(mensagem, pasta)
            esperado = tamanho_esperado(mensagem)

            # >>> A verificação que faltava: já baixou? Então pula. <<<
            if ja_foi_baixado(estado, mensagem.id, destino, esperado):
                pulados += 1

                # Garante o registro, para as próximas execuções
                # nem precisarem conferir arquivo por arquivo.
                if str(mensagem.id) not in estado and destino.exists():
                    estado[str(mensagem.id)] = {
                        "arquivo": str(destino),
                        "tamanho": destino.stat().st_size,
                        "topico": nome_topico,
                    }
                    salvar_estado(estado)

                continue

            sucesso = await baixar_com_tentativas(
                mensagem, destino, esperado
            )

            if sucesso:
                baixados += 1
                estado[str(mensagem.id)] = {
                    "arquivo": str(destino),
                    "tamanho": destino.stat().st_size,
                    "topico": nome_topico,
                }
                salvar_estado(estado)
                print(f"[OK] {nome_topico}: {destino}")
            else:
                erros += 1
    except asyncio.CancelledError:
        # Ctrl+C no meio do caminho: o progresso já foi salvo a cada
        # vídeo; aqui só garantimos uma última gravação antes de sair.
        salvar_estado(estado)
        raise

    print("\nDownload concluído!")
    print(f"Baixados agora: {baixados}")
    print(f"Pulados (já existiam): {pulados}")
    print(f"Com erro: {erros}")

    return {"baixados": baixados, "pulados": pulados, "erros": erros}


# =========================
# EXECUÇÃO PRINCIPAL
# =========================


async def main():
    CAMINHO_BASE.mkdir(parents=True, exist_ok=True)
    estado = carregar_estado()

    async with TelegramClient(NOME_SESSAO, ID_API, API_HASH) as client:
        await baixar_videos(client, NOME_GRUPO, LIMITE, estado)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Isso acontece quando você aperta Ctrl+C: não é um erro do
        # código. O parcial é apagado e o progresso fica salvo, então
        # é só rodar de novo que ele continua de onde parou,
        # sem baixar tudo outra vez.
        print(
            "\nInterrompido por você (Ctrl+C). "
            "O que já foi baixado está salvo."
        )
        print("Rode de novo para continuar de onde parou.")
        sys.exit(130)
