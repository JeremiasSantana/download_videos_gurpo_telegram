"use strict";

const $ = (id) => document.getElementById(id);

function mostrarErro(texto) {
  $("mensagem").textContent = texto || "";
}

async function chamar(url, opcoes) {
  const resposta = await fetch(url, opcoes);
  let dados = null;
  try { dados = await resposta.json(); } catch { /* sem corpo */ }
  if (!resposta.ok) {
    let detalhe = dados && dados.detail;
    if (detalhe && typeof detalhe === "object") {
      // Ambiguidade de destino: oferece os candidatos na lista.
      if (Array.isArray(detalhe.candidatos)) {
        preencherDestinos(detalhe.candidatos);
        throw new Error(detalhe.mensagem + " Escolha um na lista abaixo do botão Listar.");
      }
      detalhe = detalhe.mensagem || JSON.stringify(detalhe);
    }
    throw new Error(detalhe || ("Erro " + resposta.status));
  }
  return dados;
}

const jsonPost = (corpo) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(corpo),
});

function preencherDestinos(destinos) {
  const select = $("lista-destinos");
  select.innerHTML = "";
  for (const d of destinos) {
    const opt = document.createElement("option");
    opt.value = String(d.id);
    opt.textContent = `${d.titulo} (${d.tipo})`;
    select.appendChild(opt);
  }
  select.hidden = destinos.length === 0;
  if (destinos.length) $("destino").value = String(destinos[0].id);
}

// ---------- Status / login ----------
async function atualizarStatus() {
  try {
    const s = await chamar("/api/status");
    if (!s.configurado) {
      $("status").textContent = "Configuração incompleta: " + s.erro_config;
      return;
    }
    if (s.pasta_padrao && !$("pasta").value) $("pasta").value = s.pasta_padrao;
    if (s.autorizado) {
      $("status").textContent = "Conectado ao Telegram.";
      $("login-form").hidden = true;
      $("login-ok").hidden = false;
      $("login-ok").textContent =
        "Logado como " + (s.usuario.nome || "") +
        (s.usuario.username ? " (@" + s.usuario.username + ")" : "");
    } else {
      $("status").textContent = "Faça login no Telegram para começar.";
    }
  } catch (e) { mostrarErro(e.message); }
}

$("btn-codigo").addEventListener("click", async () => {
  mostrarErro("");
  try {
    const r = await chamar("/api/login/codigo", jsonPost({ telefone: $("telefone").value }));
    if (r.autorizado) { atualizarStatus(); return; }
    $("confirmar").hidden = false;
    $("status").textContent = "Código enviado. Confira no Telegram.";
  } catch (e) { mostrarErro(e.message); }
});

$("btn-confirmar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    const corpo = { codigo: $("codigo").value };
    if (!$("campo-senha").hidden) corpo.senha = $("senha").value;
    const r = await chamar("/api/login/confirmar", jsonPost(corpo));
    if (r.precisa_senha) {
      $("campo-senha").hidden = false;
      $("status").textContent = "Sua conta tem verificação em duas etapas: informe a senha e confirme de novo.";
      return;
    }
    atualizarStatus();
  } catch (e) { mostrarErro(e.message); }
});

// ---------- Destino / tópicos ----------
$("btn-listar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    preencherDestinos(await chamar("/api/destinos"));
  } catch (e) { mostrarErro(e.message); }
});

$("lista-destinos").addEventListener("change", () => {
  $("destino").value = $("lista-destinos").value;
});

$("btn-preparar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    const r = await chamar("/api/preparar", jsonPost({ entrada: $("destino").value }));
    $("info-destino").textContent =
      `Destino: ${r.destino.titulo} (${r.destino.tipo})`;
    const select = $("topico");
    select.innerHTML = '<option value="">Todos / sem tópico</option>';
    for (const t of r.topicos) {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      opt.textContent = t.titulo;
      select.appendChild(opt);
    }
    if (r.destino.tem_topicos) {
      $("info-destino").textContent += ` — ${r.topicos.length} tópicos.`;
    }
  } catch (e) { mostrarErro(e.message); }
});

// ---------- Download / progresso ----------
let acompanhando = null;

function acompanhar() {
  clearInterval(acompanhando);
  acompanhando = setInterval(async () => {
    try {
      const p = await chamar("/api/progresso");
      $("log").textContent = p.log.join("\n");
      $("log").scrollTop = $("log").scrollHeight;
      if (p.estado === "concluido" && p.stats) {
        $("resumo").textContent =
          `Concluído: ${p.stats.analisadas} mensagens analisadas, ` +
          `${p.stats.baixados} baixados, ${p.stats.pulados} pulados, ` +
          `${p.stats.erros} com erro.`;
      } else if (p.estado === "erro") {
        $("resumo").textContent = "Download terminou com erro: " + (p.erro || "");
      } else if (p.estado === "rodando") {
        $("resumo").textContent = "Baixando…";
      }
      if (p.estado !== "rodando") {
        clearInterval(acompanhando);
        $("btn-baixar").disabled = false;
        atualizarArquivos();
      }
    } catch { /* tenta de novo no próximo ciclo */ }
  }, 2000);
}

$("btn-baixar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    const limite = $("limite").value ? parseInt($("limite").value, 10) : null;
    const topico = $("topico").value ? parseInt($("topico").value, 10) : null;
    await chamar("/api/baixar", jsonPost({
      entrada: $("destino").value,
      topico_id: topico,
      limite: limite,
      pasta: $("pasta").value || null,
    }));
    $("btn-baixar").disabled = true;
    $("resumo").textContent = "Baixando…";
    acompanhar();
  } catch (e) { mostrarErro(e.message); }
});

// ---------- Arquivos ----------
function formatarTamanho(bytes) {
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + " GB";
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + " MB";
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(0) + " KB";
  return bytes + " B";
}

async function atualizarArquivos() {
  try {
    const pasta = encodeURIComponent($("pasta").value || "");
    const r = await chamar("/api/arquivos?pasta=" + pasta);
    const lista = $("arquivos");
    lista.innerHTML = "";
    if (!r.arquivos.length) {
      lista.innerHTML = "<li>Nenhum vídeo nesta pasta ainda.</li>";
      return;
    }
    for (const a of r.arquivos) {
      const li = document.createElement("li");
      const link = document.createElement("a");
      link.href = "/api/arquivos/baixar?pasta=" + pasta +
        "&caminho=" + encodeURIComponent(a.caminho);
      link.textContent = a.caminho;
      li.appendChild(link);
      li.appendChild(document.createTextNode(" (" + formatarTamanho(a.tamanho) + ")"));
      lista.appendChild(li);
    }
  } catch (e) { mostrarErro(e.message); }
}

$("btn-arquivos").addEventListener("click", atualizarArquivos);

atualizarStatus().then(atualizarArquivos);
