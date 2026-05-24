# Manual de Equipo — Operación y Convenciones

| Campo | Valor |
|-------|-------|
| Tipo | Plan operacional + convenciones + flujo del demo |
| Estado | Activo |
| Entrega final | **13 de junio de 2026 (sábado)** |
| Goal | UC-01 + UC-02 + UC-04 + UC-06 + UC-07 corriendo end-to-end. UC-08 nice-to-have. Dos rehearsals previos al demo. |
| Owner | P1 (Enzo Ordoñez Flores) coordina · los 4 integrantes ejecutan |

---

## 0. Por qué existe este documento

Captura decisiones operacionales que se acordaron por conversación pero no estaban en el SAD ni en ningún ADR. Sin esta página, esas decisiones se pierden y el equipo improvisa en el peor momento (el demo). Tres bloques de contenido viven aquí: el modelo de deployment, el flujo del demo, y las convenciones operativas.

---

## 1. Modelo de deployment

**Modelo elegido:** 100 % local en Vagrant, con laptop espejo en P1 como _hot spare_, y datos móviles del equipo como respaldo de conectividad para los servicios externos (OpenAI, Telegram, Discord, Twilio).

### 1.1 Razón

Cada hop de red real entre componentes es un punto de falla. El modelo 100 % local concentra los hops en `localhost` (que no falla), dejando red real sólo para los cuatro servicios externos genuinamente cloud. El modelo híbrido (Wazuh + OpenSearch + Redis en VPS Hetzner) agrega ~10 hops de red entre la laptop víctima y un manager remoto, además de configuración no trivial de VPN/firewall. La ventaja del híbrido (P4 deja de ser SPOF) se resuelve mejor con un lab espejo local en P1 que con cloud.

### 1.2 Lo que cada hop de red real cubre

- LLM Triage → OpenAI API (mitigable con `LLM_BACKEND=llama_local`, que cae a Llama 3.1 local vía Ollama, _zero-egress_).
- Notification Service → Telegram Bot API.
- Notification Service → Discord webhook.
- Notification Service → Twilio API (sólo para escalación T2 a los 60 segundos).

Todo lo demás (Wazuh agent → manager → consumer ML → SOAR → Approval Console) es localhost dentro del lab Vagrant.

### 1.3 Resiliencia operacional

- **Lab primario:** laptop de P4 (Diego). Vagrantfile + scripts en `lab/`.
- **Lab espejo:** laptop de P1 (Enzo). Mismo Vagrantfile clonado del repo, `vagrant up` independiente.
- **Decisión de qué lab usar el día del demo:** se decide cuatro horas antes según cuál esté más estable. La transición entre uno y otro es: cambiar la URL del Wazuh manager en `.env` y reiniciar servicios. No hay reconfiguración de red.
- **SSD externo (opcional, recomendado):** P4 instala las VMs en un SSD USB-C de 256 GB (~USD 30). Si su laptop falla, conecta el SSD a otro equipo con VirtualBox y bootea. Tercera línea de defensa.
- **Video respaldo:** P4 graba el demo completo uno o dos días antes con todo funcionando. Si todo falla en vivo, narra sobre el video. Pierdes impacto pero salvas la presentación.

### 1.4 Internet del salón de exposición

- **WiFi institucional:** se prueba al menos una semana antes del demo. Si hay _captive portal_ o bloqueo de puertos a `api.openai.com`, `api.telegram.org`, `api.twilio.com`, no se usa.
- **Datos móviles como respaldo:** P1 y P4 tienen sus celulares con hotspot configurado y plan con datos suficientes. Cubren WiFi bloqueado pero **no resuelven latencia variable**. Con el modelo 100 % local esto no afecta la pipeline crítica (todo es localhost), sólo las notificaciones externas, que toleran latencia.
- **Si todo internet cae:** el sistema sigue funcionando con `LLM_BACKEND=llama_local` y email post-facto a MailHog local. UC-01 y UC-02 sobreviven sin internet. UC-04 con _two-person rule_ sobrevive si los aprobadores están físicamente en la sala mirando la Streamlit Console (que es localhost).

