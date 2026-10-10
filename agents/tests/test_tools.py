import asyncio
import json

import pytest

from agence.graphs.departments import DEPARTMENT_SPECS, EXECUTORS, actions_doc
from agence.tools import ads, crm
from agence.tools.analytics import ga4_report
from agence.tools.common import NotConfigured
from agence.tools.seo import search_console_queries, seo_audit
from agence.state import DEPARTMENTS

CLIENT = {"id": "test", "name": "Test", "settings": {}}
CONFIG = {"configurable": {"client": CLIENT, "run_id": "run_test"}}


def run(coro):
    return asyncio.run(coro)


def test_every_department_has_a_spec_and_prompt():
    assert set(DEPARTMENT_SPECS) == set(DEPARTMENTS)
    for dep in DEPARTMENTS:
        assert actions_doc(dep)


def test_executors_are_documented():
    assert set(EXECUTORS) == {
        "postiz_schedule",
        "google_ads_create_campaign",
        "meta_create_campaign",
        "crm_create_company",
        "crm_create_person",
        "email_campaign",
    }
    doc = actions_doc("crm")
    assert "email_campaign" in doc and "payload" in doc


def test_seo_audit_on_real_page():
    result = json.loads(run(seo_audit.ainvoke({"url": "https://example.com"})))
    assert result["title"] == "Example Domain"
    assert isinstance(result["h1"], list) and result["word_count"] > 0


@pytest.mark.parametrize("tool", [ga4_report, search_console_queries, ads.google_ads_campaign_metrics, ads.meta_ads_insights])
def test_unconfigured_tools_degrade_gracefully(tool):
    result = run(tool.ainvoke({}, CONFIG))
    assert result.startswith("NON DISPONIBLE"), result


def test_unconfigured_executors_raise():
    with pytest.raises(NotConfigured):
        run(crm.email_campaign(CLIENT, {"subject": "x", "body": "y"}))
    with pytest.raises(NotConfigured):
        run(ads.create_meta_campaign(CLIENT, {"name": "x"}))
