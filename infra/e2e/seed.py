"""Sets up the end-to-end test's installation the way its administrator would, through the product
itself: the one-time code from `python -m app.cli setup-code` (what `reportai setup-code` runs),
the setup wizard's API, a starter document type, and the address its reports are emailed to.

Runs in the backend image (the `seed` service of infra/docker-compose.e2e.yml), standard library
only. Idempotent: an installation already set up is left alone, so the test can run again on the
same stack. The accounts and addresses are the test's (frontend/e2e/main-flow.spec.ts).
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from typing import Any

API = "http://backend:8000"
ADMIN_EMAIL = "admin@e2e.example.com"
ADMIN_PASSWORD = "e2e-admin-password"
REPORT_RECIPIENT = "office@e2e.example.com"
STARTER = "site_visit"


def call(method: str, path: str, body: dict[str, Any] | None = None, token: str | None = None) -> Any:
    request = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body else None)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    # An HTTPError propagates: a refused step must stop the seed, not leave half an installation.
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def setup_code() -> str:
    output = subprocess.run(
        [sys.executable, "-m", "app.cli", "setup-code"], check=True, capture_output=True, text=True
    ).stdout
    match = re.search(r"Setup code: (\S+)", output)
    if match is None:
        raise SystemExit(f"No setup code in the CLI's output: {output!r}")
    return match.group(1)


def main() -> None:
    if os.environ.get("REPORTAI_E2E") != "1":
        raise SystemExit("Refusing to run: this seeds the end-to-end test's installation only (REPORTAI_E2E=1)")
    if not call("GET", "/setup/status")["needs_setup"]:
        print("seed: already set up, nothing to do")
        return

    tokens = call(
        "POST",
        "/setup/complete",
        {
            "code": setup_code(),
            "company": {"name": "E2E Inspections", "language": "en", "timezone": "Europe/Madrid"},
            "admin": {"full_name": "E2E Admin", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            # The stand-in provider (infra/e2e/ai_stub.py), entered like any OpenAI-compatible one.
            "extraction": {
                "provider": "openai_compatible",
                "model": "e2e-stub",
                "base_url": "http://ai-stub:8080/v1",
                "api_key": "e2e-not-a-real-key",
            },
            "email": {"host": "mailpit", "port": 1025, "security": "none", "from_address": "reports@e2e.example.com"},
        },
    )
    token = tokens["access_token"]

    doc_type = call("POST", f"/starter-templates/{STARTER}/install", token=token)
    editable = ("name", "description", "field_schema", "prompt_instructions", "is_active")
    call(
        "PATCH",
        f"/document-types/{doc_type['id']}",
        {**{key: doc_type[key] for key in editable}, "notification_emails": [REPORT_RECIPIENT]},
        token=token,
    )
    print(f"seed: installation set up, {doc_type['name']!r} emails {REPORT_RECIPIENT}")


if __name__ == "__main__":
    main()
