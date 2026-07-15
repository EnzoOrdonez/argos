'use strict';
// Consola ARGOS — read-only. Poll /api/incidents y renderiza el HITL con el diseño.
// Por incidente seleccionado además trae la ráfaga multi-capa (corr:alerts) y el
// timeline de auditoría (Postgres argos_audit, opcional).
const TIER = { T0: 'var(--t0)', T1: 'var(--t1)', T2: 'var(--t2)', T3: 'var(--t3)' };
const ASTATUS = {
  approved: { c: 'var(--ok)', t: 'aprobó' },
  rejected: { c: 'var(--rej)', t: 'rechazó' },
  pending: { c: 'var(--pending)', t: 'pendiente' },
  timeout: { c: 'var(--timeout)', t: 'timeout' },
};
const SEV = { low: 'var(--t3)', medium: 'var(--t2)', high: 'var(--t1)', critical: 'var(--t0)' };
const CHANNEL = { telegram: 'Telegram', discord: 'Discord', twilio_voice: 'Twilio', email: 'Email' };
const STALE_AFTER_S = 5;  // 3 polls perdidos (poll = 1.5s)

let incidents = [];
let selectedId = null;
let systemUp = true;
let lastOkAt = Date.now();
const extras = {};  // incident_id -> { burst: NormalizedAlert[]|undefined, audit: {available,events}|undefined }

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const badge = (text, color) => `<span class="badge" style="background:${color}">${esc(text)}</span>`;
const mmss = secs => { const t = Math.max(0, Math.floor(secs)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; };
const hms = iso => { if (!iso) return '—'; const d = new Date(iso); return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('es', { hour12: false }); };

async function poll() {
  try {
    const r = await fetch('/api/incidents');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    incidents = await r.json();
    lastOkAt = Date.now();
    systemUp = true;
  } catch (e) { systemUp = false; }
  render();
}

function renderStatus() {
  const s = $('#status');
  if (!s) return;
  const age = (Date.now() - lastOkAt) / 1000;
  const stale = age > STALE_AFTER_S;
  s.classList.toggle('down', !systemUp);
  const detail = $('#detail');
  if (detail) detail.classList.toggle('stale', stale);
  let txt;
  if (!systemUp) txt = 'SOAR/Redis no disponible';
  else if (stale) txt = `sin datos hace ${Math.floor(age)}s`;
  else txt = 'SISTEMA ACTIVO';
  s.innerHTML = `<span class="dot"></span> ${txt}`;
}

function render() {
  renderList();
  const inc = incidents.find(i => i.incident_id === selectedId) || incidents[0] || null;
  selectedId = inc ? inc.incident_id : null;
  renderDetail(inc);
  renderStatus();
  if (selectedId) loadExtras(selectedId);
}

function renderList() {
  const ul = $('#incident-list');
  if (!incidents.length) { ul.innerHTML = '<li class="muted" style="cursor:default">— sin incidentes —</li>'; return; }
  ul.innerHTML = incidents.map(i => {
    const dot = i.final_decision == null ? '🟢' : '⚪';
    return `<li class="${i.incident_id === selectedId ? 'active' : ''}" data-id="${esc(i.incident_id)}">
      <div class="row"><span class="iid">${esc(i.incident_id)}</span>${badge(i.tier, TIER[i.tier] || 'var(--muted)')}</div>
      <div class="host">${dot} ${esc(i.host.id)} · ${esc(i.state)}</div></li>`;
  }).join('');
  ul.querySelectorAll('li[data-id]').forEach(li => {
    li.onclick = () => { selectedId = li.dataset.id; render(); };
  });
}

function renderDetail(inc) {
  const d = $('#detail');
  if (!inc) { d.innerHTML = '<div class="empty">Esperando incidentes…</div>'; return; }
  d.innerHTML = bannerHTML(inc) + incidentCard(inc)
    + `<div class="grid2">${matrixCard(inc)}${clockCard(inc)}</div>`
    + llmCard(inc) + burstCard(inc) + auditCard(inc) + actionsCard(inc);
  tickClock();
}

function voteSummary(inc) {
  const c = { approved: 0, rejected: 0, pending: 0, timeout: 0 };
  inc.approvers.forEach(a => { c[a.status] = (c[a.status] || 0) + 1; });
  const p = [`${c.approved} aprob.`, `${c.rejected} rech.`];
  if (c.timeout) p.push(`${c.timeout} timeout`);
  if (c.pending) p.push(`${c.pending} pend.`);
  return p.join(' · ');
}

function bannerHTML(inc) {
  const w = inc.consolidation_window;
  const conflict = w && w.conflict_detected ? '<div class="conflict">⚠ CONFLICTO DETECTADO · SPLIT-BRAIN</div>' : '';
  const fd = inc.final_decision;
  if (!fd) return conflict + `<div class="banner pending">Decisión pendiente · ${voteSummary(inc)}</div>`;
  const cls = fd.outcome === 'EXECUTE_ISOLATION' ? 'exec' : fd.outcome === 'NO_ACTION' ? 'noact' : 'pending';
  const exec = fd.execution_status ? ` · ejecución ${esc(fd.execution_status)}` : '';
  return conflict + `<div class="banner ${cls}">${esc(fd.outcome)} · ${esc(fd.policy_applied)}${exec}
    <div class="rationale">${esc(fd.rationale)}</div></div>`;
}

function incidentCard(inc) {
  const a = inc.alert;
  return `<div class="card"><h3>Incidente activo</h3>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
      <span class="iid mono" style="font-size:16px">${esc(inc.incident_id)}</span>
      ${badge('Tier ' + inc.tier, TIER[inc.tier] || 'var(--muted)')}
      <span class="tag">${esc(inc.state)}</span></div>
    <div class="grid2">
      <dl class="kv"><dt>Host</dt><dd class="mono">${esc(inc.host.id)}</dd>
        <dt>Criticidad</dt><dd>${esc(inc.host.criticality)}</dd>
        ${inc.host.ip ? `<dt>IP</dt><dd class="mono">${esc(inc.host.ip)}</dd>` : ''}
        ${inc.host.os ? `<dt>OS</dt><dd>${esc(inc.host.os)}</dd>` : ''}</dl>
      <dl class="kv"><dt>Capa</dt><dd class="mono">${esc(a.source_layer)}</dd>
        <dt>Severidad</dt><dd>${badge(`${a.severity_label} (${a.severity_score.toFixed(2)})`, SEV[a.severity_label] || 'var(--muted)')}</dd>
        <dt>MITRE</dt><dd class="mono">${esc(a.technique_mitre || '—')}</dd>
        ${a.triggering_rule ? `<dt>Regla</dt><dd class="mono">${esc(a.triggering_rule)}</dd>` : ''}</dl>
    </div></div>`;
}

function matrixCard(inc) {
  const rows = inc.approvers.map(a => {
    const st = ASTATUS[a.status] || { c: 'var(--muted)', t: a.status };
    const lat = a.latency_seconds != null ? `${Math.round(a.latency_seconds)}s` : '—';
    return `<tr><td class="mono">${esc(a.email)}</td>
      <td>${esc(a.role || '—')}</td>
      <td><span class="pill"><span class="d" style="background:${st.c}"></span>${esc(st.t)}</span></td>
      <td>${lat}</td><td class="mono">${esc(hms(a.responded_at))}</td>
      <td>${esc(CHANNEL[a.channel] || a.channel)}</td></tr>`;
  }).join('');
  return `<div class="card"><h3>Matriz de aprobadores</h3>
    ${inc.approvers.length ? `<table class="matrix"><thead><tr>
      <th>Aprobador</th><th>Rol</th><th>Estado</th><th>Latencia</th><th>Respondió</th><th>Canal</th></tr></thead>
      <tbody>${rows}</tbody></table>` : '<div class="muted">Aún sin respuestas.</div>'}
    <div class="muted" style="margin-top:10px;font-size:12px">${voteSummary(inc)}</div></div>`;
}

function clockCard(inc) {
  return `<div class="card"><h3>Ventana de consolidación</h3><div id="clock-body">${clockBody(inc)}</div></div>`;
}
function clockBody(inc) {
  const w = inc.consolidation_window;
  if (!w) return '<div class="muted">Sin ventana todavía (arranca con el primer voto).</div>';
  const dur = w.duration_seconds;
  const closed = !!(w.ended_at || inc.final_decision);
  const remaining = closed ? 0 : Math.max(0, (Date.parse(w.started_at) + dur * 1000 - Date.now()) / 1000);
  const frac = closed ? 1 : (dur > 0 ? Math.min(1, 1 - remaining / dur) : 1);
  return `<div class="clock">${mmss(remaining)} <span class="muted" style="font-size:14px">/ ${mmss(dur)}</span></div>
    <div class="muted" style="font-size:12px">${closed ? 'cerrada' : 'en curso'}</div>
    <div class="bar"><span style="width:${(frac * 100).toFixed(1)}%"></span></div>`;
}
function tickClock() {
  const inc = incidents.find(i => i.incident_id === selectedId);
  const body = $('#clock-body');
  if (inc && body) body.innerHTML = clockBody(inc);
  renderStatus();  // mantiene el contador de "sin datos hace Ns" vivo
}

function llmCard(inc) {
  const t = inc.llm_analysis;
  if (!t) {
    return '<div class="card llm"><h3>LLM Triage · Capa 4</h3>'
      + '<div class="muted">Sin análisis LLM (None — la contención no depende de esto, R-2).</div></div>';
  }
  const iocs = (t.indicadores_correlacionar || []).map(x => `<span class="tag">${esc(x)}</span>`).join('');
  return `<div class="card llm"><h3>LLM Triage · Capa 4 (TriageResponse)</h3>
    <div class="grid2">
      <dl class="kv"><dt>Técnica MITRE</dt><dd class="mono">${esc(t.tecnica_mitre)}</dd>
        <dt>Severidad</dt><dd>${badge(t.severidad, SEV[t.severidad] || 'var(--muted)')}</dd>
        <dt>Confianza</dt><dd>${(t.confianza * 100).toFixed(0)}%</dd>
        <dt>Backend</dt><dd class="mono">${esc(t.llm_backend)}</dd></dl>
      <div><div class="muted" style="font-size:12px">Runbook sugerido · NIST 800-61</div>
        <div>${esc(t.runbook_aplicable)}</div></div>
    </div>
    <div class="accion"><div class="muted" style="font-size:12px">Resumen del analista</div>${esc(t.accion_recomendada)}</div>
    ${iocs ? `<div style="margin-top:10px"><div class="muted" style="font-size:12px">Indicadores a correlacionar</div>${iocs}</div>` : ''}
  </div>`;
}

// -- ráfaga multi-capa (corr:alerts) --------------------------------------
function burstCard(inc) {
  return `<div class="card"><h3>Ráfaga multi-capa correlacionada</h3><div id="burst-body">${burstBody(inc)}</div></div>`;
}
function burstBody(inc) {
  const rows = (extras[inc.incident_id] || {}).burst;
  if (rows === undefined) return '<div class="muted">cargando…</div>';
  if (!rows.length) return '<div class="muted">Sin ráfaga (expiró el TTL o el incidente no tuvo correlación multi-capa).</div>';
  const body = rows.map(a =>
    `<tr><td class="mono">${esc(a.alert_id)}</td><td class="mono">${esc(a.source_layer)}</td>
     <td class="mono">${esc(a.technique_mitre || '—')}</td>
     <td>${badge(`${a.severity_label} (${a.severity_score.toFixed(2)})`, SEV[a.severity_label] || 'var(--muted)')}</td>
     <td class="mono">${esc(a.triggering_rule || '—')}</td></tr>`).join('');
  return `<table class="matrix"><thead><tr><th>Alerta</th><th>Capa</th><th>MITRE</th><th>Severidad</th><th>Regla</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

// -- timeline de auditoría (Postgres argos_audit, opcional) ----------------
function auditCard(inc) {
  return `<div class="card"><h3>Timeline de auditoría</h3><div id="audit-body">${auditBody(inc)}</div></div>`;
}
function auditBody(inc) {
  const a = (extras[inc.incident_id] || {}).audit;
  if (a === undefined) return '<div class="muted">cargando…</div>';
  if (!a.available) return '<div class="muted">Timeline no disponible (Postgres <span class="mono">argos_audit</span> no configurado). La consola funciona igual con Redis; setea <span class="mono">ARGOS_AUDIT_SQL_DSN</span> para habilitarlo.</div>';
  if (!a.events.length) return '<div class="muted">Sin eventos de auditoría todavía.</div>';
  const items = a.events.map(e =>
    `<li><span class="t mono">${esc(hms(e.ts))}</span><span class="k">${esc(e.kind)}</span>${auditPayload(e.payload)}</li>`).join('');
  return `<ol class="timeline">${items}</ol>`;
}
function auditPayload(p) {
  const keys = Object.keys(p || {});
  if (!keys.length) return '';
  const parts = keys.map(k => `${esc(k)}=${esc(p[k])}`).join(' · ');
  return `<span class="pl">${parts}</span>`;
}

function actionsCard(inc) {
  if (!inc.proposed_actions.length) return '';
  const rows = inc.proposed_actions.map(a =>
    `<tr><td class="mono">${esc(a.id)}</td><td>${esc(a.type)}</td><td class="mono">${esc(a.target)}</td>
     <td>${a.reversible ? 'sí' : 'no'}</td></tr>`).join('');
  return `<div class="card"><h3>Acciones propuestas</h3>
    <table class="matrix"><thead><tr><th>ID</th><th>Tipo</th><th>Objetivo</th><th>Reversible</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// Trae ráfaga + timeline del incidente seleccionado y parchea sus cards en sitio.
async function loadExtras(id) {
  if (!id) return;
  try {
    const [burst, audit] = await Promise.all([
      fetch(`/api/incidents/${encodeURIComponent(id)}/alerts`).then(r => r.ok ? r.json() : []),
      fetch(`/api/incidents/${encodeURIComponent(id)}/audit`).then(r => r.ok ? r.json() : { available: false, events: [] }),
    ]);
    extras[id] = { burst, audit };
  } catch (e) {
    extras[id] = extras[id] || { burst: [], audit: { available: false, events: [] } };
  }
  if (selectedId !== id) return;  // el usuario cambió de incidente mientras cargaba
  const inc = incidents.find(i => i.incident_id === id);
  if (!inc) return;
  const b = $('#burst-body'); if (b) b.innerHTML = burstBody(inc);
  const a = $('#audit-body'); if (a) a.innerHTML = auditBody(inc);
}

poll();
setInterval(poll, 1500);
setInterval(tickClock, 500);
