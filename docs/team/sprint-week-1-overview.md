# Sprint Semana 1 — Plan Operacional General

| Field | Value |
|-------|-------|
| Type | Operational plan + deployment decision record |
| Status | Active |
| Sprint window | 7 días calendario consecutivos |
| Goal | UC-01 + UC-02 + UC-04 + UC-06 + UC-07 corriendo end-to-end con dos rehearsals al final del domingo (per ADR-0008 multi-vector). UC-08 nice-to-have. |
| Owner | P1 (Enzo Ordoñez Flores) coordina, los 4 integrantes ejecutan |

---

## 0. Por qué esta documentación existe

Este documento captura decisiones operacionales que se tomaron por conversación pero no estaban en el SAD ni en ningún ADR. Sin esta página, esas decisiones se pierden y el equipo improvisa en el peor momento (el demo). Tres bloques de contenido viven aquí: la decisión del modelo de deployment, el flujo del demo, y la convención de la semana.

---

## 1. Modelo de deployment — decisión

**Modelo elegido: 100% local en Vagrant + laptop espejo en P1 como hot spare + datos móviles del equipo como respaldo de conectividad para servicios externos (OpenAI / Telegram / Discord / Twilio).**

### Razón

Cada hop de red real entre componentes es un punto de falla. El modelo 100% local concentra los hops en localhost (que no falla), dejando red real sólo para los 4 servicios externos genuinamente cloud. El modelo hybrid (Wazuh + OpenSearch + Redis en VPS Hetzner) agrega ~10 hops de red entre laptop víctima y manager remoto, además de configuración no-trivial de VPN/firewall para no exponer Redis y OpenSearch a internet. La ventaja del hybrid (P4 deja de ser SPOF) se resuelve mejor con un lab espejo local en P1 que con cloud.

### Lo que cada hop de red real cubre

- LLM Triage → OpenAI API (mitigable con `LLM_BACKEND=llama_local` que cae a Llama 3.1 local vía Ollama, zero-egress).
- Notification Service → Telegram Bot API.
- Notification Service → Discord webhook.
- Notification Service → Twilio API (sólo para escalación T2 a t=60s).

Todo lo demás (Wazuh agent → manager → ML consumer → SOAR → Approval Console) es localhost dentro del lab Vagrant.

### Resiliencia operacional

- **Lab primario:** laptop de P4 (Diego). Vagrantfile + scripts en `lab/`.
- **Lab espejo:** laptop de P1 (Enzo). Mismo Vagrantfile clonado del repo, `vagrant up` independiente.
- **Decisión de qué lab usar el día del demo:** se decide 4 horas antes según cuál esté más estable. La transición entre uno y otro es: cambiar la URL del Wazuh manager en `.env` y reiniciar servicios. No hay re-configuración de red.
- **SSD externo (opcional, recomendado):** P4 instala las VMs en un SSD USB-C de 256 GB (~$30 USD). Si su laptop falla, conecta el SSD a otro equipo con VirtualBox y bootea. Eso es la tercera línea de defensa.
- **Video respaldo:** P4 graba el demo completo 1-2 días antes con todo funcionando. Si todo falla en vivo, narra sobre el video. Pierdes impacto pero salvas la presentación.

### Internet del salón de exposición

- **WiFi institucional:** se prueba al menos una semana antes del demo. Si hay captive portal o bloqueo de puertos a `api.openai.com`, `api.telegram.org`, `api.twilio.com`, no se usa.
- **Datos móviles como respaldo:** P1 y P4 tienen sus celulares con hotspot configurado y plan con datos suficientes. Cubren WiFi bloqueado pero **no resuelven latencia variable**. Con el modelo 100% local esto no afecta la pipeline crítica (todo es localhost), sólo las notificaciones externas, que toleran latencia.
- **Si todo internet cae:** el sistema sigue funcionando con `LLM_BACKEND=llama_local` y email post-facto a MailHog local. UC-01 y UC-02 sobreviven sin internet. UC-04 con two-person rule sobrevive si los aprobadores están físicamente en la sala mirando la Streamlit Console (que es localhost).

### Lo que NO se va a nube en ninguna fase

- VMs víctima (Windows + Linux). Son donde el ransomware corre.
- PostgreSQL en producción (activo defendido). Vive en la Linux VM.
- Simulador de ransomware. Corre donde están las víctimas.
- Canary files con FIM whodata.

Estos componentes son el "núcleo del demo" — moverlos a cloud pierde la narrativa "estoy atacando un sistema real frente a ustedes".

---

## 2. Flujo del demo en vivo

### Setup pre-demo (T-1 hora)

1. P4 arranca lab primario con `vagrant up`. Verifica con `curl https://localhost:55000` (Wazuh API) que responde.
2. P4 arranca todos los servicios Python con `make demo-up` (script que levanta SOAR Decision Engine, LLM Triage, Approval API, Streamlit Console).
3. P4 verifica que Streamlit Approval Console responde en `http://localhost:8501`.
4. P1 arranca lab espejo en su laptop como hot spare. Mismo procedimiento, no proyectado.
5. Los 4 integrantes verifican que el bot Telegram envía mensaje de prueba a su celular ("ARGOS demo ready").
6. P4 conecta laptop primario al proyector.

