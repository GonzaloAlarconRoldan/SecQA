"""Deterministic technology detection for the project under test (`secqa detect`).

Reads manifests and lockfiles — never executes project code — and returns languages, frameworks,
infrastructure, API surface and an inventory of components with exact versions where a lockfile
pins them. The inventory feeds `secqa intel`, which checks it against official vulnerability feeds.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "vendor", ".next",
             ".nuxt", "target", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage", ".gradle",
             ".idea", ".vscode", "secqa-out", ".secqa", ".secqa-data", "site-packages", "bower_components"}
MAX_FILES = 50_000

LANG_EXT = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".rs": "Rust", ".scala": "Scala", ".swift": "Swift", ".c": "C", ".cpp": "C++",
    ".vue": "Vue", ".svelte": "Svelte", ".sql": "SQL", ".tf": "Terraform",
}

# package name (lower) → (kind, label)
KNOWN = {
    # web frameworks
    "express": ("framework", "Express"), "next": ("framework", "Next.js"), "react": ("framework", "React"),
    "@angular/core": ("framework", "Angular"), "vue": ("framework", "Vue"), "@nestjs/core": ("framework", "NestJS"),
    "fastify": ("framework", "Fastify"), "koa": ("framework", "Koa"), "nuxt": ("framework", "Nuxt"),
    "svelte": ("framework", "Svelte"), "hapi": ("framework", "hapi"), "@hapi/hapi": ("framework", "hapi"),
    "django": ("framework", "Django"), "flask": ("framework", "Flask"), "fastapi": ("framework", "FastAPI"),
    "starlette": ("framework", "Starlette"), "tornado": ("framework", "Tornado"), "rails": ("framework", "Rails"),
    "sinatra": ("framework", "Sinatra"), "laravel/framework": ("framework", "Laravel"),
    "symfony/symfony": ("framework", "Symfony"), "github.com/gin-gonic/gin": ("framework", "Gin"),
    "github.com/labstack/echo/v4": ("framework", "Echo"), "github.com/gofiber/fiber/v2": ("framework", "Fiber"),
    "org.springframework.boot:spring-boot-starter-web": ("framework", "Spring Boot"),
    "org.springframework.boot:spring-boot-starter": ("framework", "Spring Boot"),
    "actix-web": ("framework", "Actix"), "axum": ("framework", "Axum"), "rocket": ("framework", "Rocket"),
    # data / ORM
    "sequelize": ("db", "Sequelize"), "prisma": ("db", "Prisma"), "@prisma/client": ("db", "Prisma"),
    "typeorm": ("db", "TypeORM"), "mongoose": ("db", "MongoDB (Mongoose)"), "mongodb": ("db", "MongoDB"),
    "pg": ("db", "PostgreSQL"), "mysql": ("db", "MySQL"), "mysql2": ("db", "MySQL"), "sqlite3": ("db", "SQLite"),
    "knex": ("db", "Knex"), "sqlalchemy": ("db", "SQLAlchemy"), "psycopg": ("db", "PostgreSQL"),
    "psycopg2": ("db", "PostgreSQL"), "psycopg2-binary": ("db", "PostgreSQL"), "pymongo": ("db", "MongoDB"),
    "redis": ("db", "Redis"), "ioredis": ("db", "Redis"), "gorm.io/gorm": ("db", "GORM"),
    # auth
    "jsonwebtoken": ("auth", "JWT (jsonwebtoken)"), "passport": ("auth", "Passport"),
    "express-session": ("auth", "express-session"), "next-auth": ("auth", "NextAuth"),
    "pyjwt": ("auth", "PyJWT"), "python-jose": ("auth", "python-jose"), "django-allauth": ("auth", "django-allauth"),
    "devise": ("auth", "Devise"), "github.com/golang-jwt/jwt/v5": ("auth", "golang-jwt"),
    # API
    "graphql": ("api", "GraphQL"), "apollo-server": ("api", "Apollo GraphQL"),
    "@apollo/server": ("api", "Apollo GraphQL"),
    "graphene": ("api", "Graphene GraphQL"), "strawberry-graphql": ("api", "Strawberry GraphQL"),
    "@grpc/grpc-js": ("api", "gRPC"), "grpcio": ("api", "gRPC"), "swagger-ui-express": ("api", "Swagger UI"),
}


@dataclass
class Component:
    ecosystem: str  # OSV ecosystem names: npm, PyPI, Go, Maven, RubyGems, Packagist, crates.io, NuGet
    name: str
    version: str | None  # exact version when pinned by a lockfile, else None
    spec: str | None = None  # declared range, e.g. ^4.17.0
    direct: bool = True
    dev: bool = False
    source: str = ""


@dataclass
class StackReport:
    root: str
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    auth: list[str] = field(default_factory=list)
    api_kind: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    has_docker: bool = False
    docker_images: list[str] = field(default_factory=list)
    exposed_ports: list[int] = field(default_factory=list)
    iac: list[str] = field(default_factory=list)
    api_spec_files: list[str] = field(default_factory=list)
    env_files: list[str] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)

    @property
    def has_api(self) -> bool:
        return bool(self.api_spec_files or self.api_kind)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["has_api"] = self.has_api
        d["component_count"] = len(self.components)
        d["pinned_count"] = sum(1 for c in self.components if c.version)
        return d


def _walk(root: Path, exclude: list[str]):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                       and not any(os.path.join(rel_dir, d).lstrip("./").startswith(e.rstrip("/")) for e in exclude)]
        for f in filenames:
            count += 1
            if count > MAX_FILES:
                return
            yield Path(dirpath) / f


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ---- ecosystem parsers -----------------------------------------------------

def _npm(root: Path, p: Path, rep: StackReport) -> None:
    rel = _rel(root, p)
    if p.name == "package.json":
        data = json.loads(p.read_text("utf-8"))
        for section, dev in (("dependencies", False), ("devDependencies", True)):
            for name, spec in (data.get(section) or {}).items():
                rep.components.append(Component("npm", name, _exact(spec), str(spec), True, dev, rel))
    elif p.name == "package-lock.json":
        data = json.loads(p.read_text("utf-8"))
        for key, meta in (data.get("packages") or {}).items():
            if not key or "node_modules/" not in key or not meta.get("version"):
                continue
            name = key.rsplit("node_modules/", 1)[1]
            rep.components.append(Component("npm", name, meta["version"], None, False, bool(meta.get("dev")), rel))
        if not data.get("packages"):  # lockfile v1
            for name, meta in (data.get("dependencies") or {}).items():
                if meta.get("version"):
                    rep.components.append(Component("npm", name, meta["version"], None, False,
                                                    bool(meta.get("dev")), rel))


_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(==|>=|~=|<=|>|<|!=)?\s*([^\s;#,]+)?")


def _python(root: Path, p: Path, rep: StackReport) -> None:
    rel = _rel(root, p)
    name = p.name.lower()
    if name.startswith("requirements") and name.endswith(".txt"):
        for line in p.read_text("utf-8", errors="replace").splitlines():
            if line.strip().startswith(("#", "-")):
                continue
            m = _REQ_RE.match(line)
            if m:
                op, ver = m.group(2), m.group(3)
                rep.components.append(Component("PyPI", m.group(1), ver if op == "==" else None,
                                                f"{op}{ver}" if op else None, True, "dev" in name, rel))
    elif name == "pyproject.toml":
        data = tomllib.loads(p.read_text("utf-8"))
        project = data.get("project") or {}
        groups = [("", project.get("dependencies") or [])]
        groups += list((project.get("optional-dependencies") or {}).items())
        groups += list((data.get("dependency-groups") or {}).items())
        for group, deps in groups:
            is_dev = group.lower() in ("dev", "test", "tests", "lint", "docs", "typing")
            for dep in deps:
                m = _REQ_RE.match(dep) if isinstance(dep, str) else None
                if m and m.group(1).lower() != project.get("name", "").lower():
                    rep.components.append(Component("PyPI", m.group(1), m.group(3) if m.group(2) == "==" else None,
                                                    dep, True, is_dev, rel))
        poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        for dep, spec in poetry.items():
            if dep.lower() != "python":
                rep.components.append(Component("PyPI", dep, None, str(spec), True, False, rel))
    elif name in ("poetry.lock", "uv.lock"):
        data = tomllib.loads(p.read_text("utf-8"))
        for pkg in data.get("package") or []:
            if pkg.get("name") and pkg.get("version"):
                rep.components.append(Component("PyPI", pkg["name"], pkg["version"], None, False,
                                                pkg.get("category") == "dev", rel))
    elif name == "pipfile.lock":
        data = json.loads(p.read_text("utf-8"))
        for section, dev in (("default", False), ("develop", True)):
            for dep, meta in (data.get(section) or {}).items():
                ver = str(meta.get("version", "")).lstrip("=")
                rep.components.append(Component("PyPI", dep, ver or None, None, True, dev, rel))


_GO_REQ = re.compile(r"^\s*([\w./-]+\.[\w./-]+)\s+(v[\w.+-]+)(\s*//\s*indirect)?")


def _go(root: Path, p: Path, rep: StackReport) -> None:
    in_block = False
    for line in p.read_text("utf-8").splitlines():
        s = line.strip()
        if s.startswith("require ("):
            in_block = True
            continue
        if in_block and s == ")":
            in_block = False
            continue
        target = s[len("require "):] if s.startswith("require ") else (s if in_block else "")
        m = _GO_REQ.match(target)
        if m:
            rep.components.append(Component("Go", m.group(1), m.group(2), None, not m.group(3), False,
                                            _rel(root, p)))


def _maven(root: Path, p: Path, rep: StackReport) -> None:
    from defusedxml import ElementTree

    tree = ElementTree.parse(p)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    props = {el.tag.split("}")[-1]: (el.text or "") for el in tree.findall(".//m:properties/*", ns)}
    for dep in tree.findall(".//m:dependencies/m:dependency", ns):
        g, a = dep.findtext("m:groupId", "", ns), dep.findtext("m:artifactId", "", ns)
        v = dep.findtext("m:version", "", ns) or None
        if v and v.startswith("${"):
            v = props.get(v[2:-1]) or None
        scope = dep.findtext("m:scope", "", ns)
        rep.components.append(Component("Maven", f"{g}:{a}", v, None, True, scope == "test", _rel(root, p)))


def _gemfile_lock(root: Path, p: Path, rep: StackReport) -> None:
    in_specs = False
    for line in p.read_text("utf-8").splitlines():
        if line.strip() == "specs:":
            in_specs = True
            continue
        if in_specs and not line.startswith("    "):
            in_specs = line.startswith("  ") and not line.strip().endswith(":")
        m = re.match(r"^    ([A-Za-z0-9_.-]+) \(([^)]+)\)$", line)
        if m:
            rep.components.append(Component("RubyGems", m.group(1), m.group(2), None, False, False, _rel(root, p)))


def _composer_lock(root: Path, p: Path, rep: StackReport) -> None:
    data = json.loads(p.read_text("utf-8"))
    for section, dev in (("packages", False), ("packages-dev", True)):
        for pkg in data.get(section) or []:
            rep.components.append(Component("Packagist", pkg["name"], str(pkg.get("version", "")).lstrip("v") or None,
                                            None, False, dev, _rel(root, p)))


def _cargo_lock(root: Path, p: Path, rep: StackReport) -> None:
    data = tomllib.loads(p.read_text("utf-8"))
    for pkg in data.get("package") or []:
        if "source" in pkg:  # skip the workspace's own crates
            rep.components.append(Component("crates.io", pkg["name"], pkg["version"], None, False, False,
                                            _rel(root, p)))


def _csproj(root: Path, p: Path, rep: StackReport) -> None:
    for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', p.read_text("utf-8")):
        rep.components.append(Component("NuGet", m.group(1), m.group(2), None, True, False, _rel(root, p)))


PARSERS = {
    "package.json": ("npm", _npm), "package-lock.json": ("npm", _npm),
    "requirements.txt": ("pip", _python), "pyproject.toml": ("pip", _python), "poetry.lock": ("poetry", _python),
    "uv.lock": ("uv", _python), "pipfile.lock": ("pipenv", _python), "go.mod": ("go", _go),
    "pom.xml": ("maven", _maven), "gemfile.lock": ("bundler", _gemfile_lock),
    "composer.lock": ("composer", _composer_lock), "cargo.lock": ("cargo", _cargo_lock),
}
UNPARSED_LOCKS = {"yarn.lock": "yarn", "pnpm-lock.yaml": "pnpm", "gradle.lockfile": "gradle",
                  "build.gradle": "gradle", "build.gradle.kts": "gradle", "mix.lock": "mix"}


def _exact(spec: Any) -> str | None:
    s = str(spec).strip()
    return s if re.fullmatch(r"\d+(\.\d+){1,3}([-+][\w.]+)?", s) else None


# ---- infra -----------------------------------------------------------------

def _dockerfile(root: Path, p: Path, rep: StackReport) -> None:
    rep.has_docker = True
    for line in p.read_text("utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", line, re.I)
        if m and m.group(1).lower() != "scratch" and "$" not in m.group(1):
            rep.docker_images.append(m.group(1))
        m = re.match(r"^\s*EXPOSE\s+(.+)", line, re.I)
        if m:
            rep.exposed_ports += [int(x.split("/")[0]) for x in m.group(1).split() if x.split("/")[0].isdigit()]


def _compose(root: Path, p: Path, rep: StackReport) -> None:
    rep.has_docker = True
    data = yaml.safe_load(p.read_text("utf-8")) or {}
    for svc in (data.get("services") or {}).values():
        if not isinstance(svc, dict):
            continue
        if svc.get("image") and "$" not in str(svc["image"]):
            rep.docker_images.append(str(svc["image"]))
        for port in svc.get("ports") or []:
            host = str(port.get("published", "") if isinstance(port, dict) else port).split(":")
            published = host[-2] if len(host) >= 2 else host[0]
            if published.split("/")[0].isdigit():
                rep.exposed_ports.append(int(published.split("/")[0]))


def detect(root: str | Path, exclude: list[str] | None = None) -> StackReport:
    root = Path(root).resolve()
    rep = StackReport(root=str(root))
    langs: Counter[str] = Counter()
    managers: set[str] = set()
    for path in _walk(root, exclude or []):
        name = path.name.lower()
        rel = _rel(root, path)
        if path.suffix in LANG_EXT:
            langs[LANG_EXT[path.suffix]] += 1
        parser_key = "requirements.txt" if name.startswith("requirements") and name.endswith(".txt") else name
        try:
            if parser_key in PARSERS:
                mgr, fn = PARSERS[parser_key]
                managers.add(mgr)
                rep.manifests.append(rel)
                fn(root, path, rep)
            elif path.suffix == ".csproj":
                managers.add("nuget")
                rep.manifests.append(rel)
                _csproj(root, path, rep)
            elif name in UNPARSED_LOCKS:
                managers.add(UNPARSED_LOCKS[name])
                rep.unparsed.append(rel)
            elif name == "dockerfile" or name.endswith(".dockerfile") or name.startswith("dockerfile."):
                _dockerfile(root, path, rep)
            elif name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                _compose(root, path, rep)
            elif path.suffix == ".tf":
                rep.iac.append(rel)
            elif path.suffix in (".yml", ".yaml", ".json") and path.stat().st_size < 2_000_000:
                head = path.read_text("utf-8", errors="replace")[:4000]
                if re.search(r'^\s*"?(openapi|swagger)"?\s*:', head, re.M):
                    rep.api_spec_files.append(rel)
                    rep.api_kind.append("rest")
                elif path.suffix != ".json" and re.search(r"^apiVersion:.*\n(.|\n)*?^kind:", head, re.M):
                    rep.iac.append(rel)
            elif path.suffix in (".graphql", ".gql"):
                rep.api_spec_files.append(rel)
                rep.api_kind.append("graphql")
            elif path.suffix == ".proto":
                rep.api_spec_files.append(rel)
                rep.api_kind.append("grpc")
            elif name.startswith(".env") and name not in (".env.example", ".env.sample", ".env.template"):
                rep.env_files.append(rel)
        except Exception as exc:  # a malformed manifest must never abort detection
            rep.unparsed.append(f"{rel} ({type(exc).__name__})")

    rep.languages = dict(langs.most_common())
    rep.package_managers = sorted(managers)
    _dedupe_components(rep)
    for c in rep.components:
        kind_label = KNOWN.get(c.name.lower())
        if kind_label and not c.dev:
            kind, label = kind_label
            bucket = {"framework": rep.frameworks, "db": rep.databases, "auth": rep.auth, "api": rep.api_kind}[kind]
            if label not in bucket:
                bucket.append(label)
    rep.api_kind = sorted(set(rep.api_kind))
    rep.docker_images = sorted(set(rep.docker_images))
    rep.exposed_ports = sorted(set(rep.exposed_ports))
    return rep


def _dedupe_components(rep: StackReport) -> None:
    """Keep one entry per (ecosystem, name, version); prefer the lockfile's exact version."""
    seen: dict[tuple[str, str], list[Component]] = {}
    for c in rep.components:
        seen.setdefault((c.ecosystem, c.name.lower()), []).append(c)
    out: list[Component] = []
    for group in seen.values():
        pinned = {c.version: c for c in group if c.version}
        declared = next((c for c in group if c.spec), None)
        if pinned:
            for c in pinned.values():
                if declared:
                    c.direct = c.direct or declared.direct
                    c.spec = c.spec or declared.spec
                    c.dev = c.dev and declared.dev
                out.append(c)
        else:
            out.append(group[0])
    rep.components = sorted(out, key=lambda c: (c.ecosystem, c.name.lower(), c.version or ""))
