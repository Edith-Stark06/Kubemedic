# Third-Party Notices

KubeMedic uses the following open-source packages. Each is used under its
stated license; no modification has been made to any third-party code.

## Runtime dependencies

| Package | Version range | License | Source |
|---|---|---|---|
| `kubernetes` | >=32,<37 | Apache 2.0 | https://github.com/kubernetes-client/python |
| `pydantic` | >=2.7,<3 | MIT | https://github.com/pydantic/pydantic |
| `mcp` | >=1.20,<2 | MIT | https://github.com/modelcontextprotocol/python-sdk |
| `fastapi` | >=0.110,<1 | MIT | https://github.com/tiangolo/fastapi |
| `uvicorn` | >=0.27,<1 | BSD 3-Clause | https://github.com/encode/uvicorn |
| `jinja2` | >=3.1,<4 | BSD 3-Clause | https://github.com/pallets/jinja |
| `httpx` | >=0.27 | BSD 3-Clause | https://github.com/encode/httpx |
| `python-dotenv` | >=1.0,<2 | BSD 3-Clause | https://github.com/theskumar/python-dotenv |

## Development dependencies

| Package | Version range | License | Source |
|---|---|---|---|
| `pytest` | >=8,<10 | MIT | https://github.com/pytest-dev/pytest |
| `pytest-asyncio` | >=0.23 | Apache 2.0 | https://github.com/pytest-dev/pytest-asyncio |

## IBM Bob

IBM Bob (the IDE and the reasoning API used in this project) is a product of
IBM. Its license and terms of service govern the usage described in
`submission/HOW_WE_USED_IBM_BOB.md`.

## Kubernetes

The demo workload targets the `opspilot` Kubernetes namespace. Kubernetes is
copyright the Cloud Native Computing Foundation, licensed Apache 2.0.

---

Licenses are reproduced in the respective package distributions. No third-party
code is included in this repository's tracked source; all dependencies are
fetched at install time via `pip`.
