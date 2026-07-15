# Política de seguridad

ARGOS es un proyecto de portafolio open-source, mantenido en modo *best-effort*.
No hay un equipo de seguridad dedicado ni SLA de respuesta.

## Reportar una vulnerabilidad

Usá **GitHub Private Vulnerability Reporting**, no issues públicos:

1. Andá a la pestaña **Security** del repositorio.
2. Elegí **Report a vulnerability**.
3. Describí el problema y, si podés, un caso reproducible.

El reporte queda privado hasta que se coordine una divulgación. Por favor no abras
un issue público ni un PR para vulnerabilidades sin explotar todavía.

## Alcance

- Este repo es un **prototipo de laboratorio académico**, no un producto de producción.
  No lo despliegues como está para defender infraestructura real.
- Los secretos del repo (`.env.example`, credenciales de lab en `docs/team/`) son
  placeholders o credenciales explícitamente de-solo-lab. Nunca reutilices esos valores.
- La suite de tests corre aislada de infraestructura externa; no hay servicios reales
  expuestos por el código de este repositorio.

## Versiones soportadas

Solo la rama `main`. No hay releases con soporte extendido.
