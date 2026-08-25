"""Native Dagger checks for Assay's existing repository commands."""

from typing import Annotated, Final

import dagger
from dagger import DefaultPath, Ignore, check, dag, field, function, object_type

PYTHON_IMAGE: Final = (
    "python:3.13.14-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6"
)
NODE_URL: Final = "https://nodejs.org/dist/v22.13.0/node-v22.13.0-linux-x64.tar.xz"
NODE_SHA256: Final = "3ff0d57063c33313d73d0bdcebc4c778ad6be948234584694a042c6fe57164f6"
ACTIONLINT_URL: Final = (
    "https://github.com/rhysd/actionlint/releases/download/v1.7.12/"
    "actionlint_1.7.12_linux_amd64.tar.gz"
)
ACTIONLINT_SHA256: Final = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
PNPM_VERSION: Final = "11.5.0"
SOURCE_INCLUDE: Final = [
    ".dagger/src/**",
    ".env.example",
    ".github/**",
    ".gitleaksignore",
    ".gitignore",
    "CHANGELOG.md",
    "CLAUDE.md",
    "LICENSE",
    "QUICKSTART.md",
    "README.md",
    "SECURITY.md",
    "benchmarks/**",
    "dagger.json",
    "docs/**",
    "examples/**",
    "pyproject.toml",
    "scripts/**",
    "src/**",
    "testdata/**",
    "tests/**",
    "ts/**",
    "uv.lock",
]
SOURCE_EXCLUDES: Final = [
    ".git",
    ".venv",
    "**/.venv",
    "**/__pycache__",
    "**/node_modules",
    "**/dist",
    ".env",
    "**/.env",
    "*.key",
    "**/*.key",
    "*.pem",
    "**/*.pem",
]


