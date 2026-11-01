<div align="center">

# SecQA

**QA de seguridad y performance asistido por IA para Claude Code, con un Hub central de ejecuciones, casos de prueba y defectos.**

[English](README.md) · [Arquitectura](docs/architecture.md) · [Integraciones](docs/integrations.md) · [Despliegue](docs/deployment.md)

![SecQA Hub](docs/images/overview.png)

</div>

SecQA convierte a Claude Code en un tester de seguridad y performance para cualquier repositorio. Detecta el stack, corre los escáneres adecuados (SAST, SCA, secretos, API, DAST) y pruebas de carga con k6. Todo lo que encuentra llega al **SecQA Hub**, donde las personas hacen el triage, gestionan defectos con SLA y siguen las tendencias entre ejecuciones.

## Qué incluye

- **Skills de Claude Code** que eligen herramientas según el stack y se detienen si algo está fuera de scope: `/pentest-run`, `/perf-test`, `/pentest-report`…
- **Hub web multi-proyecto**:
  - dashboard con KPIs (defectos abiertos, SLA vencidos, MTTR, pass rate),
  - ejecuciones con su detalle,
  - triage de hallazgos en lote,
  - gestor de defectos e incidentes (tabla + kanban, comentarios, adjuntos, historial),
  - repositorio de casos de prueba,
  - tendencias de performance,
  - matriz de cumplimiento OWASP / ISO 27001,
  - reportes HTML/PDF en ES/EN.
- **Memoria de decisiones**: los falsos positivos siguen suprimidos en próximas runs, y si un hallazgo de un defecto cerrado reaparece, el defecto se reabre solo.
- **Performance con baseline**: perfiles k6 (smoke, load, stress, spike, soak) limitados por `scope.yml`. Métricas por endpoint, detección automática de regresiones y un defecto abierto cuando hay regresión. También importa resultados de JMeter.
- **Formatos estándar**: SARIF, k6, JMeter JTL, JUnit → Hub → HTML/PDF, CSV, SARIF para GitHub.
- **Seguro por defecto**: solo objetivos autorizados, tope de usuarios virtuales en las pruebas de carga, auditoría de cada comando activo, secretos enmascarados, y reportes que solo contienen datos validados por una persona.

## Inicio rápido

### Demo (2 minutos)

```bash
git clone https://github.com/GonzaloAlarconRoldan/SecQA && cd SecQA
docker compose -f examples/demo/docker-compose.yml up --build
```

Abre **http://127.0.0.1:8787**. El Hub viene con 12 semanas de historial de OWASP Juice Shop, que corre en `127.0.0.1:3000` como objetivo real.

### En tu proyecto

```bash
pip install "secqa[hub] @ git+https://github.com/GonzaloAlarconRoldan/SecQA"
secqa hub serve
secqa init /ruta/a/tu-proyecto --project SHOP
cd /ruta/a/tu-proyecto
secqa project create SHOP --name "Shop API"
cp scope.yml.example scope.yml      # hosts permitidos, límites de carga, quién autoriza
```

Y en Claude Code: `/pentest-run`, `/perf-test`, `/pentest-report`.

## Uso responsable

Prueba **solo** sistemas propios o para los que tengas autorización explícita. Las fases activas exigen un `scope.yml` con los objetivos permitidos y quién los autoriza. Las pruebas de carga solo corren contra hosts locales o propios, con tope de `max_vus`, y los perfiles pesados piden confirmación cada vez. Ver [SECURITY.md](SECURITY.md).

## Licencia

[MIT](LICENSE) © Gonzalo Alarcón Roldán