### Ejecución del demo (12-13 min total)

| Tiempo | UC | Acción | Pantalla |
|--------|----|--------|----------|
| 0:00-2:00 | UC-01 | P4 ejecuta `python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc01 --target windows-victim` | Streamlit Console muestra 3 capas firing → T0 → auto-isolate. Audiencia ve archivos cifrándose en Windows VM. |
| 2:00-3:30 | UC-02 | P4 ejecuta `python attack-simulation/ransomware_simulator/canary_path.py --target linux-victim` | Console muestra Layer 3 sola firing → T0 → aislamiento sin que se cifre un solo archivo real. |
| 3:30-7:00 | UC-04 | P4 ejecuta `python attack-simulation/ransomware_simulator/postgres_attack.py --target linux-victim` | Two-person rule: 4 integrantes reciben Telegram, P1 y P2 aprueban en sus celulares, P3 espera, P4 timeout. Sistema espera 2 aprobaciones, luego ejecuta. |
| 7:00-12:00 | Q&A | Profesor pregunta | Mostrar audit log en OpenSearch Dashboards |

### Rol de cada integrante durante el demo

- **P4 (Diego):** Operador del demo. Ejecuta los comandos, navega entre pantallas, controla el proyector. Cualquier crash, él reinicia.
- **P1 (Enzo):** Narrador principal. Explica qué está pasando en cada pantalla. Tiene laptop espejo abierta por si hay que conmutar.
- **P2 (Sebastian):** Aprobador 1 en UC-04. Explica la capa ML cuando salga ML score en pantalla.
- **P3 (Angeles):** Aprobador 2 en UC-04. Explica las reglas Sigma cuando salgan disparadas.

---

## 3. Convenciones del sprint

### Standup diario (20 min, 9:00 AM)

Discord, canal `#argos-standup`, llamada de voz. Cada integrante 3 minutos:
- Lo que cerré ayer (PRs mergeados, tests passing).
- Lo que cierro hoy (objetivos del día).
- Bloqueos (qué necesito de otro integrante para no atascarme).

Si alguien no aparece al standup, los demás siguen y le pingean por DM. Si alguien está bloqueado y nadie sabe quién es el dueño del bloqueo, P1 lo absorbe y delega después — esto evita parálisis por consenso.

### Commits y PRs

- Branches: `feature/<persona>/<descripcion-corta>` — ejemplo: `feature/p1/llm-triage-stub`.
- Commits convencionales: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Push diario obligatorio antes de las 22:00. Si alguien no pushea, su nombre aparece en el standup del día siguiente.
- PR a `main` requiere CI verde + 1 review. Review no puede bloquear más de 1 hora; si hay desacuerdo, se discute en el siguiente standup.
- Pairing entre integrantes para code review: P1 ↔ P2, P3 ↔ P4. Cuando un integrante abre PR, hace tag al revisor por defecto.

### Reglas de oro durante la semana

1. **No tocar la doc.** Los docs están sincronizados con la realidad. Si cambias algo arquitectónico, abre un ADR nuevo. No toques el SAD, threat model, READMEs durante esta semana.
2. **No optimizar prematuramente.** El objetivo es que las 3 demos corran end-to-end, no que sean óptimas. Performance, latencia, cobertura de tests por encima del mínimo se ajustan en la semana 2.
3. **Mocks son OK al inicio.** Si tu pieza depende de otra que aún no está lista, usa FakeRedis, mocked HTTP, o synthetic data. La integración real se hace cuando ambas piezas están listas.
4. **Verificar en lab real al menos 2 veces al día.** Cada integrante corre el flujo end-to-end en su Vagrant antes del almuerzo y antes de pushear al final del día. Esto detecta integraciones rotas temprano.
5. **Pedir ayuda en menos de 30 minutos.** Si llevas más de media hora atascado en un problema, pingueas en `#argos-help` o llamas a otro integrante. No quemar horas en debug solitario.

### Lo que NO se entrega esta semana (consciente y documentado)

- Calibración Q5 protocol con dataset etiquetado de ~600 alertas (semana 2).
- UC-03 split-brain con 4 aprobadores reales no scripted (semana 2 o 3).
- UC-05 stealth agent-kill (semana 2).
- PRs Sigma upstream aceptados por maintainers (depende de tiempos externos, semana 2-3).
- Video demo final pulido y editado (semana 3).
- Informe técnico final (semana 3).
- Cross-encoder reranker en RAG (descartado del scope v1 per ADR-0001 v2).

### Manuales individuales

Cada integrante tiene su propio manual día-a-día con comandos, instalaciones, y troubleshooting:

- **P1 (Enzo):** `sprint-week-1-p1-enzo.md` (incluido en este sprint)
- **P2 (Sebastian):** `sprint-week-1-p2-sebastian.md` (a generar — pendiente)
- **P3 (Angeles):** `sprint-week-1-p3-angeles.md` (a generar — pendiente)
- **P4 (Diego):** `sprint-week-1-p4-diego.md` (a generar — pendiente)

---

## 4. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial sprint operational plan. Documenta decisión de deployment (100% local + hot spare), flujo de demo, convenciones del sprint, y reglas operacionales que no estaban en otros docs del repo. | P1 |
