from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class StaticResponseWriter(Protocol):
    wfile: Any

    def send_response(self, code: int, message: str | None = None) -> None: ...

    def send_header(self, keyword: str, value: str) -> None: ...

    def end_headers(self) -> None: ...

    def _json(self, status: int, body: dict | list) -> None: ...


def web_root() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    repo_root = package_root.parents[0]
    repo_path = repo_root / "zw-brain-web"
    if repo_path.exists():
        return repo_path
    packaged_path = package_root / "_assets" / "zw-brain-web"
    return packaged_path


def web_public_root(root: Path | None = None) -> Path:
    """Serve Vite production bundle when dist-vite/ exists; else dev index (needs Vite :5173)."""
    candidate = root or web_root()
    built = candidate / "dist-vite"
    if (built / "index.html").is_file():
        return built
    return candidate


def spa_index_path() -> Path:
    """Live path to the SPA shell (index.html) the REST process would serve right now."""
    return web_public_root(web_root()) / "index.html"


def webui_index_readable() -> bool:
    """True when the live SPA shell exists and is a regular file; False on absence or OSError."""
    try:
        return spa_index_path().is_file()
    except OSError:
        return False


def validate_webui_shell(
    *,
    logger: Any,
    is_prod_deploy_mode: Callable[[], bool],
    index_readable: Callable[[], bool] = webui_index_readable,
    index_path: Callable[[], Path] = spa_index_path,
) -> None:
    """Startup gate for the SPA shell.

    Production refuses to boot when the browser shell is missing; non-production
    keeps the API available and logs a loud degraded-surface warning.
    """
    if index_readable():
        return
    logger.error(
        "WebUI shell missing: %s does not exist. The REST API will answer but the browser "
        "gets a blank page. Build the bundle with `npm run build` in zw-brain-web/ (produces "
        "dist-vite/index.html), or run the Vite dev server on :5173 for the dev shell.",
        index_path(),
    )
    if is_prod_deploy_mode():
        raise SystemExit(
            "WebUI shell missing under a prod/production deploy mode — refusing to boot. "
            f"Build the production bundle so {index_path()} exists before deploying."
        )


def serve_file(
    handler: StaticResponseWriter,
    path: Path,
    *,
    enforce_web_root: bool = False,
    web_root_path: Path,
    web_public_root_path: Path,
) -> None:
    try:
        if enforce_web_root:
            try:
                resolved = path.resolve()
                for root in (web_root_path.resolve(), web_public_root_path.resolve()):
                    try:
                        resolved.relative_to(root)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError("outside web roots")
            except (ValueError, FileNotFoundError):
                handler._json(404, {"error": "not_found", "path": str(path)})
                return
        if not path.exists() or not path.is_file():
            handler._json(404, {"error": "not_found", "path": str(path)})
            return
        payload = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        handler.send_response(200)
        handler.send_header("Content-Type", content_type or "application/octet-stream")
        try:
            _ = path.resolve().relative_to(web_root_path.resolve())
        except ValueError:
            pass
        else:
            suf = path.suffix.lower()
            if suf in {".js", ".css"} or path.name.lower() == "index.html":
                handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
    except (BrokenPipeError, ConnectionResetError):
        pass  # client disconnected — nothing to do
