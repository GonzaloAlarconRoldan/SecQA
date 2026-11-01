---
name: secqa-setup
description: Prepara el entorno de SecQA en esta máquina y proyecto — instala los escáneres que el framework usa (semgrep, gitleaks, osv-scanner, k6 y opcionales), verifica la conexión con el Hub, el proyecto y scope.yml. Usar la primera vez que se usa SecQA, cuando el usuario diga "instala lo necesario", "prepara el entorno", "setup", o cuando otra skill detecte herramientas faltantes.
---

# SecQA — Setup del entorno

SecQA no trae escáneres propios: orquesta herramientas externas y sube sus resultados al Hub. Esta skill deja la máquina lista para que `/pentest-run` y `/perf-test` funcionen con cobertura completa.

## 1. Diagnóstico

```bash
secqa --json doctor --all
```

Resume al usuario en una tabla corta: herramienta, para qué sirve, si está instalada, y el comando que se usaría para instalarla.

- **core** (semgrep, gitleaks, osv-scanner, k6): necesarias para la cobertura por defecto.
- **optional** (trivy, nuclei, zap, jmeter): solo si el usuario va a hacer DAST, IaC o tiene planes JMeter.

Si `secqa` no existe, el framework no está instalado: `pip install "secqa @ git+https://github.com/GonzaloAlarconRoldan/SecQA"` (pregunta antes).

## 2. Instalar (con permiso)

Instalar software en la máquina del usuario es una acción que él debe aprobar:

1. Muestra los comandos exactos que se ejecutarán (vienen en `install_cmd`).
2. Pregunta: ¿instalo las core? ¿también alguna opcional?
3. Solo con un sí explícito:
   ```bash
   secqa doctor --install --yes                 # core
   secqa doctor --install --yes --only trivy,nuclei   # opcionales elegidas
   ```
4. Vuelve a correr `secqa doctor` y confirma el resultado. Si algo falló, muestra el error y el enlace `docs` de esa herramienta; no lo intentes por otras vías (curl | sh, sudo) sin preguntar.

Casos especiales:
- Sin gestor de paquetes (`package_managers` vacío): en macOS sugiere instalar Homebrew (https://brew.sh); en Windows, winget o scoop; en Linux, pipx/go o Homebrew. No los instales tú sin permiso.
- Herramientas instaladas con `go install` quedan en `$(go env GOPATH)/bin`: avisa si no está en el PATH.
- **ZAP** no tiene paquete simple: se usa vía Docker (`docker run -t zaproxy/zap-stable zap-baseline.py -t <url>`), y solo dentro de scope.

## 3. Hub, proyecto y scope

```bash
secqa status                  # ¿responde el Hub? ¿qué proyecto?
```

- Hub caído → ofrece `secqa hub serve` (en segundo plano) o `docker compose up -d`.
- Sin proyecto en `.secqa/config.yml` → pregunta la KEY y ejecuta `secqa project create KEY --name "…"`.
- Sin `scope.yml` → cópialo de `scope.yml.example` y **pide al usuario** los hosts/puertos permitidos, si habilita performance (`max_vus`) y quién autoriza. No inventes la autorización.
- Crea `secqa-out/` si no existe (k6 no crea carpetas).

## 4. Cierre

Resume: herramientas listas, Hub y proyecto, estado del scope, y siguiente paso (`/pentest-run` o `/perf-test`).
