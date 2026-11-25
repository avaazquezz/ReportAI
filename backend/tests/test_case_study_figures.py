"""The engineering case study (/arquitectura in the panel) and the landing's "what's behind the
report" section quote figures read off this code. These tests fail when the code moves and the pages
don't, so no page states something the repo contradicts.

ponytail: the test counts on the page (backend and frontend) are not checked here; they only grow,
so a stale one understates. Refresh them by hand with each release.
"""

import json
import re
from pathlib import Path

import pytest

from app.services.agent.graph import build_graph
from tests.eval.golden import build_cases
from tests.test_tenant_isolation import ID_ROUTES

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# The dev container mounts only backend/; CI checks out the whole repository and runs these.
pytestmark = pytest.mark.skipif(not FRONTEND.is_dir(), reason="needs the frontend next to the backend (the repository checkout)")


def _landing(language: str) -> dict:
    return json.loads((FRONTEND / "i18n" / "locales" / language / "landing.json").read_text())["landing"]


def _home(language: str) -> dict:
    return json.loads((FRONTEND / "i18n" / "locales" / language / "home.json").read_text())["home"]


def _built(language: str) -> dict:
    return _home(language)["built"]


def _numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_page_counts_the_agent_graph_nodes(language: str) -> None:
    assert _numbers(_landing(language)["architecture"]["sub"]) == [len(build_graph().nodes)]


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_page_counts_the_routes_in_the_isolation_matrix(language: str) -> None:
    caption = _landing(language)["tenancy"]["matrixCaption"]
    assert _numbers(caption)[:2] == [len(ID_ROUTES)] * 2


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_landing_counts_the_agent_graph_nodes(language: str) -> None:
    assert _numbers(_built(language)["stages"]["agent"]["body"]) == [len(build_graph().nodes)]


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_landing_counts_the_routes_in_the_isolation_matrix(language: str) -> None:
    assert _numbers(_built(language)["facts"]["tenancy"]["body"])[:2] == [len(ID_ROUTES)] * 2


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_landing_quotes_the_golden_set_as_the_case_study_does(language: str) -> None:
    # The pass rates come from a paid run (pytest -m eval), so only the copies are compared; the
    # number of cases is read off the golden set itself.
    quoted = _numbers(_built(language)["facts"]["eval"]["body"])
    assert quoted == _numbers(_landing(language)["quality"]["figures"]["invented"]["source"])
    assert quoted[0] == len(build_cases())


def test_the_drawn_matrix_has_one_cell_per_route() -> None:
    sheet = (FRONTEND / "app" / "components" / "landing" / "TenancySheet.vue").read_text()
    drawn = re.search(r"const ROUTES_WITH_AN_ID = (\d+)", sheet)
    assert drawn is not None
    assert int(drawn.group(1)) == len(ID_ROUTES)


def test_the_pages_promise_the_audio_retention_the_hosted_service_runs_with() -> None:
    # The hosted service's compose pins it; an .env can't quietly break the FAQ and privacy policy.
    compose = (FRONTEND.parent / "infra" / "docker-compose.prod.yml").read_text()
    pinned = re.search(r'^\s+AUDIO_RETENTION_DAYS: "(\d+)"$', compose, re.MULTILINE)
    assert pinned is not None, "docker-compose.prod.yml must pin AUDIO_RETENTION_DAYS"
    days = int(pinned.group(1))
    for language, pattern in (("es", r"se borran a los (\d+) días"), ("en", r"deleted after (\d+) days")):
        promises = [_home(language)["faq"]["items"]["data"]["a"], _landing(language)["privacy"]["customerData"]["body"]]
        assert [int(m) for text in promises for m in re.findall(pattern, text)] == [days, days], language
