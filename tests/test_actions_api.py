from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from actions_api import create_server


class FakeTutorService:
    DEFAULT_DECK = "000-WuCai Inbox"
    ANKI_REVIEW_WRITEBACK_ENABLED = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_due_cards(self, **kwargs):
        self.calls.append(("get_due_cards", kwargs))
        return {"deck": kwargs["deck"], "returned": 0, "cards": []}

    def get_study_session(self, **kwargs):
        self.calls.append(("get_study_session", kwargs))
        return {
            "has_study_session": True,
            "session_id": kwargs.get("session_id") or "study_" + "a" * 32,
            "cards": [],
        }

    def get_tutor_context(self, **kwargs):
        self.calls.append(("get_tutor_context", kwargs))
        return {"card_id": kwargs["card_id"], "has_history": True}

    def record_triage_results(self, **kwargs):
        self.calls.append(("record_triage_results", kwargs))
        return {
            "session_id": kwargs["session_id"],
            "recorded_count": len(kwargs["results"]),
            "anki_mutated": False,
        }

    def decide_tutor_next_step(self, **kwargs):
        self.calls.append(("decide_tutor_next_step", kwargs))
        return {"state": "prompted_recall", "anki_mutated": False}

    def record_review_result(self, **kwargs):
        self.calls.append(("record_review_result", kwargs))
        return {"event_id": "review_123", "sync_status": "pending"}

    def sync_pending_reviews(self, **kwargs):
        self.calls.append(("sync_pending_reviews", kwargs))
        return {
            "dry_run": kwargs["dry_run"],
            "pending_found": 0,
            "applied": 0,
        }


class ActionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeTutorService()
        self.server = create_server(
            host="127.0.0.1", port=0, token="test-secret", service=self.service
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path: str, payload: dict, *, token: str | None = None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_rejects_missing_or_wrong_bearer_token(self) -> None:
        for token in (None, "wrong-secret"):
            with self.subTest(token=token), self.assertRaises(HTTPError) as caught:
                self.request("/v1/due-cards", {}, token=token)
            self.assertEqual(caught.exception.code, 401)
            caught.exception.close()
        self.assertEqual(self.service.calls, [])

    def test_due_cards_uses_safe_default_limit_five(self) -> None:
        status, payload = self.request(
            "/v1/due-cards", {}, token="test-secret"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["deck"], "000-WuCai Inbox")
        self.assertEqual(
            self.service.calls,
            [("get_due_cards", {"deck": "000-WuCai Inbox", "limit": 5})],
        )

    def test_study_session_reads_active_batch_without_anki_write(self) -> None:
        status, payload = self.request(
            "/v1/study-session", {}, token="test-secret"
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["has_study_session"])
        self.assertEqual(self.service.calls, [("get_study_session", {})])

    def test_record_review_only_delegates_to_durable_record_api(self) -> None:
        status, payload = self.request(
            "/v1/review-result",
            {
                "card_id": 123,
                "first_attempt_result": "failed",
                "tutor_state": "prompted_recall",
                "scheduler_snapshot": {},
            },
            token="test-secret",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["sync_status"], "pending")
        self.assertEqual(self.service.calls[0][0], "record_review_result")
        self.assertNotIn(
            "sync_pending_reviews", [name for name, _ in self.service.calls]
        )

    def test_triage_results_are_sent_in_one_batch(self) -> None:
        session_id = "study_" + "a" * 32
        results = [
            {
                "card_id": 123,
                "treatment": "remember",
                "source": "teacher",
                "reason": "durable recall is useful",
            },
            {
                "card_id": 124,
                "treatment": "reference",
                "source": "teacher",
                "reason": "lookup material",
            },
        ]

        status, payload = self.request(
            "/v1/triage-results",
            {"session_id": session_id, "results": results},
            token="test-secret",
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["recorded_count"], 2)
        self.assertEqual(
            self.service.calls,
            [
                (
                    "record_triage_results",
                    {"session_id": session_id, "results": results},
                )
            ],
        )

    def test_sync_defaults_to_dry_run(self) -> None:
        status, payload = self.request(
            "/v1/sync-reviews", {}, token="test-secret"
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(
            self.service.calls,
            [("sync_pending_reviews", {"dry_run": True, "limit": 100})],
        )

    def test_unknown_path_is_not_an_anki_proxy(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            self.request(
                "/v1/answer-cards", {"card_id": 123}, token="test-secret"
            )
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()
        self.assertEqual(self.service.calls, [])

    def test_openapi_uses_forwarded_public_host_and_bearer_auth(self) -> None:
        request = Request(
            self.base_url + "/openapi.json",
            headers={"Host": "example.trycloudflare.com", "X-Forwarded-Proto": "https"},
        )
        with urlopen(request, timeout=2) as response:
            schema = json.loads(response.read())
        self.assertEqual(
            schema["servers"], [{"url": "https://example.trycloudflare.com"}]
        )
        self.assertEqual(
            schema["components"]["securitySchemes"]["bearerAuth"]["scheme"],
            "bearer",
        )
        self.assertEqual(schema["components"]["schemas"], {})
        self.assertLessEqual(
            len(schema["paths"]["/v1/study-session"]["post"]["description"]),
            300,
        )
        for path in schema["paths"].values():
            response_schema = path["post"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            self.assertIn("properties", response_schema)
        non_consequential_paths = {
            "/v1/due-cards",
            "/v1/study-session",
            "/v1/tutor-context",
            "/v1/triage-results",
            "/v1/next-step",
            "/v1/review-result",
        }
        for path in non_consequential_paths:
            self.assertIs(
                schema["paths"][path]["post"]["x-openai-isConsequential"],
                False,
            )
        self.assertIs(
            schema["paths"]["/v1/sync-reviews"]["post"][
                "x-openai-isConsequential"
            ],
            True,
        )
        self.assertEqual(
            schema["paths"]["/v1/sync-reviews"]["post"]["requestBody"]
            ["content"]["application/json"]["schema"]["properties"]["dry_run"]
            ["default"],
            True,
        )
        triage_schema = schema["paths"]["/v1/triage-results"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        self.assertEqual(triage_schema["properties"]["results"]["maxItems"], 100)
        self.assertEqual(
            triage_schema["properties"]["results"]["items"]["properties"][
                "source"
            ]["enum"],
            ["teacher", "learner_override"],
        )


if __name__ == "__main__":
    unittest.main()
