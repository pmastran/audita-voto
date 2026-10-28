/* Audita Voto — somente resultados calculados a partir da resposta real do servidor. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const settings = window.AUDITA_CONFIG || {};
  const configured = Boolean(settings.supabaseUrl && settings.supabasePublishableKey);
  const officialApi = "https://xhxrkkqjmzccapovfici.supabase.co/functions/v1/audita-tse?op=health";
  async function readOfficialTable(table, query) {
    if (!configured) {
      if (table !== "av_catalogos") throw new Error("Consulta de relatórios ainda não habilitada. O catálogo TSE está disponível, mas não há auditoria processada acessível neste site.");
      const response = await fetch("./data/catalogo-tse.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Catálogo oficial indisponível no site (HTTP ${response.status}).`);
      const snapshot = await response.json();
      const source = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna";
      if (snapshot.status !== "ok" || snapshot.source !== source || snapshot.catalog?.api_url !== source ||
          !Array.isArray(snapshot.catalog?.archives)) {
        throw new Error(snapshot.error || "O GitHub ainda não conseguiu consultar o catálogo oficial do TSE.");
      }
      return [{ conteudo: snapshot.catalog, atualizado_em: snapshot.retrieved_at }];
    }
    const base = new URL(settings.supabaseUrl);
    if (base.protocol !== "https:" || !base.hostname.endsWith(".supabase.co")) throw new Error("Endereço Supabase inválido.");
    const api = new URL(`/rest/v1/${table}`, base);
    api.search = query.toString();
    const key = settings.supabasePublishableKey;
    const headers = { "apikey": key, "Accept": "application/json" };
    if (key.split(".").length === 3) headers.Authorization = `Bearer ${key}`;
    const response = await fetch(api.toString(), { headers, cache: "no-store" });
    if (!response.ok) throw new Error(`Supabase retornou HTTP ${response.status}. Confira a conexão e as políticas públicas de leitura.`);
    const rows = await response.json();
    if (!Array.isArray(rows)) throw new Error("Resposta de dados inválida.");
    return rows;
  }
  const state = { catalog: null, health: null, report: null, busy: false, selected: "overview", catalogError: null };
  const formatNumber = (x) => x === null || x === undefined ? "—" : Number(x).toLocaleString("pt-BR");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const safeLink = (url) => {
    try { const u = new URL(url); return u.protocol === "https:" && ["cdn.tse.jus.br", "dadosabertos.tse.jus.br"].includes(u.hostname) ? esc(url) : ""; }
    catch { return ""; }
  };

  let toastTimer;
  function toast(message, isError = false) {
    const t = $("toast"); t.textContent = message; t.classList.toggle("error", isError); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 7500);
  }
  function showPage(name) {
    if (!["overview", "audit", "sources", "method"].includes(name)) name = "overview";
    state.selected = name;
    const titles = { overview: "Visão geral", audit: "Consultar auditorias", sources: "Fontes oficiais", method: "Metodologia" };
    document.querySelectorAll(".page").forEach((n) => n.classList.toggle("hidden", n.id !== "page-" + name));
    document.querySelectorAll(".nav-btn").forEach((n) => {
      const active = n.dataset.page === name;
      n.classList.toggle("active", active);
      if (active) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
    });
    $("page-crumb").textContent = titles[name];
    $("sidebar").classList.remove("show"); $("menu-toggle").setAttribute("aria-expanded", "false");
    if (window.location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    window.scrollTo({ top: 0, behavior: "auto" });
  }
  document.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
  document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.go)));
  $("menu-toggle").addEventListener("click", () => {
    const next = !$("sidebar").classList.contains("show");
    $("sidebar").classList.toggle("show", next);
    $("menu-toggle").setAttribute("aria-expanded", String(next));
  });
  window.addEventListener("hashchange", () => showPage(location.hash.replace("#", "")));
  const initialPage = location.hash.replace("#", "");
  if (initialPage) showPage(initialPage);

  async function loadHealth() {
    state.health = { audit_requires_key: false };
    try { const r = await fetch(officialApi, {signal: AbortSignal.timeout(8000)}); const data = await r.json(); if (r.ok && data.status === "ok" && data.service === "audita-voto-tse") state.health.tse_api_online = true; } catch (_) { state.health.tse_api_online = false; }
    $("operator-field").classList.add("hidden");
    $("connection-text").textContent = configured ? "Aguardando catálogo sincronizado" : "Consultando catálogo TSE via GitHub Pages";
    const wl = $("workflow-link");
    if (settings.githubRepository && /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(settings.githubRepository)) {
      wl.href = `https://github.com/${settings.githubRepository}/actions/workflows/auditar.yml`;
    } else { wl.removeAttribute("href"); wl.textContent = "Configure primeiro o repositório"; }
  }

  function updateFromCatalog() {
    const c = state.catalog;
    const online = Boolean(c && Array.isArray(c.archives));
    $("top-indicator").classList.toggle("online", online);
    $("side-dot").classList.toggle("online", online);
    $("connection-text").textContent = online ? (state.health?.tse_api_online ? "Catálogo TSE sincronizado · API ativa" : "Catálogo oficial sincronizado") : "Fonte não sincronizada";
    $("side-status").textContent = online ? (configured ? "Metadados oficiais no Supabase" : "Catálogo oficial via GitHub Pages") : "Fonte não sincronizada";
    $("stat-resources").textContent = online ? formatNumber(c.resources_total) : "—";
    $("stat-resources-detail").textContent = online ? "Recursos listados pelo catálogo oficial" : "Ainda sem catálogo sincronizado";
    $("stat-files").textContent = online ? formatNumber(c.archives.length) : "—";
    $("stat-files-detail").textContent = online ? "Arquivos ZIP de boletim identificados" : "Ainda sem catálogo sincronizado";
    $("catalog-info").textContent = online
      ? `Sincronizado pelo operador em ${new Date(c.retrieved_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}. ${c.archives.length} arquivo(s) identificados; a fonte original está indicada em cada registro.`
      : state.catalogError || "Ainda não foi possível consultar o catálogo.";
    renderSources(); updateTurnOptions();
  }

  function updateTurnOptions() {
    const box = $("uf-select"), t = Number($("turno-select").value);
    const previous = box.value;
    const resources = state.catalog?.archives?.filter((r) => r.turno === t) || [];
    const ufs = [...new Set(resources.map((r) => r.uf))].sort();
    if (!ufs.length) {
      box.innerHTML = `<option value="">${state.catalog ? "Nenhum arquivo oficial disponível para este turno" : "Catálogo oficial indisponível"}</option>`;
      $("audit-button").disabled = true;
      return;
    }
    box.innerHTML = ufs.map((uf) => `<option value="${esc(uf)}">${esc(uf)}</option>`).join("");
    box.value = ufs.includes(previous) ? previous : (ufs.includes("AC") ? "AC" : ufs[0]);
    $("audit-button").disabled = state.busy || !state.catalog;
  }
  $("turno-select").addEventListener("change", updateTurnOptions);

  function renderSources() {
    const c = state.catalog;
    if (!c) {
      $("sources-body").innerHTML = `<tr><td colspan="5" class="empty-row">${esc(state.catalogError || "Nenhum dado de catálogo recebido.")}</td></tr>`;
      return;
    }
    if (!c.archives.length) {
      $("sources-body").innerHTML = `<tr><td colspan="5" class="empty-row">O catálogo retornou sem arquivos BWEB identificáveis. Nenhuma auditoria disponível.</td></tr>`;
      return;
    }
    $("sources-body").innerHTML = c.archives.map((r) => `<tr>
      <td><strong>${esc(r.uf)}</strong></td><td>${esc(r.turno)}º turno</td>
      <td>${esc(r.name)}</td><td><span class="table-badge muted">Conferência no download</span></td>
      <td>${safeLink(r.url) ? `<a href="${safeLink(r.url)}" target="_blank" rel="noopener noreferrer">Arquivo ZIP ↗</a>` : "URL não validada"}</td>
    </tr>`).join("");
  }
  async function loadCatalog(force = false) {
    $("refresh-catalog").disabled = true;
    $("refresh-catalog").textContent = "Carregando relatório de fontes...";
    try {
      const rows = await readOfficialTable("av_catalogos", new URLSearchParams({ "select":"conteudo,atualizado_em", "chave":"eq.tse2026bu", "limit":"1" }));
      if (!rows.length || !rows[0].conteudo || !Array.isArray(rows[0].conteudo.archives)) {
        throw new Error("O catálogo oficial ainda não foi sincronizado. Execute a rotina Sincronizar catálogo no GitHub Actions.");
      }
      state.catalog = rows[0].conteudo; state.catalogError = null;
      updateFromCatalog();
      if (force) toast("Metadados publicados recarregados. Para atualizar diretamente no TSE, use o GitHub Actions.");
    } catch (e) {
      state.catalog = null; state.catalogError = e.message;
      updateFromCatalog(); if (force) toast(e.message, true);
    } finally {
      $("refresh-catalog").disabled = false;
      $("refresh-catalog").textContent = "↻ Recarregar catálogo";
    }
  }

  $("refresh-catalog").addEventListener("click", () => loadCatalog(true));

  function saveReport() {
    if (!state.report) return;
    const text = JSON.stringify(state.report, null, 2);
    const url = URL.createObjectURL(new Blob([text], { type: "application/json;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `audita-voto-${state.report.uf}-${state.report.turno}t-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  const readableVote = (v) => `${esc(v.nome)}${v.numero ? " · " + esc(v.numero) : ""}`;
  function renderReport(report) {
    const p = $("audit-result");
    const { resumo, origem, coincidencias, diferencas } = report;
    const source = safeLink(origem.arquivo_url);
    const hashLink = safeLink(origem.hash_url);
    const resultHtml = coincidencias.length
      ? coincidencias.map((f, i) => `<article class="finding-card">
        <div class="finding-head"><div><strong>${esc(f.municipio)}</strong><small>Ocorrência ${i + 1} · ${esc(f.regra)} · ${formatNumber(f.quantidade_secoes)} seções</small></div><span class="finding-badge">COINCIDÊNCIA NUMÉRICA</span></div>
        <details><summary>Ver seções e números originais</summary><div class="finding-content">
          <span>Seções com combinação idêntica:</span><div class="pill-list">${f.secoes.map((s) => `<span class="pill">${esc(s.municipio)} · Z${esc(s.zona)} / S${esc(s.secao)} · ${formatNumber(s.comparecimento)} votantes</span>`).join("")}</div>
          <div class="vote-list">${f.votos.map((v) => `<div><strong>${formatNumber(v.votos)}</strong><span>${readableVote(v)}</span></div>`).join("")}</div>
          <p>O padrão foi encontrado nos dados oficiais selecionados. A coincidência não demonstra irregularidade.</p>
        </div></details>
      </article>`).join("")
      : `<div class="empty-results"><strong>Nenhuma coincidência encontrada com estes filtros.</strong>Isso é resultado desta auditoria específica, não uma conclusão sobre outras UFs ou turnos.</div>`;
    const differences = diferencas.length ? diferencas.map((f) => `<article class="finding-card"><div class="finding-head"><div><strong>${esc(f.municipio)} · Zona ${esc(f.zona)}, seção ${esc(f.secao)}</strong><small>${esc(f.regra)}</small></div><span class="finding-badge">DADO PARA CONFERÊNCIA</span></div><div class="finding-content">${esc(f.explicacao)}${f.soma_votos !== undefined ? ` Soma dos votos: ${formatNumber(f.soma_votos)} · Comparecimento: ${formatNumber(f.comparecimento)}.` : ""}</div></article>`).join("") : `<div class="empty-results"><strong>Nenhuma diferença aritmética identificada.</strong>Neste arquivo e no cargo analisado, as regras executadas não encontraram diferenças.</div>`;
    p.innerHTML = `
      <div class="results-banner"><div><span class="section-kicker">RELATÓRIO GERADO A PARTIR DE ARQUIVO VALIDADO</span><h2>Auditoria concluída: ${esc(report.uf)} · ${esc(report.turno)}º turno</h2><p>SHA-512 conferido com o resumo oficial do TSE · ${new Date(report.executado_em_utc).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</p></div><button class="button button-outline" id="export-report">↓ Exportar JSON</button></div>
      <div class="result-metrics"><div class="result-metric"><strong>${formatNumber(resumo.secoes_processadas)}</strong><span>Seções processadas</span></div><div class="result-metric"><strong>${formatNumber(resumo.municipios)}</strong><span>Municípios no arquivo</span></div><div class="result-metric"><strong>${formatNumber(resumo.grupos_duplicados)}</strong><span>Grupos com resultado repetido</span></div><div class="result-metric"><strong>${formatNumber(resumo.diferencas_aritmeticas_ou_de_registro)}</strong><span>Diferenças a conferir</span></div></div>
      <div class="panel finding-panel"><h2>Coincidências identificadas</h2><p>Exibindo ${formatNumber(resumo.grupos_exibidos)} de ${formatNumber(resumo.grupos_duplicados)} grupo(s) encontrados. Apenas o conjunto calculado foi considerado.</p>${resultHtml}</div>
      <div class="panel finding-panel"><h2>Conferência aritmética</h2><p>Exibindo ${formatNumber(resumo.diferencas_exibidas)} de ${formatNumber(resumo.diferencas_aritmeticas_ou_de_registro)} registro(s) apontados para conferência.</p>${differences}</div>
      <div class="panel finding-panel"><h2>Proveniência documental</h2><p>Registros técnicos que permitem reproduzir a auditoria.</p><div class="evidence"><strong>Arquivo:</strong> ${esc(origem.recurso_nome)}<br/><strong>CSV lido:</strong> ${esc(report.leitura.arquivo_csv)}<br/><strong>SHA-512:</strong> ${esc(origem.sha512)}<br/><strong>Hash verificado:</strong> ${origem.hash_verificado ? "SIM — IGUAL AO OFICIAL" : "NÃO"}<br/><strong>Processador:</strong> ${esc(report.versao_parser)}<br/><strong>Linhas presidenciais:</strong> ${formatNumber(report.leitura.linhas_presidente_validas)}<br/><strong>Fonte:</strong> ${source ? `<a href="${source}" target="_blank" rel="noopener noreferrer">Arquivo TSE ↗</a>` : "URL não validada"}<br/><strong>Arquivo de hash:</strong> ${hashLink ? `<a href="${hashLink}" target="_blank" rel="noopener noreferrer">Hash oficial ↗</a>` : "URL não validada"}</div><p class="subtext">O relatório é referente a um arquivo, uma UF, um cargo e um turno; resultados idênticos não provam fraude.</p></div>`;
    $("export-report").addEventListener("click", saveReport);
    $("stat-audit").textContent = `${esc(report.uf)} · ${report.turno}º turno`;
    $("stat-audit-detail").textContent = `${formatNumber(resumo.secoes_processadas)} seções analisadas nesta sessão`;
    p.classList.remove("hidden");
  }
  async function handleAudit(event) {
    event.preventDefault();
    if (state.busy || !state.catalog) return;
    const args = {
      uf: $("uf-select").value,
      turno: Number($("turno-select").value),
      modo: $("modo-select").value,
      comparecimento_minimo: Number($("min-voters").value),
      minimo_secoes: Number($("min-match").value),
      mesmo_municipio: $("same-municipality").checked,
    };
    if (!args.uf || args.comparecimento_minimo < 0 || args.comparecimento_minimo > 9999 || args.minimo_secoes < 2 || args.minimo_secoes > 20) {
      toast("Confira os filtros antes de consultar.", true); return;
    }
    state.busy = true; $("audit-button").disabled = true;
    $("audit-button").textContent = "Consultando relatórios registrados...";
    $("audit-result").classList.remove("hidden");
    $("audit-result").innerHTML = `<div class="status-info" role="status">Consultando relatórios previamente processados. Nenhuma auditoria nova será iniciada nesta página.</div>`;
    try {
      const q = new URLSearchParams({
        "select":"relatorio,executado_em",
        "uf":`eq.${args.uf}`,
        "turno":`eq.${args.turno}`,
        "modo":`eq.${args.modo}`,
        "comparecimento_minimo":`eq.${args.comparecimento_minimo}`,
        "minimo_secoes":`eq.${args.minimo_secoes}`,
        "mesmo_municipio":`eq.${args.mesmo_municipio}`,
        "publicado":"eq.true",
        "order":"executado_em.desc", "limit":"1",
      });
      const rows = await readOfficialTable("av_relatorios", q);
      if (!rows.length) {
        state.report = null;
        $("audit-result").innerHTML = `<div class="status-info"><strong>Sem auditoria publicada para os filtros escolhidos.</strong> Nenhum resultado foi inferido. Para executar esse recorte, abra a rotina no GitHub Actions, escolha os parâmetros e publique o relatório validado.</div>`;
        return;
      }
      const report = rows[0].relatorio;
      if (!report?.origem?.hash_verificado || !report?.resumo || !Array.isArray(report.coincidencias)) throw new Error("Relatório incompleto ou sem comprovação de hash: exibição bloqueada.");
      state.report = report;
      renderReport(report);
      toast("Relatório existente recuperado do banco. Origem e SHA-512 estão no documento.");
    } catch (e) {
      state.report = null;
      $("audit-result").innerHTML = `<div class="status-error">Consulta não concluída: ${esc(e.message)}<br/><small>Nenhum resultado foi apresentado ou presumido.</small></div>`;
      toast("Consulta não concluída: " + e.message, true);
    } finally {
      state.busy = false;
      $("audit-button").textContent = "Consultar relatórios publicados →";
      updateTurnOptions();
    }
  }

  $("audit-form").addEventListener("submit", handleAudit);
  loadHealth().then(() => loadCatalog());
})();