@object_type
class Assay:
    """Run Assay's canonical checks and build verified package artifacts."""

    source: Annotated[dagger.Directory, DefaultPath("/"), Ignore(SOURCE_EXCLUDES)] = field()

    @function
    @check
    def python(self) -> dagger.Container:
        """Run the complete Python quality gate."""
        return self._repository().with_exec(["uv", "run", "poe", "gate"])

    @function
    @check
    def typescript(self) -> dagger.Container:
        """Run the complete TypeScript quality gate."""
        return self._repository().with_exec(["pnpm", "--dir", "ts", "gate"])

    @function
    @check
    def parity(self) -> dagger.Container:
        """Replay every shared Python and TypeScript scoring vector."""
        return (
            self._repository()
            .with_exec(
                [
                    "uv",
                    "run",
                    "pytest",
                    "tests/test_consumer_conformance.py",
                    "tests/test_metric_vectors.py",
                    "-q",
                ]
            )
            .with_exec(
                [
                    "pnpm",
                    "--dir",
                    "ts",
                    "exec",
                    "vitest",
                    "run",
                    "src/compositionVectors.test.ts",
                    "src/metricVectors.test.ts",
                ]
            )
        )

    @function
    @check
    def mutations(self) -> dagger.Container:
        """Prove the retained mutation guards fail when their wiring breaks."""
        return self._repository().with_exec(["uv", "run", "poe", "mutants"])

    @function
    @check
    def example(self) -> dagger.Container:
        """Run the installed-artifact Northstar example."""
        return (
            self._repository()
            .with_exec(
                ["uv", "run", "pytest", "tests/test_example.py", "tests/test_measurement.py", "-q"]
            )
            .with_exec(["bash", "examples/run_composite.sh"])
        )

    @function
    @check
    def benchmarks(self) -> dagger.Container:
        """Enforce the frozen Python and TypeScript resource budgets."""
        return (
            self._repository()
            .with_exec(["uv", "run", "poe", "benchmark"])
            .with_exec(["pnpm", "--dir", "ts", "benchmark"])
        )

    @function
    @check
    def security(self) -> dagger.Container:
        """Audit locked dependencies and workflow policy without credentials."""
        return (
            self._with_actionlint(self._repository())
            .with_exec(["uv", "run", "poe", "audit"])
            .with_exec(["uv", "run", "poe", "workflow-lint"])
            .with_exec(["uv", "run", "poe", "workflow-security"])
        )

    @function
    def artifacts(self) -> dagger.Directory:
        """Build and clean-install the reviewed Python and npm artifacts."""
        return self._artifact_container().directory("/release")

    @function
    def preview(self) -> dagger.Service:
        """Serve verified artifacts for local consumer inspection."""
        return (
            dag.container()
            .from_(PYTHON_IMAGE)
            .with_directory("/srv", self.artifacts())
            .with_workdir("/srv")
            .with_exposed_port(8080)
            .as_service(args=["python", "-m", "http.server", "8080"])
        )

    @function
    @check
    def distribution(self) -> dagger.Container:
        """Fetch the verified checksum manifest through the artifact service."""
        script = (
            "import urllib.request; "
            "urllib.request.urlopen('http://packages:8080/SHA256SUMS', timeout=30).read()"
        )
        return (
            dag.container()
            .from_(PYTHON_IMAGE)
            .with_service_binding("packages", self.preview())
            .with_exec(["python", "-c", script])
        )

    @function
    @check
    def publish_ready(self) -> dagger.Container:
        """Build reviewed bytes and stage the pinned npm publisher without publishing."""
        return self._artifact_container().with_exec(
            ["bash", "scripts/stage_npm_publisher.sh", "/publish-tools"]
        )

    def _artifact_container(self) -> dagger.Container:
        return self._repository().with_exec(
            ["bash", "scripts/build_release_artifacts.sh", "/release"]
        )

    def _repository(self) -> dagger.Container:
        source = self.source.filter(include=SOURCE_INCLUDE)
        return (
            self._toolchain()
            .with_env_variable("CI", "true")
            .with_directory("/src", source)
            .with_workdir("/src")
            .with_exec(["git", "init", "-q"])
            .with_exec(["git", "config", "user.email", "dagger@invalid"])
            .with_exec(["git", "config", "user.name", "Dagger"])
            .with_exec(["git", "add", "."])
            .with_env_variable("GIT_AUTHOR_DATE", "2000-01-01T00:00:00Z")
            .with_env_variable("GIT_COMMITTER_DATE", "2000-01-01T00:00:00Z")
            .with_exec(["git", "commit", "-qm", "workspace"])
            .with_exec(["uv", "sync", "--frozen", "--all-groups", "--all-extras"])
            .with_exec(["pnpm", "--dir", "ts", "install", "--frozen-lockfile", "--ignore-scripts"])
        )

    def _toolchain(self) -> dagger.Container:
        node = dag.http(NODE_URL, checksum=f"sha256:{NODE_SHA256}")
        return (
            self._base()
            .with_file("/opt/node.tar.xz", node)
            .with_exec(
                ["tar", "-xJf", "/opt/node.tar.xz", "-C", "/usr/local", "--strip-components=1"]
            )
            .with_exec(["npm", "install", "--global", f"pnpm@{PNPM_VERSION}"])
        )

    def _base(self) -> dagger.Container:
        return (
            dag.container(platform=dagger.Platform("linux/amd64"))
            .from_(PYTHON_IMAGE)
            .with_exec(["apt-get", "update"])
            .with_exec(
                [
                    "apt-get",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    "ca-certificates",
                    "git",
                    "jq",
                    "xz-utils",
                ]
            )
            .with_exec(["ln", "-s", "/usr/local/bin/python3", "/usr/bin/python3"])
            .with_mounted_cache("/root/.cache/uv", dag.cache_volume("assay-uv"))
            .with_mounted_cache("/root/.local/share/pnpm/store", dag.cache_volume("assay-pnpm"))
            .with_exec(["python", "-m", "pip", "install", "uv==0.11.32"])
        )

    def _with_actionlint(self, container: dagger.Container) -> dagger.Container:
        archive = dag.http(ACTIONLINT_URL, checksum=f"sha256:{ACTIONLINT_SHA256}")
        return container.with_file("/opt/actionlint.tar.gz", archive).with_exec(
            ["tar", "-xzf", "/opt/actionlint.tar.gz", "-C", "/usr/local/bin", "actionlint"]
        )
