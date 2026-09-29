"""Isolated Docker gateway checks. No real model calls or existing data volumes.

Build images first, or pass --api-image / --web-image for existing reviewed builds.
Only randomly named test containers, network and volume are removed on completion.
"""

import argparse
import base64
import http.client
import json
import secrets
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from configure import CADDY, ROOT


def docker(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["docker", *args],
        input=input_text.encode() if input_text is not None else None,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", default="haru-estate-cloud-api:smoke")
    parser.add_argument("--web-image", default="haru-estate-cloud-web:smoke")
    args = parser.parse_args()
    prefix = "haru-cloud-smoke-" + uuid4().hex[:12]
    containers: list[str] = []
    network = prefix + "-network"
    volume = prefix + "-data"
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    checks = 0

    def check(condition: bool, label: str) -> None:
        nonlocal checks
        if not condition:
            raise AssertionError(label)
        checks += 1
        print("PASS " + label, flush=True)

    def run(name: str, *options: str) -> None:
        containers.append(name)
        docker("run", "-d", "--name", name, "--network", network, *options)

    def port(name: str, container_port: str) -> str:
        return docker("port", name, container_port).splitlines()[0].rsplit(":", 1)[1]

    with tempfile.TemporaryDirectory(prefix=prefix, dir=artifacts) as directory:
        directory_path = Path(directory)
        password = secrets.token_urlsafe(24)
        hashed = docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            CADDY,
            "caddy",
            "hash-password",
            "--bcrypt-cost",
            "4",
            input_text=password + "\n",
        )
        auth = directory_path / "auth.caddy"
        auth.write_text("demo " + hashed + "\n", encoding="utf-8")
        caddy = directory_path / "Caddyfile"
        caddy.write_text(
            (ROOT / "deploy/cloud/Caddyfile")
            .read_text(encoding="utf-8")
            .replace(
                "https://{$HARU_DOMAIN} {", "https://{$HARU_DOMAIN} {\n    tls internal"
            ),
            encoding="utf-8",
        )
        api, web, gateway = [prefix + suffix for suffix in ("-api", "-web", "-gateway")]
        try:
            docker("network", "create", network)
            docker("volume", "create", volume)
            run(
                api,
                "--network-alias",
                "api",
                "-v",
                volume + ":/app/data",
                args.api_image,
            )
            run(
                web,
                "--network-alias",
                "web",
                "-e",
                "HARU_DOMAIN=localhost",
                "-e",
                "HARU_DEMO_AI=off",
                "-p",
                "127.0.0.1::8081",
                "-v",
                str(ROOT / "deploy/cloud/nginx.conf.template")
                + ":/etc/nginx/templates/default.conf.template:ro",
                args.web_image,
            )
            run(
                gateway,
                "-e",
                "HARU_DOMAIN=localhost",
                "-p",
                "127.0.0.1::443",
                "-p",
                "127.0.0.1::80",
                "-v",
                str(caddy) + ":/etc/caddy/Caddyfile:ro",
                "-v",
                str(auth) + ":/run/secrets/cloud-auth.caddy:ro",
                CADDY,
            )
            admin_url = "http://127.0.0.1:" + port(web, "8081")
            local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(60):
                try:
                    with local_opener.open(
                        admin_url + "/api/v1/health", timeout=2
                    ) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.HTTPError):
                    time.sleep(1)
            else:
                raise RuntimeError("Isolated API failed readiness")
            ca = docker(
                "exec", gateway, "cat", "/data/caddy/pki/authorities/local/root.crt"
            )
            context = ssl.create_default_context(cadata=ca)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=context),
            )
            redirect = http.client.HTTPConnection(
                "127.0.0.1", int(port(gateway, "80")), timeout=10
            )
            redirect.request("GET", "/", headers={"Host": "localhost"})
            response = redirect.getresponse()
            check(
                response.status == 308
                and response.getheader("Location", "").startswith("https://localhost"),
                "HTTP redirects to HTTPS without serving data",
            )
            response.read()
            redirect.close()
            url = "https://localhost:" + port(gateway, "443")
            authorization = (
                "Basic " + base64.b64encode(("demo:" + password).encode()).decode()
            )

            def request(
                path: str,
                method: str = "GET",
                *,
                authenticated: bool = True,
                extra: dict[str, str] | None = None,
                base: str | None = None,
            ) -> tuple[int, bytes]:
                headers = {"Authorization": authorization} if authenticated else {}
                headers.update(extra or {})
                body = b"{}" if method in {"POST", "PUT", "DELETE"} else None
                if body is not None:
                    headers["Content-Type"] = "application/json"
                req = urllib.request.Request(
                    (base or url) + path, data=body, method=method, headers=headers
                )
                try:
                    with opener.open(req, timeout=10) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            for path in [
                "/",
                "/brand/logo.png",
                "/api/v1/health",
                "/api/v1/projects",
                "/api/v1/runs",
                "/api/v1/agent/tasks",
                "/docs",
                "/openapi.json",
            ]:
                check(
                    request(path, authenticated=False)[0] == 401,
                    "anonymous blocked " + path,
                )
            check(
                request("/", extra={"Authorization": "Basic ZGVtbzp3cm9uZw=="})[0]
                == 401,
                "wrong password blocked",
            )
            check(request("/")[0] == 200, "authenticated page and trusted test TLS")
            check(request("/api/v1/health")[0] == 200, "authenticated API")
            before = request("/api/v1/projects")[1]
            check(
                request("/api/v1/projects", "POST", authenticated=False)[0] == 401,
                "anonymous mutation blocked",
            )
            for method in ["GET", "PUT", "DELETE"]:
                for path in [
                    "/api/v1/model-config",
                    "/api/v1/model-config/",
                    "/api/v1/%6dodel-config",
                ]:
                    check(
                        request(
                            path,
                            method,
                            extra={"Origin": "https://localhost", "X-Haru-Config": "1"},
                        )[0]
                        == 403,
                        "public configuration denied " + method + " " + path,
                    )
            for origin in [None, "https://untrusted.example", "null"]:
                check(
                    request(
                        "/api/v1/projects",
                        "POST",
                        extra={"Origin": origin} if origin else {},
                    )[0]
                    == 403,
                    "cross-site or absent Origin rejected",
                )
            for path in [
                "/api/v1/agent/tasks",
                "/api/v1/agent/tasks/test/reply",
                "/api/v1/agent/tasks/test/resume",
            ]:
                check(
                    request(path, "POST", extra={"Origin": "https://localhost"})[0]
                    == 403,
                    "AI switch blocks " + path,
                )
            check(
                request("/api/v1/projects")[1] == before,
                "rejected writes preserve data",
            )
            status, body = request(
                "/api/v1/model-config",
                authenticated=False,
                extra={"X-Haru-Config": "1"},
                base=admin_url,
            )
            check(
                status == 200 and json.loads(body)["configured"] is False,
                "loopback administrator configuration available without model key",
            )
            # Enable only in this isolated web container; no model key is configured.
            docker(
                "exec",
                web,
                "sh",
                "-c",
                "sed -i 's/:off/:on/g' /etc/nginx/conf.d/default.conf && nginx -s reload",
            )
            time.sleep(1)
            statuses = [
                request(
                    "/api/v1/agent/tasks", "POST", extra={"Origin": "https://localhost"}
                )[0]
                for _ in range(5)
            ]
            check(
                422 in statuses and 429 in statuses,
                "enabled assistant reaches API and has its own rate limit",
            )
            # Reset only the global write bucket so each limiter is tested independently.
            docker(
                "exec",
                web,
                "sh",
                "-c",
                "sed -i 's/demo_writes/demo_writes_second/g' /etc/nginx/conf.d/default.conf "
                "&& nginx -s reload",
            )
            time.sleep(1)
            # Invalid bodies cannot create runs; they still exercise edge rate limits.
            statuses = [
                request("/api/v1/runs", "POST", extra={"Origin": "https://localhost"})[
                    0
                ]
                for _ in range(10)
            ]
            check(
                422 in statuses and 429 in statuses,
                "valid Origin reaches API; burst writes rate-limited",
            )
            check(
                request("/api/v1/projects")[0] == 200, "reads unaffected by write limit"
            )

            check(not docker("port", api), "API has no host port")
            check(
                docker("port", web).startswith("8081/tcp -> 127.0.0.1:"),
                "administrator binds loopback",
            )
            replacement = secrets.token_urlsafe(24)
            replacement_hash = docker(
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                CADDY,
                "caddy",
                "hash-password",
                "--bcrypt-cost",
                "4",
                input_text=replacement + "\n",
            )
            auth.write_text("demo " + replacement_hash + "\n", encoding="utf-8")
            docker("restart", gateway)
            url = "https://localhost:" + port(gateway, "443")
            time.sleep(2)
            check(request("/")[0] == 401, "rotated password rejects old credentials")
            authorization = (
                "Basic " + base64.b64encode(("demo:" + replacement).encode()).decode()
            )
            check(request("/")[0] == 200, "rotated password accepts new credentials")
            auth.write_text("", encoding="utf-8")
            docker("restart", gateway)
            url = "https://localhost:" + port(gateway, "443")
            time.sleep(2)
            try:
                empty_status = request("/", authenticated=False)[0]
            except OSError:
                empty_status = 0
            check(
                empty_status in {0, 401},
                "empty authentication file never opens anonymous access",
            )
            print(
                f"{checks} cloud gateway checks passed; no real model calls.",
                flush=True,
            )
        finally:
            for name in reversed(containers):
                subprocess.run(
                    ["docker", "rm", "-f", "-v", name], capture_output=True, check=False
                )
            subprocess.run(
                ["docker", "network", "rm", network], capture_output=True, check=False
            )
            subprocess.run(
                ["docker", "volume", "rm", volume], capture_output=True, check=False
            )


if __name__ == "__main__":
    main()
