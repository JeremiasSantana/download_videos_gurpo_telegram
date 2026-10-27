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
      if (Array.isArray(detalhe.candidatos)) {
        preencherDestinos(detalhe.candidatos);
        throw new Error(detalhe.mensagem + " Escolha um na lista que abriu.");
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

function formatarTamanho(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + " GB";
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + " MB";
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(0) + " KB";
  return bytes + " B";
}

// ---------- Tema claro/escuro (sol/lua) ----------
function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  try { localStorage.setItem("tema", tema); } catch { /* sem storage */ }
  montarLogos();
}

$("btn-tema").addEventListener("click", () => {
  const atual = document.documentElement.dataset.tema === "claro" ? "claro" : "escuro";
  aplicarTema(atual === "claro" ? "escuro" : "claro");
});

(function iniciarTema() {
  let tema = "escuro";
  try { tema = localStorage.getItem("tema") || "escuro"; } catch { /* padrão */ }
  document.documentElement.dataset.tema = tema === "claro" ? "claro" : "escuro";
})();

// ---------- Fundo animado: rede neural + logos flutuando ----------
const canvas = $("fundo-rede");
const ctx = canvas.getContext("2d");
let pontos = [];

function iniciarRede() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const quantidade = Math.min(70, Math.floor(window.innerWidth / 18));
  pontos = Array.from({ length: quantidade }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    vx: (Math.random() - 0.5) * 0.45,
    vy: (Math.random() - 0.5) * 0.45,
  }));
}

function desenharRede() {
  const cor = getComputedStyle(document.documentElement)
    .getPropertyValue("--rede").trim() || "90, 180, 250";
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const p of pontos) {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
    if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2.3, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${cor}, 0.95)`;
    ctx.fill();
  }
  ctx.lineWidth = 1.3;
  for (let i = 0; i < pontos.length; i++) {
    for (let j = i + 1; j < pontos.length; j++) {
      const dx = pontos[i].x - pontos[j].x;
      const dy = pontos[i].y - pontos[j].y;
      const dist = Math.hypot(dx, dy);
      if (dist < 145) {
        ctx.beginPath();
        ctx.moveTo(pontos[i].x, pontos[i].y);
        ctx.lineTo(pontos[j].x, pontos[j].y);
        ctx.strokeStyle = `rgba(${cor}, ${(1 - dist / 145) * 0.65})`;
        ctx.stroke();
      }
    }
  }
  requestAnimationFrame(desenharRede);
}

const TECNOLOGIAS = [
  { slug: "python", cor: "3776AB", sigla: "Py" },
  { slug: "git", cor: "F05032", sigla: "Git" },
  { slug: "github", cor: null, sigla: "GH" }, // cor depende do tema
  { slug: "telegram", cor: "26A5E4", sigla: "TG" },
  { slug: "javascript", cor: "F7DF1E", sigla: "JS" },
  { slug: "html5", cor: "E34F26", sigla: "HTML" },
  { slug: "css", cor: "663399", sigla: "CSS" },
  { slug: "fastapi", cor: "009688", sigla: "API" },
  { slug: "linux", cor: "FCC624", sigla: "Linux" },
  { slug: "docker", cor: "2496ED", sigla: "Docker" },
];
let flutuantes = [];

function montarLogos() {
  const caixa = $("logos-flutuantes");
  caixa.innerHTML = "";
  flutuantes = [];
  const escuro = document.documentElement.dataset.tema !== "claro";
  for (const tec of TECNOLOGIAS) {
    const cor = tec.cor || (escuro ? "FFFFFF" : "181717");
    const el = document.createElement("div");
    el.className = "logo-flutuante";
    const sigla = document.createElement("span");
    sigla.className = "sigla";
    sigla.textContent = tec.sigla;
    el.appendChild(sigla);
    const img = document.createElement("img");
    img.alt = "";
    img.src = `https://cdn.simpleicons.org/${tec.slug}/${cor}`;
    img.addEventListener("load", () => { sigla.remove(); });
    img.addEventListener("error", () => { img.remove(); });
    el.appendChild(img);
    caixa.appendChild(el);
    flutuantes.push({
      el,
      x: Math.random() * Math.max(1, window.innerWidth - 50),
      y: Math.random() * Math.max(1, window.innerHeight - 50),
      vx: (Math.random() < 0.5 ? -1 : 1) * (0.25 + Math.random() * 0.5),
      vy: (Math.random() < 0.5 ? -1 : 1) * (0.25 + Math.random() * 0.5),
    });
  }
}

