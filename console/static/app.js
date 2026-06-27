'use strict';
// Consola ARGOS — read-only. Poll /api/incidents y renderiza el HITL con el diseño.
const TIER = { T0: 'var(--t0)', T1: 'var(--t1)', T2: 'var(--t2)', T3: 'var(--t3)' };
const ASTATUS = {
  approved: { c: 'var(--ok)', t: 'aprobó' },
  rejected: { c: 'var(--rej)', t: 'rechazó' },
  pending: { c: 'var(--pending)', t: 'pendiente' },
  timeout: { c: 'var(--timeout)', t: 'timeout' },
};
const SEV = { low: 'var(--t3)', medium: 'var(--t2)', high: 'var(--t1)', critical: 'var(--t0)' };
const CHANNEL = { telegram: 'Telegram', discord: 'Discord', twilio_voice: 'Twilio', email: 'Email' };

let incidents = [];
let selectedId = null;

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const badge = (text, color) => `<span class="badge" style="background:${color}">${esc(text)}</span>`;
const mmss = secs => { const t = Math.max(0, Math.floor(secs)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; };

async function poll() {
  try {
    const r = await fetch('/api/incidents');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    incidents = await r.json();
    setStatus(true);
  } catch (e) { setStatus(false); }
  render();
}
function setStatus(up) {
  const s = $('#status');
  s.classList.toggle('down', !up);
  s.innerHTML = `<span class="dot"></span> ${up ? 'SISTEMA ACTIVO' : 'SOAR/Redis no disponible'}`;
}

function render() {
  renderList();
  const inc = incidents.find(i => i.incident_id === selectedId) || incidents[0] || null;
  selectedId = inc ? inc.incident_id : null;
  renderDetail(inc);
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
    + llmCard(inc) + actionsCard(inc);
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
      <td><span class="pill"><span class="d" style="background:${st.c}"></span>${esc(st.t)}</span></td>
      <td>${lat}</td><td>${esc(CHANNEL[a.channel] || a.channel)}</td></tr>`;
  }).join('');
  return `<div class="card"><h3>Matriz de aprobadores</h3>
    ${inc.approvers.length ? `<table class="matrix"><thead><tr>
      <th>Aprobador</th><th>Estado</th><th>Latencia</th><th>Canal</th></tr></thead>
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
  const remaining = Math.max(0, (Date.parse(w.started_at) + dur * 1000 - Date.now()) / 1000);
  const frac = dur > 0 ? Math.min(1, 1 - remaining / dur) : 1;
  return `<div class="clock">${mmss(remaining)} <span class="muted" style="font-size:14px">/ ${mmss(dur)}</span></div>
    <div class="muted" style="font-size:12px">${w.ended_at ? 'cerrada' : 'en curso'}</div>
    <div class="bar"><span style="width:${(frac * 100).toFixed(1)}%"></span></div>`;
}
function tickClock() {
  const inc = incidents.find(i => i.incident_id === selectedId);
  const body = $('#clock-body');
  if (inc && body) body.innerHTML = clockBody(inc);
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

function actionsCard(inc) {
  if (!inc.proposed_actions.length) return '';
  const rows = inc.proposed_actions.map(a =>
    `<tr><td class="mono">${esc(a.id)}</td><td>${esc(a.type)}</td><td class="mono">${esc(a.target)}</td>
     <td>${a.reversible ? 'sí' : 'no'}</td></tr>`).join('');
  return `<div class="card"><h3>Acciones propuestas</h3>
    <table class="matrix"><thead><tr><th>ID</th><th>Tipo</th><th>Objetivo</th><th>Reversible</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

poll();
setInterval(poll, 1500);
setInterval(tickClock, 500);
