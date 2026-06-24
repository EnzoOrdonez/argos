# Texto para Exposición — P3 (Angeles Castillo)

## 1. Resumen corto de mi parte

Soy responsable de la **Capa 1 (detección basada en reglas)** y la **Capa 3
(canary files / engaño)** dentro de ARGOS. En la Capa 1 escribo reglas Sigma
mapeadas a MITRE ATT&CK y las convierto a formato Wazuh. En la Capa 3
construyo el generador de archivos cebo y la configuración de integridad
de archivos (FIM) que detecta cualquier toque sobre ellos con confianza
máxima. También construí los simuladores controlados que generan los
eventos de laboratorio para validar ambas capas.

---

## 2. Texto oral de 1 minuto

> "Yo como P3 me encargué de dos capas del sistema de defensa: la Capa 1,
> que es detección basada en reglas, y la Capa 3, que es la capa de
> engaño con archivos cebo.
>
> En la Capa 1 escribí nueve reglas Sigma — un formato estándar de la
> industria — cada una mapeada a una técnica específica de MITRE ATT&CK,
> como cifrado de archivos, eliminación de shadow copies, o inyección
> SQL. Esas reglas se convierten automáticamente a formato Wazuh, que es
> el motor que corre en producción.
>
> En la Capa 3 construí un generador que crea archivos 'cebo' — con
> nombres como 'passwords.txt' o 'financials.xlsx' — que un atacante
> priorizaría robar. Si alguien los toca, se dispara una alerta crítica
> con confianza del 95% o más, porque ningún usuario legítimo debería
> tocar esos archivos nunca.
>
> Además construí tres simuladores controlados, todos con salvaguardas
> de seguridad, para generar los eventos de laboratorio que prueban que
> mis reglas realmente disparan."

---

## 3. Texto oral de 2 minutos

> "Mi rol en ARGOS es P3, Detection Engineer, y cubro dos de las cuatro
> capas de defensa del sistema: la Capa 1 (reglas) y la Capa 3 (engaño).
>
> Para la Capa 1, escribí nueve reglas en formato Sigma — un estándar
> abierto usado por la industria de ciberseguridad — cubriendo ocho
> técnicas de MITRE ATT&CK: desde eliminación de shadow copies y
> escrituras de alta entropía, que son indicadores de ransomware, hasta
> patrones de denegación de servicio e inyección SQL. Cada regla sigue
> una disciplina estricta: tiene que tener un ID único, estar mapeada a
> una técnica MITRE válida, y tener al menos un test de Atomic Red Team
> asociado que demuestre que la regla realmente dispara ante el ataque
> real. Todo esto está validado con 73 tests automatizados que corren en
> cada cambio.
>
> Las reglas se convierten de Sigma a formato Wazuh nativo usando
> `sigma-cli`, y mantengo una matriz de trazabilidad en
> `mitre-mapping.yaml` que conecta cada técnica con las reglas que la
> cubren — esto es clave porque el motor de decisión del equipo, que
> maneja otro integrante, depende de que cada alerta venga con una
> técnica MITRE válida.
>
> Para la Capa 3, construí el generador de canary files: archivos señuelo
> con nombres realistas, contenido no vacío, y fechas de modificación
> simuladas entre 60 y 180 días atrás, para que parezcan archivos
> legítimos y antiguos. Combiné eso con configuración de integridad de
> archivos usando whodata en Windows y auditd en Linux, que captura
> exactamente qué usuario, proceso y PID tocó el archivo. La regla de
> Wazuh asociada dispara con severidad crítica — nivel 12 o 13 — y
> garantiza que la alerta llegue con toda la información que necesita el
> motor de decisión para aislar automáticamente sin pedir corroboración
> humana, porque este tipo de alerta tiene cero falsos positivos por
> diseño: nadie legítimo debería tocar esos archivos jamás.
>
> Finalmente, construí tres simuladores controlados —uno de ransomware,
> uno de denegación de servicio, y uno de inyección SQL— todos con
> salvaguardas: nunca ejecutan un comando real sin que yo confirme
> explícitamente el objetivo, bloquean direcciones IP públicas conocidas,
> y limitan la tasa de tráfico. Todo esto está confinado a un entorno de
> laboratorio aislado y nunca toca infraestructura real."

---

## 4. Posibles preguntas del profesor con respuestas simples

**P: ¿Por qué Sigma y no reglas nativas de Wazuh directamente?**
R: Sigma es un formato independiente de la herramienta — las mismas reglas se pueden convertir a Wazuh, Splunk, o Elastic. Eso hace que el trabajo sea reutilizable y, de hecho, parte del plan es enviar algunas reglas como contribución abierta al repositorio oficial de SigmaHQ.

**P: ¿Qué pasa si el atacante sabe que existen los canary files?**
R: Por diseño, la Capa 3 es complementaria, no la única defensa — por eso existen las otras capas. Pero mitigamos parcialmente nombrando los canaries con patrones que un atacante priorizaría de forma realista, y en producción (fuera del alcance académico) se randomizaría la colocación por host.

**P: ¿Cómo sabes que tus reglas no generan demasiados falsos positivos?**
R: Cada regla documenta sus falsos positivos esperados en el campo `falsepositives`, y el plan incluye medir la tasa de FP contra una línea base de actividad benigna de 24-48 horas una vez el laboratorio esté arriba.

**P: ¿Por qué la regla de canary tiene severidad tan alta?**
R: Porque es zero-FP por diseño: ningún proceso legítimo debería tocar esos archivos nunca, así que cualquier toque es, casi con certeza, malicioso. Eso permite que el motor de decisión actúe sin esperar corroboración de otras capas.

**P: ¿Probaste esto contra un ataque real?**
R: Las reglas y los tests están validados sintácticamente y contra fixtures sintéticos. La validación contra el laboratorio real con Atomic Red Team y los simuladores depende de que la infraestructura (Vagrant, Wazuh manager, hosts víctima) esté levantada por el integrante responsable de esa parte.

---

## 5. Qué decir si preguntan por ML, SOAR, LLM o infraestructura

> "Esa parte no es mi responsabilidad — yo cubro las capas 1 y 3, que son
> detección por reglas y engaño. El procesamiento con machine learning,
> la orquestación de respuesta automática (SOAR), el triage con modelos
> de lenguaje, y la infraestructura del laboratorio las maneja el resto
> del equipo. Lo que yo entrego es la alerta cruda con toda la
> información necesaria — técnica MITRE, severidad, y contexto del
> proceso — para que esas otras capas la consuman correctamente."

No improvisar detalles de esas partes — si insisten, ofrecer pasar la palabra al integrante correspondiente.

---

## 6. Checklist antes de presentar

- [ ] Confirmar que `sigma-cli check detection/sigma-rules/` corre sin errores en tu máquina.
- [ ] Confirmar que `pytest detection/tests/ deception/tests/ -v` muestra todos los tests en verde.
- [ ] Tener a la mano una captura de pantalla del generador de canaries corriendo en modo `--local-sandbox` (por si el lab real no está listo el día de la demo).
- [ ] Tener a la mano la salida de `uc01_lockbit_like.py --run` como evidencia visual del flujo completo.
- [ ] Revisar que sepas explicar, en una frase, qué es MITRE ATT&CK, qué es Sigma, y qué es whodata — el profesor puede preguntar definiciones básicas.
- [ ] Tener claro qué está pendiente de P4 (infraestructura) para no comprometerte a mostrar algo que no depende de ti.
- [ ] Repasar el límite de tu alcance: no profundizar en ml/, soar/, llm_triage/ ni ui/ aunque te pregunten — redirige cordialmente.