function moverLogos() {
  for (const f of flutuantes) {
    f.x += f.vx; f.y += f.vy;
    if (f.x < 0 || f.x > window.innerWidth - 52) f.vx *= -1;
    if (f.y < 0 || f.y > window.innerHeight - 52) f.vy *= -1;
    f.x = Math.min(Math.max(f.x, 0), window.innerWidth - 52);
    f.y = Math.min(Math.max(f.y, 0), window.innerHeight - 52);
    f.el.style.transform = `translate(${f.x}px, ${f.y}px)`;
  }
  requestAnimationFrame(moverLogos);
}

window.addEventListener("resize", iniciarRede);
iniciarRede();
desenharRede();
montarLogos();
moverLogos();

// ---------- Status / login ----------
// Lista de conversas: painel próprio (não o <select> do navegador),
// aberto pela seta ao lado do campo. Abre com um clique e só fecha
// ao escolher um item ou ao clicar na seta de novo — nada de clicar
// e segurar o mouse. A seta mostra as conversas que combinam com o
// texto digitado; campo vazio mostra todas.
let todosDestinos = null; // cache da lista completa de conversas

function abrirListaDestinos() {
  $("lista-destinos").hidden = false;
  $("btn-seta-destinos").textContent = "▴";
}

function fecharListaDestinos() {
  $("lista-destinos").hidden = true;
  $("btn-seta-destinos").textContent = "▾";
}

function avisoNaLista(texto) {
  const lista = $("lista-destinos");
  lista.innerHTML = "";
  const aviso = document.createElement("div");
  aviso.className = "item-vazio";
  aviso.textContent = texto;
  lista.appendChild(aviso);
}

function montarListaDestinos(destinos) {
  // Monta os itens do painel SEM mexer no texto digitado no campo.
  if (!destinos.length) {
    avisoNaLista("Nenhuma conversa encontrada.");
    return;
  }
  const lista = $("lista-destinos");
  lista.innerHTML = "";
  for (const d of destinos) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "item-destino";
    item.textContent = `${d.titulo} (${d.tipo})`;
    item.addEventListener("click", () => {
      $("destino").value = String(d.id);
      invalidarVerificacao();
      fecharListaDestinos();
    });
    lista.appendChild(item);
  }
}

function preencherDestinos(destinos) {
  // Usado para os candidatos de um nome duplicado: mostra e abre.
  montarListaDestinos(destinos);
  if (destinos.length) abrirListaDestinos();
}

function filtrarDestinos(destinos, texto) {
  const t = texto.trim().toLowerCase();
  if (!t) return destinos;
  return destinos.filter((d) =>
    d.titulo.toLowerCase().includes(t) ||
    (d.username && d.username.toLowerCase().includes(t)) ||
    String(d.id).includes(t)
  );
}

async function mostrarDestinosDaSeta() {
  if (!todosDestinos) {
    // Abre o painel na hora com o aviso de carregando: nada de
    // clicar e "não acontecer nada" enquanto a lista vem.
    avisoNaLista("Carregando conversas…");
    abrirListaDestinos();
    try {
      todosDestinos = await chamar("/api/destinos");
    } catch (e) {
      avisoNaLista("Não consegui carregar as conversas: " + e.message);
      return;
    }
  }
  montarListaDestinos(
    filtrarDestinos(todosDestinos, $("destino").value)
  );
  abrirListaDestinos();
}

$("btn-seta-destinos").addEventListener("click", async () => {
  mostrarErro("");
  if (!$("lista-destinos").hidden) {
    fecharListaDestinos();
    return;
  }
  await mostrarDestinosDaSeta();
});

