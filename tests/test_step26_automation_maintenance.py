import json
from pathlib import Path

from maintenance.diagnostics import build_pipeline_diagnosis, render_diagnosis_markdown
from maintenance.documentation import check_documentation_sync
from maintenance.github_issues import sync_diagnosis_issue


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeGitHubOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=30):
        self.requests.append(request)
        return FakeResponse(self.responses.pop(0))


def test_provider_failure_is_retryable_and_creates_issue():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failure",
        sources=[
            {
                "status": "partial_success",
                "warnings": [
                    {
                        "step": "news_ingestion",
                        "status": "failed",
                        "message": "HTTP Error 503: Service Unavailable",
                    }
                ],
            }
        ],
    )

    assert diagnosis["status"] == "failed"
    assert diagnosis["findings"][0]["category"] == "provider_unavailable"
    assert diagnosis["findings"][0]["retryable"] is True
    assert diagnosis["issue"]["should_create"] is True
    assert diagnosis["automation"]["llm_used"] is False
    assert diagnosis["automation"]["direct_main_push_allowed"] is False


def test_supabase_payload_mismatch_has_non_retryable_schema_action():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-outcomes",
        workflow_status="failed",
        sources=[
            {
                "status": "failed",
                "errors": [
                    "Supabase upsert failed with HTTP 400: PGRST102 All object keys must match"
                ],
            }
        ],
    )

    finding = diagnosis["findings"][0]
    assert finding["category"] == "supabase_schema"
    assert finding["retryable"] is False
    assert "migration" in finding["recommended_action"]


def test_success_without_findings_does_not_create_issue():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-prices",
        workflow_status="success",
        sources=[{"status": "success", "warnings": [], "errors": []}],
    )

    assert diagnosis["status"] == "success"
    assert diagnosis["findings"] == []
    assert diagnosis["issue"]["should_create"] is False
    assert "No actionable finding" in render_diagnosis_markdown(diagnosis)


def test_degraded_ml_health_report_creates_trackable_issue():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-outcomes",
        workflow_status="success",
        sources=[
            {
                "overall_status": "degraded",
                "components": {
                    "calibration": {
                        "status": "degraded",
                        "summary": "Calibration report has 6 warning(s).",
                    }
                },
            }
        ],
    )

    assert diagnosis["status"] == "degraded"
    assert diagnosis["findings"][0]["category"] == "ml_health"
    assert diagnosis["issue"]["should_create"] is True


def test_same_pipeline_category_and_step_has_stable_fingerprint():
    first = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failed",
        message="HTTP Error 503 from provider",
    )
    second = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failed",
        message="HTTP Error 503 from provider again",
    )

    assert first["issue"]["fingerprint"] == second["issue"]["fingerprint"]


def test_diagnosis_redacts_secrets_before_issue_body():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failed",
        sources=[
            {
                "status": "failed",
                "errors": [
                    "provider failed api_key=sk-or-v1-super-secret-value password=hunter2"
                ],
            }
        ],
    )

    serialized = json.dumps(diagnosis)
    assert "super-secret-value" not in serialized
    assert "hunter2" not in serialized
    assert "[REDACTED]" in serialized


def test_github_issue_sync_creates_new_issue_when_fingerprint_is_new():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failed",
        message="HTTP Error 503 from provider",
    )
    opener = FakeGitHubOpener([[], {"number": 12, "html_url": "https://example.test/issues/12"}])

    result = sync_diagnosis_issue(
        diagnosis,
        repository="owner/repo",
        token="token",
        opener=opener,
    )

    assert result == {
        "status": "created",
        "issue_number": 12,
        "issue_url": "https://example.test/issues/12",
    }
    assert opener.requests[0].method == "GET"
    assert opener.requests[1].method == "POST"


def test_github_issue_sync_comments_on_existing_fingerprint():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-news",
        workflow_status="failed",
        message="HTTP Error 503 from provider",
    )
    fingerprint = diagnosis["issue"]["fingerprint"]
    opener = FakeGitHubOpener(
        [
            [
                {
                    "number": 7,
                    "html_url": "https://example.test/issues/7",
                    "body": f"<!-- market-agent-diagnosis:{fingerprint} -->",
                }
            ],
            {"id": 100},
        ]
    )

    result = sync_diagnosis_issue(
        diagnosis,
        repository="owner/repo",
        token="token",
        opener=opener,
    )

    assert result["status"] == "updated"
    assert result["issue_number"] == 7
    assert opener.requests[1].full_url.endswith("/issues/7/comments")


def test_issue_sync_skips_non_actionable_diagnosis():
    diagnosis = build_pipeline_diagnosis(
        pipeline="daily-prices",
        workflow_status="success",
    )

    result = sync_diagnosis_issue(diagnosis, repository="owner/repo", token="token")

    assert result == {"status": "skipped", "reason": "diagnosis_not_issue_worthy"}


def test_automation_change_requires_matching_documentation():
    findings = check_documentation_sync([".github/workflows/daily-prices.yml"])

    assert len(findings) == 1
    assert "automation" in findings[0]["message"].lower()


def test_automation_documentation_satisfies_sync_rule():
    findings = check_documentation_sync(
        [".github/workflows/daily-prices.yml", "docs/automation_maintenance.md"]
    )

    assert findings == []


def test_schema_change_requires_schema_guide():
    findings = check_documentation_sync(["supabase/migrations/009_example.sql"])

    assert findings[0]["accepted_docs"] == ["docs/supabase_schema.md"]


def test_all_scheduled_workflows_use_diagnosis_without_contents_write():
    workflow_names = [
        "daily-prices.yml",
        "daily-news.yml",
        "daily-outcomes.yml",
        "daily-ml-predictions.yml",
        "daily-research-fixtures.yml",
        "weekly-research-fixtures.yml",
        "weekly-ml-dataset.yml",
        "monthly-universe.yml",
    ]
    for workflow_name in workflow_names:
        text = Path(".github/workflows", workflow_name).read_text(encoding="utf-8")
        assert "uses: ./.github/actions/pipeline-diagnosis" in text
        assert "issues: write" in text
        assert "contents: read" in text
        assert "contents: write" not in text
        assert "data/maintenance/diagnoses/*" in text
