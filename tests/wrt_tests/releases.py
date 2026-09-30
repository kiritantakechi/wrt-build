"""A stand-in for GitHub's Releases API on the emulated internet (r4s-release-pipeline D7).

``serve`` answers what wrt-sync asks, over HTTPS with the test CA's certificate:
a repository's newest stable release (``/repos/<owner>/<repo>/releases/latest``),
its releases newest first (``/repos/<owner>/<repo>/releases``), and each asset at
its ``browser_download_url`` (``/<owner>/<repo>/releases/download/<tag>/<asset>``,
as on GitHub). A repository's releases are directories under
``<root>/<owner>/<repo>``, each an assembled release (release-publish.sh) that
``publish`` put there. A release with a ``.cut`` file sends only that many bytes
of each asset, then drops the connection: a sync interrupted halfway. Every
download is recorded in the release's ``.downloads``, which ``downloads`` reads.
"""

import argparse
import json
import os
import shutil
import ssl
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

PORT = 443
CHUNK = 1 << 16
DOWNLOADS = ".downloads"
# Where the sandbox's stand-in serves from, in the sandbox's directory.
ROOT = Path("inet") / "releases"


def publish(
    root: Path,
    repository: str,
    release: Path,
    *,
    tag: str | None = None,
    prerelease: bool | None = None,
) -> str:
    """Publish an assembled release in ``repository`` (owner/repo), the newest now; return its tag.

    ``tag`` and ``prerelease`` publish it as another release: one assembled
    build stands for several. Its files are linked, not copied (none changes).
    """
    info = json.loads((release / "release.json").read_text())
    info["tag"] = tag or info["tag"]
    info["prerelease"] = info["prerelease"] if prerelease is None else prerelease
    info["published"] = time.time()
    target = root / repository / info["tag"]
    shutil.copytree(release, target, copy_function=os.link)
    (target / "release.json").unlink()
    (target / "release.json").write_text(json.dumps(info))
    return str(info["tag"])


def cut(root: Path, repository: str, tag: str, size: int | None) -> None:
    """Have downloads of ``tag`` stop after ``size`` bytes, or run whole again (None)."""
    marker = root / repository / tag / ".cut"
    if size is None:
        marker.unlink(missing_ok=True)
    else:
        marker.write_text(str(size))


def downloads(root: Path, repository: str, tag: str) -> list[str]:
    """Return the assets of ``tag`` downloaded so far, in order, each as often as it was."""
    record = root / repository / tag / DOWNLOADS
    return record.read_text().splitlines() if record.is_file() else []


def _releases(directory: Path, base: str) -> list[dict[str, Any]]:
    """Return a repository's releases in the API's form, newest first."""
    found = []
    for release in directory.iterdir() if directory.is_dir() else ():
        manifest = release / "release.json"
        if not manifest.is_file():
            continue
        info = json.loads(manifest.read_text())
        found.append(
            {
                "tag_name": info["tag"],
                "name": info["tag"],
                "prerelease": info["prerelease"],
                "draft": False,
                "body": info["notes"],
                "published": info.get("published", 0),
                "assets": [
                    {
                        "name": asset,
                        "size": (release / asset).stat().st_size,
                        "browser_download_url": f"{base}/download/{info['tag']}/{asset}",
                    }
                    for asset in info["assets"]
                    if asset != "release.json"
                ],
            }
        )
    return sorted(found, key=lambda release: -release["published"])


class _Handler(BaseHTTPRequestHandler):
    root: Path
    base: str

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of access logs."""

    def _json(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _listed(self, owner: str, name: str) -> list[dict[str, Any]]:
        return _releases(self.root / owner / name, f"{self.base}/{owner}/{name}/releases")

    def do_GET(self) -> None:
        """Answer the API's requests and the downloads."""
        path = self.path.split("?", 1)[0].strip("/").split("/")
        match path:
            case ["repos", owner, name, "releases"]:
                self._json(self._listed(owner, name))
            case ["repos", owner, name, "releases", "latest"]:
                stable = [r for r in self._listed(owner, name) if not r["prerelease"]]
                if stable:
                    self._json(stable[0])
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            case [owner, name, "releases", "download", tag, asset] if (
                self.root / owner / name / tag / asset
            ).is_file():
                release = self.root / owner / name / tag
                self._download(release / asset, release / ".cut")
            case _:
                self.send_error(HTTPStatus.NOT_FOUND)

    def _download(self, file: Path, cut_file: Path) -> None:
        with (file.parent / DOWNLOADS).open("a") as record:
            record.write(f"{file.name}\n")
        size = file.stat().st_size
        limit = int(cut_file.read_text()) if cut_file.is_file() else size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with file.open("rb") as source:
            remaining = min(size, limit)
            while remaining:
                chunk = source.read(min(CHUNK, remaining))
                self.wfile.write(chunk)
                remaining -= len(chunk)
        if limit < size:
            self.close_connection = True
            self.connection.close()


def serve(root: Path, address: str, name: str, certificate: Path, key: Path) -> None:
    """Serve the releases under ``root`` on ``address`` as https://``name``."""
    root.mkdir(parents=True, exist_ok=True)
    handler = type("Handler", (_Handler,), {"root": root, "base": f"https://{name}"})
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certificate, key)
    with ThreadingHTTPServer((address, PORT), handler) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.serve_forever()


def main() -> None:
    """Command line: serve the releases of a directory."""
    parser = argparse.ArgumentParser(prog="releases", description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--address", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    serve(args.root, args.address, args.name, args.certificate, args.key)


if __name__ == "__main__":
    main()