async function atualizarStatus() {
  try {
    const s = await chamar("/api/status");
    if (!s.configurado) {
      $("status").textContent = "Configuração incompleta: " + s.erro_config;
      return;
    }
    if (s.pasta_padrao && !$("pasta").value) $("pasta").value = s.pasta_padrao;
    if (s.download === "rodando") {
      // Página recarregada no meio de um download: restaura os botões.
      botoesDownload(true);
      $("resumo").textContent = "Baixando…";
      acompanhar();
    }
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
// Estado da verificação: guarda para QUAL texto o destino/tópicos em
// tela foram verificados. Se o texto mudar, a verificação antiga é
// descartada — nada de resultado velho de outro grupo.
let entradaVerificada = null;
let sequenciaVerificacao = 0;

function limparTopicos() {
  $("topico").innerHTML = '<option value="">Todos / sem tópico</option>';
}

function invalidarVerificacao() {
  entradaVerificada = null;
  sequenciaVerificacao++;
  $("info-destino").textContent = "";
  limparTopicos();
}

$("destino").addEventListener("input", () => {
  if (entradaVerificada !== null &&
      $("destino").value.trim() !== entradaVerificada) {
    invalidarVerificacao();
  }
  // Com o painel aberto, digitar já filtra as conversas na hora.
  if (!$("lista-destinos").hidden && todosDestinos) {
    montarListaDestinos(
      filtrarDestinos(todosDestinos, $("destino").value)
    );
  }
});

async function verificarDestino() {
  const entrada = $("destino").value.trim();
  if (!entrada) {
    $("info-destino").textContent =
      "Digite o nome ou o ID do destino primeiro.";
    return false;
  }
  const minhaSequencia = ++sequenciaVerificacao;
  const botao = $("btn-preparar");
  botao.disabled = true;
  entradaVerificada = null;
  limparTopicos();
  $("info-destino").textContent = "Verificando…";
  try {
    const r = await chamar(
      "/api/preparar", jsonPost({ entrada })
    );
    if (minhaSequencia !== sequenciaVerificacao) return false; // velha
    $("info-destino").textContent =
      `Destino: ${r.destino.titulo} (${r.destino.tipo})`;
    for (const t of r.topicos) {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      opt.textContent = t.titulo;
      $("topico").appendChild(opt);
    }
    if (r.destino.tem_topicos) {
      $("info-destino").textContent += ` — ${r.topicos.length} tópicos.`;
    }
    entradaVerificada = entrada;
    return true;
  } catch (e) {
    if (minhaSequencia !== sequenciaVerificacao) return false; // velha
    // O erro aparece aqui, junto do campo — não só no rodapé da página.
    $("info-destino").textContent = e.message;
    mostrarErro(e.message);
    return false;
  } finally {
    if (minhaSequencia === sequenciaVerificacao) botao.disabled = false;
  }
}

$("btn-preparar").addEventListener("click", async () => {
  mostrarErro("");
  await verificarDestino();
});

// ---------- Download / progresso ----------
let acompanhando = null;

function botoesDownload(rodando) {
  // Baixar fica clicável só sem download em andamento; Cancelar, só com.
  $("btn-baixar").disabled = rodando;
  $("btn-cancelar").disabled = !rodando;
}

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
      } else if (p.estado === "cancelado") {
        $("resumo").textContent =
          "Download cancelado. O que já foi baixado está salvo " +
          "e não será baixado de novo.";
      } else if (p.estado === "erro") {
        $("resumo").textContent = "Download terminou com erro: " + (p.erro || "");
      } else if (p.estado === "rodando") {
        $("resumo").textContent = "Baixando…";
        botoesDownload(true);
      }
      if (p.estado !== "rodando") {
        clearInterval(acompanhando);
        botoesDownload(false);
        atualizarHistorico();
      }
    } catch { /* tenta de novo no próximo ciclo */ }
  }, 2000);
}

$("btn-baixar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    // Se o texto atual ainda não foi verificado (ou mudou desde a
    // última verificação), verifica agora — nunca baixar usando
    // tópico/resultado de outro destino.
    if (entradaVerificada !== $("destino").value.trim()) {
      const ok = await verificarDestino();
      if (!ok) return;
    }
    const limite = $("limite").value ? parseInt($("limite").value, 10) : null;
    const topico = $("topico").value ? parseInt($("topico").value, 10) : null;
    await chamar("/api/baixar", jsonPost({
      entrada: $("destino").value.trim(),
      topico_id: topico,
      limite: limite,
      pasta: $("pasta").value || null,
    }));
    botoesDownload(true);
    $("resumo").textContent = "Baixando…";
    acompanhar();
  } catch (e) { mostrarErro(e.message); }
});

