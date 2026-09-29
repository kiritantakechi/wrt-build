"""The app Pod of the services tests (r4s-services D4, D10), which stands in for qBittorrent.

Its declaration lies on the data disk, as an administrator would write one: a
Kubernetes Pod of the test app image whose uhttpd serves a directory of the data
disk, and an options file that gives it a fixed address for a port forward.
wrt-containers starts it once the data disk is mounted.
"""

import shlex
from typing import TYPE_CHECKING

from wrt_tests.poll import until
from wrt_tests.storage import MOUNT

if TYPE_CHECKING:
    from wrt_tests.router import Router

POD = "web"
CONTAINER = f"{POD}-httpd"
ADDRESS = "10.88.0.10"
PODS = f"{MOUNT}/containers/pods"
WWW = f"{MOUNT}/containers/www"
START_TIMEOUT = 180


def declaration(image: str) -> str:
    """Return the Pod's declaration, as podman kube play reads it."""
    return f"""\
apiVersion: v1
kind: Pod
metadata:
  name: {POD}
spec:
  containers:
    - name: httpd
      image: {image}
      command: [uhttpd, -f, -p, "0.0.0.0:80", -h, /www]
      volumeMounts:
        - name: www
          mountPath: /www
  volumes:
    - name: www
      hostPath:
        path: {WWW}
        type: DirectoryOrCreate
"""


def declare(router: Router, image: str) -> None:
    """Write the Pod's declaration and its page to the data disk, and start the Pod."""
    router.run(
        f"mkdir -p {PODS} {WWW} && echo {POD} >{WWW}/index.html"
        f" && printf %s {shlex.quote(declaration(image))} >{PODS}/{POD}.yaml"
        f" && echo --ip={ADDRESS} >{PODS}/{POD}.options"
        " && /etc/init.d/wrt-containers restart"
    )


def running(router: Router) -> str | None:
    """Return the app container's ID while it runs."""
    state = router.run(
        f"podman container inspect --format '{{{{.State.Running}}}} {{{{.Id}}}}' {CONTAINER}"
        " 2>/dev/null || true"
    ).split()
    return state[1] if state[:1] == ["true"] else None


def wait_running(router: Router) -> str:
    """Wait until the app container runs; return its ID (or fail with wrt-containers' log)."""
    try:
        return until(lambda: running(router), timeout=START_TIMEOUT, what=f"{CONTAINER} running")
    except TimeoutError as error:
        error.add_note(router.run("logread -e wrt-containers | tail -n 20"))
        raise
