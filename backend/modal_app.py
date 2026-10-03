"""Modal entry points. Deploy only after verifying account spending caps."""

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import modal

GUARD_MESSAGE = (
    "Cloud execution is blocked. Manually verify TiDB, Modal ($0 out-of-pocket "
    "limit and a usage budget below free credits), and free provider cost controls; "
    "then set SPEND_GUARDS_VERIFIED=true in backend/.env.modal and update the "
    "data-intelligence Modal Secret."
)
REQUIRED_SECRET_FIELDS = (
    "DATABASE_URL",
    "CLERK_ISSUER",
    "CLERK_JWKS_URL",
    "OPENROUTER_API_KEY",
    "FRONTEND_ORIGIN",
)


def require_spend_guards(values: Mapping[str, str]) -> None:
    if values.get("SPEND_GUARDS_VERIFIED", "false").lower() != "true":
        raise RuntimeError(GUARD_MESSAGE)
    if values.get("ALLOW_PAID_PROVIDERS", "false").lower() != "false":
        raise RuntimeError("ALLOW_PAID_PROVIDERS must remain false for Modal deployment")
    if values.get("DISPATCH_MODE") != "modal":
        raise RuntimeError("DISPATCH_MODE must be modal in the Modal Secret")
    for name in REQUIRED_SECRET_FIELDS:
        if not values.get(name):
            raise RuntimeError(f"{name} is required in the data-intelligence Modal Secret")
    if not values["DATABASE_URL"].startswith("mysql+pymysql://"):
        raise RuntimeError("Modal DATABASE_URL must use mysql+pymysql:// for TiDB")
    tls = parse_qs(urlsplit(values["DATABASE_URL"]).query)
    if (
        not tls.get("ssl_ca")
        or tls.get("ssl_verify_cert", [""])[0].lower() != "true"
        or tls.get("ssl_verify_identity", [""])[0].lower() != "true"
    ):
        raise RuntimeError(
            "Modal DATABASE_URL must enable TiDB TLS certificate and identity checks"
        )


if modal.is_local():
    # The Modal Secret is unavailable to the CLI process. Check only guard fields
    # in the file used to create it; never log or package that file.
    dotenv_path = Path(__file__).with_name(".env.modal")
    if not dotenv_path.is_file():
        raise RuntimeError(f"{GUARD_MESSAGE} Missing backend/.env.modal.")
    guards = {}
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() in set(REQUIRED_SECRET_FIELDS) | {
            "SPEND_GUARDS_VERIFIED",
            "ALLOW_PAID_PROVIDERS",
            "DISPATCH_MODE",
        }:
            guards[name.strip()] = value.strip().strip("\"'")
    require_spend_guards(guards)
else:
    require_spend_guards(os.environ)


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ca-certificates")
    .pip_install_from_pyproject("backend/pyproject.toml")
    .run_commands("python -m playwright install --with-deps chromium")
    .workdir("/root")
    .add_local_dir("backend/app", remote_path="/root/app")
)
app = modal.App(
    "data-intelligence",
    image=image,
    secrets=[modal.Secret.from_name("data-intelligence")],
)


@app.function()
@modal.asgi_app()
def api():
    require_spend_guards(os.environ)
    from app.main import app as fastapi_app

    return fastapi_app


@app.function(timeout=600)
def run_worker(run_id: str):
    require_spend_guards(os.environ)
    from app.worker import drain_queue

    drain_queue(run_id)


@app.function(schedule=modal.Cron("* * * * *"), timeout=600)
def minute_scheduler():
    require_spend_guards(os.environ)
    from app.worker import tick

    queued = tick()
    if queued:
        run_worker.spawn(queued[0])