$("btn-cancelar").addEventListener("click", async () => {
  mostrarErro("");
  try {
    await chamar("/api/cancelar", { method: "POST" });
    $("btn-cancelar").disabled = true;
    $("resumo").textContent = "Cancelando…";
  } catch (e) { mostrarErro(e.message); }
});

// ---------- Histórico de vídeos baixados ----------
function lerOcultos() {
  try { return new Set(JSON.parse(localStorage.getItem("historico-ocultos") || "[]")); }
  catch { return new Set(); }
}
function salvarOcultos(ocultos) {
  try { localStorage.setItem("historico-ocultos", JSON.stringify([...ocultos])); } catch { /* sem storage */ }
}

async function atualizarHistorico() {
  const caixa = $("historico");
  try {
    const pasta = encodeURIComponent($("pasta").value || "");
    const r = await chamar("/api/historico?pasta=" + pasta);
    const ocultos = lerOcultos();
    caixa.innerHTML = "";
    if (!r.grupos.length) {
      caixa.innerHTML = "<p class='dica'>Nenhum vídeo no histórico desta pasta ainda.</p>";
      return;
    }
    for (const grupo of r.grupos) {
      const oculto = ocultos.has(grupo.chave);
      const div = document.createElement("div");
      div.className = "grupo";

      const cab = document.createElement("div");
      cab.className = "grupo-cabecalho";

      const titulo = document.createElement("button");
      titulo.type = "button";
      titulo.className = "grupo-titulo" + (oculto ? " embacado" : "");
      titulo.textContent = grupo.destino;
      cab.appendChild(titulo);

      const resumo = document.createElement("span");
      resumo.className = "grupo-resumo";
      resumo.textContent = `${grupo.total} vídeo(s) • ${formatarTamanho(grupo.tamanho_total)}`;
      cab.appendChild(resumo);

      const btnOcultar = document.createElement("button");
      btnOcultar.type = "button";
      btnOcultar.textContent = oculto ? "Mostrar" : "Ocultar";
      btnOcultar.addEventListener("click", () => {
        const o = lerOcultos();
        if (o.has(grupo.chave)) o.delete(grupo.chave); else o.add(grupo.chave);
        salvarOcultos(o);
        atualizarHistorico();
      });
      cab.appendChild(btnOcultar);

      const btnExcluir = document.createElement("button");
      btnExcluir.type = "button";
      btnExcluir.className = "perigo";
      btnExcluir.textContent = "Excluir histórico";
      btnExcluir.addEventListener("click", async () => {
        const ok = confirm(
          `Excluir o histórico de "${grupo.destino}"?\n\n` +
          "Isso apaga só o registro dos downloads desse local. " +
          "Os vídeos continuam na pasta, mas sem o registro eles " +
          "podem ser baixados de novo no futuro."
        );
        if (!ok) return;
        try {
          await chamar(
            "/api/historico?chave=" + encodeURIComponent(grupo.chave) +
            "&pasta=" + pasta,
            { method: "DELETE" }
          );
          const o = lerOcultos();
          o.delete(grupo.chave);
          salvarOcultos(o);
          atualizarHistorico();
        } catch (e) { mostrarErro(e.message); }
      });
      cab.appendChild(btnExcluir);
      div.appendChild(cab);

      const lista = document.createElement("ul");
      lista.className = "grupo-videos" + (oculto ? " embacado" : "");
      lista.hidden = true;
      for (const v of grupo.videos) {
        const li = document.createElement("li");
        if (v.caminho) {
          const link = document.createElement("a");
          link.href = "/api/arquivos/baixar?pasta=" + pasta +
            "&caminho=" + encodeURIComponent(v.caminho);
          link.textContent = v.topico ? `${v.topico} / ${v.nome}` : v.nome;
          li.appendChild(link);
        } else {
          li.textContent = v.topico ? `${v.topico} / ${v.nome}` : v.nome;
        }
        li.appendChild(document.createTextNode(" (" + formatarTamanho(v.tamanho) + ")"));
        lista.appendChild(li);
      }
      titulo.addEventListener("click", () => { lista.hidden = !lista.hidden; });
      div.appendChild(lista);
      caixa.appendChild(div);
    }
  } catch (e) { mostrarErro(e.message); }
}

$("btn-historico").addEventListener("click", atualizarHistorico);

atualizarStatus().then(atualizarHistorico);
