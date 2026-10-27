"""Black-box acceptance-test fixtures for XGeneratePosts v3."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

MODEL_TEXT = """\
===URL===
https://example.test/generated-story
===TITLE===
A security engineering story
===SOURCE===
https://example.test/feed.xml
===TWEET===
A useful security engineering development worth watching.
===LINKEDIN===
A useful security engineering development, with context for practitioners.
===WHY===
This story has practical implications for security teams.
===END===
"""


class StubState:
    """Mutable state shared with a stub server's request handler."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.status = 200
        self.body = json.dumps({"choices": [{"message": {"content": MODEL_TEXT}}]}).encode()
        self.headers: dict[str, str] = {}
        self.delay = 0.0
        self.feed_responses: dict[str, tuple[int, bytes, dict[str, str]]] = {}
        self.plain_http_feed = b""

    def record(self, request: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append(request)

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.requests)


class ModelStub:
    """Local HTTP implementation of the documented OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        self.state = StubState()
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                """Plain-HTTP feed target for the R18 downgrade test."""
                state.record({"method": "GET", "path": self.path})
                payload = state.plain_http_feed
                self.send_response(200)
                self.send_header("Content-Type", "application/rss+xml")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(payload)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length)
                try:
                    body: Any = json.loads(raw_body)
                except json.JSONDecodeError:
                    body = raw_body.decode("utf-8", errors="replace")

                state.record(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": body,
                    }
                )

                if state.delay:
                    time.sleep(state.delay)

                payload = state.body
                status = state.status
                headers = dict(state.headers)

                if status == 200:
                    headers.setdefault("Content-Type", "application/json")

                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()

                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(payload)

            def log_message(self, format_string: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.allow_reuse_address = True
        self.ready = threading.Event()
        self.thread = threading.Thread(
            target=self._serve,
            name="acceptance-model-stub",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def _serve(self) -> None:
        self.ready.set()
        self.server.serve_forever(poll_interval=0.05)

    def start(self) -> ModelStub:
        self.thread.start()
        if not self.ready.wait(timeout=5):
            raise RuntimeError("Model stub failed to signal readiness")
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FeedStub:
    """Local HTTPS server for RSS/Atom documents and redirect/error fixtures."""

    def __init__(self, certificate: Path, private_key: Path) -> None:
        self.state = StubState()
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                state.record({"method": "GET", "path": self.path})
                status, payload, headers = state.feed_responses.get(
                    self.path,
                    (
                        404,
                        b"Not found",
                        {"Content-Type": "text/plain"},
                    ),
                )
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()

                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(payload)

            def log_message(self, format_string: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.allow_reuse_address = True

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate), str(private_key))
        self.server.socket = context.wrap_socket(
            self.server.socket,
            server_side=True,
        )

        self.ready = threading.Event()
        self.thread = threading.Thread(
            target=self._serve,
            name="acceptance-feed-stub",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"https://{host}:{port}"

    def url(self, path: str = "/feed.xml") -> str:
        return f"{self.base_url}{path}"

    def set_response(
        self,
        path: str,
        body: str | bytes,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        payload = body.encode() if isinstance(body, str) else body
        content_headers = dict(headers or {"Content-Type": "application/rss+xml"})
        self.state.feed_responses[path] = (
            status,
            payload,
            content_headers,
        )

    def redirect_to_http(self, path: str, target_url: str) -> None:
        self.set_response(
            path,
            b"",
            status=302,
            headers={"Location": target_url},
        )

    def _serve(self) -> None:
        self.ready.set()
        self.server.serve_forever(poll_interval=0.05)

    def start(self) -> FeedStub:
        self.thread.start()
        if not self.ready.wait(timeout=5):
            raise RuntimeError("Feed stub failed to signal readiness")
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def model_text() -> str:
    """Return a valid canned model response in the documented delimited format."""
    return MODEL_TEXT


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Return a fresh data directory for a test."""
    path = tmp_path / "data"
    path.mkdir()
    return path


@pytest.fixture
def profile_writer(data_dir: Path) -> Callable[..., Path]:
    """Write an author profile using the documented Markdown structure."""

    def write_profile(
        *,
        feeds: list[str] | None = None,
        include_feeds_section: bool = True,
        extra_sections: str = "",
    ) -> Path:
        path = data_dir / "author_profile.md"
        content = (
            "# Author profile\n\n"
            "## Beat\nSecurity engineering.\n\n"
            "## Voice\nClear, direct, practical.\n"
        )
        content += extra_sections

        if include_feeds_section:
            content += "\n## Feeds\n"
            content += "".join(f"- {url}\n" for url in (feeds or []))

        path.write_text(content, encoding="utf-8")
        return path

    return write_profile


@pytest.fixture
def env_builder(
    tmp_path: Path,
    data_dir: Path,
) -> Callable[..., dict[str, str]]:
    """Build a clean child environment without inheriting caller variables."""

    def build(**overrides: str) -> dict[str, str]:
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "AI_POST_DATA_DIR": str(data_dir),
            "AI_POST_ENV_FILE": str(tmp_path / "env-file-does-not-exist"),
        }
        env.update(overrides)
        return env

    return build


