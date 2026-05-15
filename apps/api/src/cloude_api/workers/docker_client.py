"""aiodocker client lifecycle helpers.

One Docker client per worker process. The worker's on_startup hook constructs
one and stashes it in arq's ctx; on_shutdown closes it. Spawn/lifecycle helpers
take the client as an explicit parameter — no module-level globals.
"""

from __future__ import annotations

import aiodocker


async def make_docker_client() -> aiodocker.Docker:
    """Construct an aiodocker client using DOCKER_HOST or the default unix socket."""
    return aiodocker.Docker()


async def close_docker_client(client: aiodocker.Docker) -> None:
    """Close the underlying aiohttp connector. Safe to call twice."""
    await client.close()