### 1.5 Lo que NO se va a nube en ninguna fase

- VMs víctima (Windows + Linux). Son donde el ransomware corre.
- PostgreSQL en producción (activo defendido). Vive en la Linux VM.
- Simulador de ransomware. Corre donde están las víctimas.
- Canary files con FIM whodata.

Estos componentes son el "núcleo del demo": moverlos a cloud pierde la narrativa "estoy atacando un sistema real frente a ustedes".

---

## 2. Flujo del demo en vivo

### 2.1 Setup pre-demo (T - 1 hora)

1. P4 arranca el lab primario con `vagrant up`. Verifica con `curl https://localhost:55000` (Wazuh API) que responde.
2. P4 arranca todos los servicios Python con `make demo-up` (script que levanta SOAR Decision Engine, LLM Triage, Approval API, Streamlit Console).
3. P4 verifica que Streamlit Approval Console responde en `http://localhost:8501`.
4. P1 arranca el lab espejo en su laptop como _hot spare_. Mismo procedimiento, sin proyectar.
5. Los cuatro integrantes verifican que el bot Telegram envía mensaje de prueba a sus celulares (`"ARGOS demo ready"`).
6. P4 conecta laptop primario al proyector.

### 2.2 Ejecución del demo (12-13 minutos totales)

| Tiempo | UC | Acción | Pantalla |
|--------|----|--------|----------|
| 0:00-2:00 | UC-01 | P4 ejecuta `python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target windows-victim` | Streamlit Console muestra 3 capas firing → T0 → auto-isolate. Audiencia ve archivos cifrándose en la VM Windows. |
| 2:00-3:30 | UC-02 | P4 ejecuta `python attack-simulation/ransomware_simulator/canary_path.py --target linux-victim` | Console muestra Layer 3 sola firing → T0 → aislamiento sin que se cifre un solo archivo real. |
| 3:30-7:00 | UC-04 | P4 ejecuta `python attack-simulation/ransomware_simulator/postgres_attack.py --target linux-victim` | _Two-person rule_: 4 integrantes reciben Telegram, P1 y P2 aprueban, P3 espera, P4 timeout. Sistema espera 2 aprobaciones, luego ejecuta. |
| 7:00-12:00 | Q&A | Profesor pregunta | Mostrar audit log en OpenSearch Dashboards |

### 2.3 Rol de cada integrante durante el demo

- **P4 (Diego):** operador del demo. Ejecuta los comandos, navega entre pantallas, controla el proyector. Cualquier crash, él reinicia.
- **P1 (Enzo):** narrador principal. Explica qué está pasando en cada pantalla. Tiene la laptop espejo abierta por si hay que conmutar.
- **P2 (Sebastian):** aprobador 1 en UC-04. Explica la capa ML cuando salga el ML score en pantalla.
- **P3 (Angeles):** aprobador 2 en UC-04. Explica las reglas Sigma cuando salgan disparadas.

---

## 3. Convenciones operativas

### 3.1 Standup diario (20 minutos, 9:00 AM)

Discord, canal `#argos-standup`, llamada de voz. Cada integrante en 3 minutos:

- Lo que cerré ayer (PRs mergeados, tests passing).
- Lo que cierro hoy (objetivos del día).
- Bloqueos (qué necesito de otro integrante para no atascarme).

Si alguien no aparece al standup, los demás siguen y le pingean por DM. Si alguien está bloqueado y nadie sabe quién es el dueño del bloqueo, P1 lo absorbe y delega después; esto evita parálisis por consenso.

### 3.2 Commits y PRs

