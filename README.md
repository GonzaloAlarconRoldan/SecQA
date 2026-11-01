# SecQA — Framework de QA de seguridad para Claude Code

Framework portable que convierte a Claude Code en un "pentester" dentro de cualquier
repositorio: detecta el stack automáticamente, busca vulnerabilidades (inyecciones,
secretos expuestos, dependencias vulnerables, riesgos de red y de API), y deja los
hallazgos en una base de datos local para que un humano los revise, apruebe, rechace
o complemente antes de generar un reporte.

No es un escáner específico de un lenguaje o framework — en la fase de recon detecta
qué tecnologías usa el proyecto objetivo y adapta qué herramientas invocar.

## Componentes

```
.claude/skills/        Skills de Claude Code que orquestan cada fase (ver abajo)
tools/db/               Esquema SQLite (findings.db) + script de inicialización
tools/server/           Dashboard de revisión local (API + UI) — sin dependencias externas
tools/report/           Generador de reportes HTML/PDF filtrados
tools/mapping/          Mapeo de categorías de hallazgo → OWASP / CWE / ISO-IEC 27001 Anexo A
scope.yml.example       Plantilla de alcance autorizado (hosts, agresividad permitida)
install.sh              Copia el framework dentro de otro proyecto
```

## Fases (skills)

1. **pentest-recon** — detecta lenguajes, frameworks, infraestructura, y si hay API.
2. **pentest-sast** — vulnerabilidades en el código fuente propio (inyecciones, XSS, IDOR, deserialización, etc.).
3. **pentest-sca** — dependencias con CVEs conocidos y misconfiguración de Dockerfiles/IaC.
4. **pentest-secrets** — credenciales y datos sensibles expuestos en el código/historial de git.
5. **pentest-api** — si hay API (REST/GraphQL/gRPC), pruebas específicas mapeadas a OWASP API Top 10.
6. **pentest-dast** — pruebas dinámicas y de red contra un entorno local controlado (solo con confirmación).
7. **pentest-report** — abre el dashboard de revisión o genera reportes HTML/PDF.
8. **pentest-run** — orquesta las fases anteriores en orden.

Cada skill está documentado en su propio `SKILL.md` dentro de `.claude/skills/`.

## Instalación en un proyecto objetivo

```bash
./install.sh /ruta/al/proyecto-objetivo
cd /ruta/al/proyecto-objetivo
cp scope.yml.example scope.yml   # edítalo: hosts permitidos, agresividad, autorización
python3 tools/db/init_db.py --db-path findings.db
```

Luego, dentro de Claude Code abierto en ese proyecto:

```
/pentest-run
```

## Revisar hallazgos (dashboard)

```bash
python3 tools/server/app.py --db-path findings.db --evidence-dir evidence
```

Abre `http://127.0.0.1:8787/`. Incluye dashboard con gráficos (severidad, estado,
tendencia por ejecución, categorías), switch ES/EN, filtros, y acciones de
aprobar/rechazar/añadir hallazgo manual. Todo corre localmente — los datos no salen
de la máquina.

## Generar reportes

```bash
# Global, solo lo aprobado
python3 tools/report/generate_report.py

# Por ejecución específica, con PDF
python3 tools/report/generate_report.py --run-id 3 --pdf

# Filtrado por severidad, en inglés
python3 tools/report/generate_report.py --severity critical high --lang en
```

## Principios de seguridad del propio framework

- Ninguna fase activa (DAST, pruebas dinámicas de API) corre sin que `scope.yml` autorice
  explícitamente el objetivo, y sin confirmación del usuario en la sesión.
- Solo se prueban objetivos locales/contenedores propios — nunca producción ni terceros.
- Toda acción activa queda registrada en `audit_log`.
- Los secretos detectados se enmascaran antes de guardarse como evidencia o en el reporte.
- El reporte compartible (`generate_report.py`) solo incluye hallazgos `approved`/`manual`
  por defecto — nunca `pending` sin validar.

## Requisitos

- Python 3.9+ (solo librería estándar para el dashboard y el runtime del framework).
- Herramientas externas opcionales según lo que detecte recon: `semgrep`, `osv-scanner`,
  `gitleaks`, `trivy`, `OWASP ZAP`, `nuclei`, `nmap`. El framework indica cuáles faltan
  en vez de fallar silenciosamente.
- Para export automático a PDF: un binario de Chrome/Chromium en el PATH (opcional,
  si no está, se puede exportar manualmente desde el navegador).

## Notas sobre ISO/IEC 27001

El mapeo en `tools/mapping/iso_owasp_map.json` referencia IDs y títulos de controles del
Anexo A de ISO/IEC 27001:2022 solo para trazabilidad — el texto completo de la norma es
material con copyright y no se reproduce aquí. Si tu organización tiene licencia del
estándar o un set de controles propio, extiende ese archivo.
