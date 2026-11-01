"""External scanners SecQA orchestrates: detection and installation (`secqa doctor`).

SecQA ships no scanners of its own; the skills call these tools and ingest their output.
Installation always goes through the platform's package manager and is never silent:
`secqa doctor --install` asks before running anything unless `--yes` is passed.
"""
from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tool:
    name: str
    binary: str
    purpose: str
    skill: str
    tier: str  # core = needed for the default /pentest-run + /perf-test; optional = extra coverage
    version_args: tuple[str, ...] = ("--version",)
    # package manager → install command (argv). Tried in the order of PACKAGE_MANAGERS.
    install: dict[str, tuple[str, ...]] = field(default_factory=dict)
    docs: str = ""
    # Python packages are detected by import, not by a binary on PATH, and installed with this interpreter's pip.
    python_module: str | None = None
    post_install: tuple[str, ...] | None = None


TOOLS: tuple[Tool, ...] = (
    Tool("semgrep", "semgrep", "Static analysis of your own code (SQLi, XSS, …)", "pentest-sast", "core",
         install={"brew": ("brew", "install", "semgrep"),
                  "pipx": ("pipx", "install", "semgrep")},
         docs="https://semgrep.dev/docs/getting-started/"),
    Tool("gitleaks", "gitleaks", "Secrets in code and git history", "pentest-secrets", "core",
         version_args=("version",),
         install={"brew": ("brew", "install", "gitleaks"),
                  "scoop": ("scoop", "install", "gitleaks"),
                  "go": ("go", "install", "github.com/zricethezav/gitleaks/v8@latest")},
         docs="https://github.com/gitleaks/gitleaks#installing"),
    Tool("osv-scanner", "osv-scanner", "Dependencies with known CVEs", "pentest-sca", "core",
         install={"brew": ("brew", "install", "osv-scanner"),
                  "scoop": ("scoop", "install", "osv-scanner"),
                  "go": ("go", "install", "github.com/google/osv-scanner/v2/cmd/osv-scanner@latest")},
         docs="https://google.github.io/osv-scanner/installation/"),
    Tool("k6", "k6", "Load / performance tests", "perf-test", "core",
         version_args=("version",),
         install={"brew": ("brew", "install", "k6"),
                  "winget": ("winget", "install", "k6", "--source", "winget"),
                  "go": ("go", "install", "go.k6.io/k6@latest")},
         docs="https://grafana.com/docs/k6/latest/set-up/install-k6/"),
    Tool("playwright", "playwright", "Screenshots as visual evidence (secqa capture)", "pentest-api / pentest-dast",
         "core", python_module="playwright",
         install={"pip": (sys.executable, "-m", "pip", "install", "playwright>=1.48")},
         # Uses an installed Chrome when present; otherwise fetch Playwright's Chromium.
         post_install=(sys.executable, "-m", "playwright", "install", "chromium"),
         docs="https://playwright.dev/python/docs/intro"),
    Tool("trivy", "trivy", "Dependencies, Dockerfiles and IaC misconfiguration", "pentest-sca", "optional",
         install={"brew": ("brew", "install", "trivy"),
                  "scoop": ("scoop", "install", "trivy")},
         docs="https://trivy.dev/latest/getting-started/installation/"),
    Tool("nuclei", "nuclei", "Known-vulnerability templates against a running app", "pentest-dast", "optional",
         version_args=("-version",),
         install={"brew": ("brew", "install", "nuclei"),
                  "go": ("go", "install", "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest")},
         docs="https://docs.projectdiscovery.io/tools/nuclei/install"),
    Tool("zap", "zap-baseline.py", "OWASP ZAP passive/active web scanning", "pentest-dast", "optional",
         install={},  # easiest via Docker: docker run -t zaproxy/zap-stable zap-baseline.py -t <url>
         docs="https://www.zaproxy.org/docs/docker/about/"),
    Tool("jmeter", "jmeter", "Run existing JMeter plans (results are imported)", "perf-test", "optional",
         version_args=("--version",),
         install={"brew": ("brew", "install", "jmeter")},
         docs="https://jmeter.apache.org/download_jmeter.cgi"),
)

# Preferred package managers per OS, best first.
PACKAGE_MANAGERS = {
    "Darwin": ("brew", "pipx", "go"),
    "Linux": ("brew", "pipx", "go"),
    "Windows": ("winget", "scoop", "pipx", "go"),
}


@dataclass
class ToolStatus:
    tool: Tool
    path: str | None
    version: str | None
    install_cmd: tuple[str, ...] | None

    @property
    def installed(self) -> bool:
        return self.path is not None


def available_managers() -> list[str]:
    return [m for m in PACKAGE_MANAGERS.get(platform.system(), ("brew", "pipx", "go")) if shutil.which(m)]


def install_command(tool: Tool, managers: list[str]) -> tuple[str, ...] | None:
    for m in managers:
        if m in tool.install:
            return tool.install[m]
    return None


def _version(binary: str, args: tuple[str, ...]) -> str | None:
    try:
        out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=20, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr).strip().splitlines()
    return text[0][:80] if text else None


def _module_version(module: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(module)
    except PackageNotFoundError:
        return None


def needs_browser_download() -> bool:
    """Playwright can drive an installed Chrome; only download Chromium when there is none."""
    candidates = ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    win = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    from pathlib import Path

    return not (any(shutil.which(c) for c in candidates) or Path(mac).exists() or Path(win).exists())


def check_tools(tools: tuple[Tool, ...] = TOOLS) -> list[ToolStatus]:
    managers = available_managers()
    statuses = []
    for t in tools:
        if t.python_module:
            spec = importlib.util.find_spec(t.python_module)
            path = spec.origin if spec else None
            version = _module_version(t.python_module) if spec else None
            cmd = None if spec else t.install.get("pip")
        else:
            path = shutil.which(t.binary)
            version = _version(path, t.version_args) if path else None
            cmd = None if path else install_command(t, managers)
        statuses.append(ToolStatus(tool=t, path=path, version=version, install_cmd=cmd))
    return statuses


def run_install(cmd: tuple[str, ...]) -> bool:
    return subprocess.run(list(cmd), check=False).returncode == 0  # noqa: S603


def post_install_steps(tool: Tool) -> list[tuple[str, ...]]:
    if tool.post_install and (tool.name != "playwright" or needs_browser_download()):
        return [tool.post_install]
    return []