- Branches: `feature/<persona>/<descripcion-corta>` — por ejemplo `feature/p1/llm-triage-stub`.
- Commits convencionales: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Push diario obligatorio antes de las 22:00. Si alguien no pushea, su nombre aparece en el standup del día siguiente.
- PR a `main` requiere CI verde + 1 review. La review no puede bloquear más de 1 hora; si hay desacuerdo, se discute en el siguiente standup.
- _Pairing_ entre integrantes para code review: P1 ↔ P2, P3 ↔ P4. Cuando un integrante abre PR, hace tag al revisor por defecto.

### 3.3 Reglas de oro durante la implementación

1. **No tocar la doc arquitectónica.** El SAD, threat model y READMEs están sincronizados con la realidad. Cualquier cambio arquitectónico abre un ADR nuevo en lugar de modificar los docs existentes.
2. **No optimizar prematuramente.** El objetivo es que los UCs corran end-to-end, no que sean óptimos. Performance, latencia y cobertura de tests por encima del mínimo se ajustan al final, si queda tiempo.
3. **Los mocks son OK al inicio.** Si tu pieza depende de otra que aún no está lista, usa `FakeRedis`, mocked HTTP o synthetic data. La integración real se hace cuando ambas piezas están listas.
4. **Verificar en lab real al menos dos veces al día.** Cada integrante corre el flujo end-to-end en su Vagrant antes del almuerzo y antes de pushear al final del día. Esto detecta integraciones rotas temprano.
5. **Pedir ayuda en menos de 30 minutos.** Si llevas más de media hora atascado en un problema, pingueas en `#argos-help` o llamas a otro integrante. No quemar horas en debug solitario.

### 3.4 Lo que NO se entrega para el demo (consciente y documentado)

- Calibración _Q5 protocol_ con dataset etiquetado real (~100 ransomware + ~500 benignas) — queda para iteración post-demo.
- UC-03 _split-brain_ con 4 aprobadores reales no scripted — post-demo.
- UC-05 _stealth agent-kill_ end-to-end pulido — post-demo.
- PRs Sigma upstream aceptados por SigmaHQ maintainers (depende de tiempos externos).
- Video demo final editado.
- Informe técnico final pulido.
- Cross-encoder reranker en RAG (descartado del scope v1, ver ADR-0001 v2).

---

## 4. Manuales individuales

Cada integrante tiene un manual completo, organizado por orden de implementación (Fase 1 → 4), con comandos copy-paste, salidas esperadas literales, bloques de verificación al final de cada sección y apéndices de troubleshooting:

- **P1 (Enzo):** `manual-p1-enzo.md` — SOAR Decision Engine, HITL, Notificaciones, Integración cross-layer.
- **P2 (Sebastian):** `manual-p2-sebastian.md` — ML Layer 2 (Isolation Forest + OC-SVM + Shannon), LLM Triage Layer 4, RAG BM25+BGE.
- **P3 (Angeles):** `manual-p3-angeles.md` — Sigma + Wazuh (Layer 1), Canary FIM (Layer 3), Attack Simulators (ransomware + DDoS + SQLi).
- **P4 (Diego):** `manual-p4-diego.md` — Lab Vagrant/VirtualBox, PostgreSQL + pgAudit, OpenSearch, Redis, Streamlit Approval Console.

El PDF de cada integrante (`docs/team/pdf/argos-manual-p[N]-*.pdf`) tiene Parte I (intro común al proyecto) + Parte II (manual individual). Existe además una versión HTML interactiva (`docs/team/html/argos-manual-p[N]-*.html`) con botones de copia funcionales.

---

## 5. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Plan operacional inicial: decisión de deployment, flujo de demo, convenciones del equipo. | P1 |
| 2.0 | 2026-05-24 | Reorganización completa. Eliminadas todas las referencias a "sprint/semana 1/2/3". Reformateado para reflejar que es un manual operativo continuo hasta el deadline (2026-06-13), no un sprint de calendario. | P1 |
