"""Create cloud settings locally; passwords never enter command arguments or Git."""

import argparse
import getpass
import os
import re
import subprocess
from pathlib import Path

CADDY = (
    "caddy:2.11.2-alpine@sha256:"
    "834468128c7696cec0ceea6172f7d692daf645ae51983ca76e39da54a97c570d"
)
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain", required=True, help="DNS hostname only, without scheme or port"
    )
    parser.add_argument("--rotate-password", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
        args.domain,
    ):
        parser.error("Use a lowercase DNS hostname, without URL/path/port")
    auth = ROOT / "secrets/cloud-auth.caddy"
    env = ROOT / ".env.cloud"
    if not args.rotate_password and (auth.exists() or env.exists()):
        parser.error("Settings already exist; preserve them or use --rotate-password")
    if args.rotate_password and not (auth.is_file() and env.is_file()):
        parser.error("Initialize first before rotating the password")
    password = getpass.getpass("Shared demo password (at least 20 characters): ")
    if (
        len(password) < 20
        or len(password.encode()) > 72
        or "\n" in password
        or "\r" in password
    ):
        parser.error("Use 20+ characters, at most 72 UTF-8 bytes, without line breaks")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords differ")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            CADDY,
            "caddy",
            "hash-password",
        ],
        input=(password + "\n").encode(),
        capture_output=True,
        check=True,
    )
    password = ""
    hashed = result.stdout.decode("utf-8").strip()
    if not re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", hashed):
        raise RuntimeError("Password hashing failed; configuration unchanged")
    os.umask(0o077)
    auth.parent.mkdir(exist_ok=True, mode=0o700)
    content = "demo " + hashed + "\n"
    # Keep the bind-mounted inode when rotating; a gateway restart reloads it.
    with auth.open("w" if args.rotate_password else "x", encoding="utf-8") as target:
        target.write(content)
    auth.chmod(0o600)
    if not args.rotate_password:
        release = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, text=True
        ).strip()
        with env.open("x", encoding="utf-8") as target:
            target.write(
                f"HARU_DOMAIN={args.domain}\nHARU_RELEASE={release}\nHARU_ADMIN_PORT=18088\nHARU_DEMO_AI=off\n"
            )
        env.chmod(0o600)
    print("Saved private configuration. Username: demo. No password was printed.")
    if args.rotate_password:
        print("Restart the gateway to apply the new password; do not restart the API.")


if __name__ == "__main__":
    main()
