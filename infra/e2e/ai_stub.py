"""Stands in for the AI provider in the end-to-end test (infra/docker-compose.e2e.yml).

Speaks just enough of the OpenAI chat completions API for the openai_compatible path of
backend/app/services/llm.py: a forced function call whose arguments are the report's fields, and
the token usage it reads. The installation is pointed here in the setup wizard (infra/e2e/seed.py),
like any OpenAI-compatible provider, so the backend runs unchanged.

Standard library only: nothing to install, nothing to drift. Anything it was not written for (a
tool other than the extraction, fields of another document type) is answered with a 400, so the
report fails loudly instead of the test passing on an answer nobody checked.
"""

import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PORT = 8080
EXTRACT_TOOL = "extract_report_fields"  # TOOL_NAME in backend/app/services/agent/nodes/extract.py

# The "site_visit" starter's fields (backend/app/services/templates/starters.py), as the test
# (frontend/e2e/main-flow.spec.ts) expects to see them. The findings are the note itself: the test
# can then tell that the text it typed is what reached the model.
FIELDS: dict[str, Any] = {
    "cliente": "Acme Facilities",
    "lugar": "12 Harbour Road",
    "fecha": "2026-11-20",
    "asistentes": ["Jane Doe", "Tom Lee"],
    "motivo": "Quarterly fire safety walkthrough",
    "proximos_pasos": ["Replace the extinguishers"],
}
ECHOED_FIELD = "conclusiones"


class StubError(Exception):
    """A request this stub does not answer: sent back as the provider's 400."""


def _requested_fields(parameters: dict[str, Any]) -> set[str]:
    """The field names of the extraction's JSON schema (pydantic puts the nested model in $defs)."""
    fields = parameters["properties"]["fields"]
    if ref := fields.get("$ref"):
        fields = parameters["$defs"][ref.rsplit("/", 1)[-1]]
    return set(fields["properties"])


def _note(messages: list[dict[str, Any]]) -> str:
    """The report's text: extract.py sends it as "Message:\\n<text>", then any corrections."""
    user = next(m["content"] for m in messages if m["role"] == "user")
    return str(user).removeprefix("Message:\n").split("\n\n", 1)[0].strip()


def _extraction(body: dict[str, Any]) -> dict[str, Any]:
    tool = body["tools"][0]["function"]
    wanted = _requested_fields(tool["parameters"])
    known = {*FIELDS, ECHOED_FIELD}
    if not known <= wanted:
        raise StubError(f"the stub answers the site_visit starter's fields; this document type asks for {sorted(wanted)}")
    note = _note(body["messages"])
    fields = {name: None for name in wanted} | FIELDS | {ECHOED_FIELD: note}
    # A quote only where the value is word for word in the note, as a real model is told to do.
    evidence = {name: value if isinstance(value, str) and value in note else None for name, value in fields.items()}
    return {"fields": fields, "evidence": evidence}


def completion(body: dict[str, Any]) -> dict[str, Any]:
    tool_name = body.get("tool_choice", {}).get("function", {}).get("name")
    if tool_name != EXTRACT_TOOL:
        raise StubError(f"the stub only answers a forced {EXTRACT_TOOL!r} call, not {tool_name!r}")
    arguments = _extraction(body)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body["model"],
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{uuid.uuid4().hex}",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": {"message": f"no route {self.path}", "type": "not_found"}})

    def do_POST(self) -> None:
        if not self.path.endswith("/chat/completions"):
            self._send(404, {"error": {"message": f"no route {self.path}", "type": "not_found"}})
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            self._send(200, completion(body))
        except StubError as exc:
            print(f"ai-stub: refused: {exc}", file=sys.stderr, flush=True)
            self._send(400, {"error": {"message": str(exc), "type": "invalid_request_error"}})


if __name__ == "__main__":
    print(f"ai-stub: listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
