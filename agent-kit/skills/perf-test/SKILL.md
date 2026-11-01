---
name: perf-test
description: Pruebas de performance/carga con k6 (o importando resultados de JMeter) contra el entorno local del proyecto, con límites de scope.yml, baseline y detección de regresiones en el SecQA Hub. Usar cuando el usuario pida "prueba de carga", "performance", "stress test", "k6", "jmeter", "cuánto aguanta".
---

# SecQA — Performance (k6 / JMeter)

Una prueba de carga sin límites es un ataque de denegación de servicio. Esta fase **solo** corre contra objetivos locales/propios que `scope.yml` autoriza, con un tope de usuarios virtuales.

## 1. Gate (obligatorio, cada vez)

```bash
secqa scope show                     # revisa performance.enabled, max_vus, allowed_profiles
secqa scope check <BASE_URL> --profile <perfil> --vus <N>
```

- Si sale con error, **detente** y explica el motivo al usuario. No lo esquives.
- `stress`, `spike` y `soak` requieren que el usuario lo confirme explícitamente **en esta sesión**; solo entonces añade `--confirm-heavy`.
- Empieza siempre por `smoke` para validar el script antes de una carga real.

## 2. Preparar endpoints

Si no existe `perf/endpoints.json`, créalo desde `perf/endpoints.example.json` con los `perf_candidates` de recon:
- Nombres estables (`"GET /api/items/{id}"`) — el Hub compara por nombre contra el baseline.
- Solo operaciones idempotentes o sobre datos de prueba. Nada que borre, pague o envíe emails reales.
- Credenciales: una cuenta de prueba creada para esto; pide al usuario los datos, no inventes.
- Pesos (`weight`) que reflejen el uso real.

## 3. Ejecutar

```bash
secqa run start --kind performance --name "<perfil> — <versión/rama>" --target <BASE_URL> --env local-docker
secqa audit "k6 run PROFILE=<perfil> VUS=<N>" --target <host:puerto>
k6 run -e BASE_URL=<BASE_URL> -e PROFILE=<perfil> -e VUS=<N> -e MAX_VUS=<performance.max_vus> \
       -e P95_MS=<umbral> -e ERROR_RATE=<umbral> perf/scenarios/endpoints.js
secqa ingest k6 secqa-out/k6-summary.json --scenario <perfil>
secqa run finish
```

Umbrales: usa `performance.thresholds` de `scope.yml` si existen; si no, p95 500 ms y error < 1 %.

Si k6 no está instalado: `brew install k6` / `choco install k6` / imagen `grafana/k6` (con `--network host` para llegar a localhost).

**JMeter** (si el equipo ya tiene planes `.jmx`): ejecútalo headless con salida CSV y súbelo:
```bash
jmeter -n -t <plan.jmx> -l secqa-out/results.jtl -Jjmeter.save.saveservice.output_format=csv
secqa ingest jtl secqa-out/results.jtl --scenario <perfil>
```

## 4. Interpretar y reportar

`secqa ingest` devuelve si pasaron los thresholds y cuántas regresiones hay frente al baseline. Si hay regresión, el Hub abre automáticamente un defecto `performance`.

Resume al usuario:
- p95/p99, throughput (req/s) y tasa de error totales y por endpoint (tabla corta),
- thresholds que fallaron,
- comparación con baseline (endpoint, métrica, antes → ahora, %),
- hipótesis de causa **marcadas como hipótesis** (N+1, falta de índice, sin caché, pool de conexiones), con dónde mirar en el código.

Si no hay baseline y la run es sana, sugiere marcarla: `secqa run update --baseline`.

## Reglas

- Nunca contra producción, staging compartido ni terceros; nunca sin `secqa scope check` exitoso.
- Nunca subas `MAX_VUS` por encima de `performance.max_vus`.
- Si la app empieza a devolver errores masivos o se cae, detén k6 (Ctrl+C) y repórtalo: es un hallazgo, no un motivo para reintentar con más carga.
- Si se ve un problema de seguridad (p. ej. sin rate limiting), regístralo además como hallazgo `api-rate-limiting` en una run de seguridad.