@pytest.fixture(scope="session")
def tls_certificate(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    """Generate a self-signed test certificate with an IP subjectAltName."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.fail(
            "HTTPS acceptance tests require openssl on PATH; "
            "install openssl before running the acceptance suite.",
            pytrace=False,
        )

    directory = tmp_path_factory.mktemp("acceptance-tls")
    certificate = directory / "cert.pem"
    private_key = directory / "key.pem"

    result = subprocess.run(  # noqa: S603 - fixed argv list, no shell
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
            "-days",
            "2",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail(
            f"openssl failed to generate the test certificate: {result.stderr.strip()}",
            pytrace=False,
        )

    return certificate, private_key


@pytest.fixture
def model_stub() -> Iterator[ModelStub]:
    """Start a local model stub and stop it after the test."""
    stub = ModelStub().start()
    try:
        yield stub
    finally:
        stub.close()


@pytest.fixture
def feed_stub(
    tls_certificate: tuple[Path, Path],
) -> Iterator[FeedStub]:
    """Start a local HTTPS feed stub and stop it after the test."""
    certificate, private_key = tls_certificate
    stub = FeedStub(certificate, private_key).start()
    try:
        yield stub
    finally:
        stub.close()


@pytest.fixture
def rss_feed() -> Callable[[list[dict[str, str]]], str]:
    """Build an RSS 2.0 document from title, link, date, and summary fields."""

    def build(entries: list[dict[str, str]]) -> str:
        items = []
        for entry in entries:
            items.append(
                "<item>"
                f"<title>{entry['title']}</title>"
                f"<link>{entry['link']}</link>"
                f"<pubDate>{entry['date']}</pubDate>"
                f"<description>{entry['summary']}</description>"
                "</item>"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel>'
            "<title>Acceptance feed</title>" + "".join(items) + "</channel></rss>"
        )

    return build


@pytest.fixture
def atom_feed() -> Callable[[list[dict[str, str]]], str]:
    """Build an Atom document from title, link, date, and summary fields."""

    def build(entries: list[dict[str, str]]) -> str:
        items = []
        for entry in entries:
            items.append(
                "<entry>"
                f"<title>{entry['title']}</title>"
                f'<link href="{entry["link"]}" />'
                f"<updated>{parsedate_to_datetime(entry['date']).isoformat()}</updated>"
                f"<summary>{entry['summary']}</summary>"
                "</entry>"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>Acceptance Atom feed</title>" + "".join(items) + "</feed>"
        )

    return build


_TOPIC_FLAGS = ("--topic", "--random-topic", "--list-topics", "--history")


def _with_default_topic(args: tuple[str, ...]) -> tuple[str, ...]:
    """Section 11 precondition: without a terminal, a drafting run needs a topic."""
    if any(flag in args for flag in _TOPIC_FLAGS) or "--no-default-topic" in args:
        return tuple(a for a in args if a != "--no-default-topic")
    return (*args, "--topic", "Acceptance testing")


@pytest.fixture
def run_cli(
    data_dir: Path,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run the CLI as a subprocess and record new run.log lines on its result."""

    def run(
        *args: str,
        env: Mapping[str, str],
        timeout: float = 30,
        python_flags: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        if timeout > 60:
            raise ValueError("Acceptance-test subprocess timeout must not exceed 60 seconds")

        log_path = data_dir / "run.log"
        before = len(log_path.read_text(encoding="utf-8").splitlines()) if log_path.exists() else 0

        result = subprocess.run(  # noqa: S603 - fixed argv list, no shell
            [sys.executable, *python_flags, "daily_post.py", *_with_default_topic(args)],
            cwd=REPO_ROOT,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        after = len(log_path.read_text(encoding="utf-8").splitlines()) if log_path.exists() else 0
        result.log_lines_added = after - before
        return result

    return run


@pytest.fixture
def successful_rss_environment(
    env_builder: Callable[..., dict[str, str]],
    profile_writer: Callable[..., Path],
    feed_stub: FeedStub,
    tls_certificate: tuple[Path, Path],
    model_stub: ModelStub,
    rss_feed: Callable[[list[dict[str, str]]], str],
) -> Callable[..., dict[str, str]]:
    """Configure an OpenAI-compatible run with a working HTTPS feed."""

    def build(
        *,
        entries: list[dict[str, str]] | None = None,
        feed_paths: list[str] | None = None,
        **overrides: str,
    ) -> dict[str, str]:
        selected_entries = entries or [
            {
                "title": "Working HTTPS feed entry",
                "link": "https://example.test/working-feed-entry",
                "date": "Mon, 26 Oct 2026 09:00:00 +0000",
                "summary": "A working HTTPS feed summary.",
            }
        ]
        paths = feed_paths or ["/feed.xml"]

        for path in paths:
            feed_stub.set_response(path, rss_feed(selected_entries))

        profile_writer(feeds=[feed_stub.url(path) for path in paths])
        certificate, _ = tls_certificate

        env = {
            "OPENAI_COMPAT_BASE_URL": model_stub.base_url,
            "OPENAI_COMPAT_MODEL": "test-model",
            "SSL_CERT_FILE": str(certificate),
            **overrides,
        }
        return env_builder(**env)

    return build
