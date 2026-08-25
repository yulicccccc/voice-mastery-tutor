"""Narrow HTTP adapter for a private ChatGPT GPT Action.

The adapter deliberately exposes only the existing Tutor/Review public functions.
It never proxies arbitrary AnkiConnect actions. Real review writes remain guarded by
the existing ANKI_REVIEW_WRITEBACK_ENABLED feature flag and dry-run default.
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlsplit

import anki_mcp_server as tutor_service


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 28766
MAX_REQUEST_BYTES = 256 * 1024
KEYCHAIN_SERVICE = "voice-mastery-tutor-actions"


def load_actions_token() -> str:
    """Load the bearer token without printing it or storing it in the repo."""
    from_environment = os.environ.get("ACTIONS_API_TOKEN", "").strip()
    if from_environment:
        return from_environment

    try:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "No Actions bearer token is available. Store one in macOS Keychain "
            f"under service {KEYCHAIN_SERVICE!r} or set ACTIONS_API_TOKEN."
        ) from exc

    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("The Actions bearer token is empty.")
    return token


def _openapi_schema(base_url: str) -> dict[str, Any]:
    states = [
        "retrieval_gap",
        "independent_recall",
        "prompted_recall",
        "understanding_gap",
        "known_but_not_transferable",
        "mastered",
        "skipped_low_value",
        "paused",
    ]
    snapshot = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "modified",
            "reps",
            "lapses",
            "queue",
            "type",
            "due",
            "interval",
            "factor",
            "left",
        ],
        "properties": {
            name: {"type": "integer"}
            for name in (
                "modified",
                "reps",
                "lapses",
                "queue",
                "type",
                "due",
                "interval",
                "factor",
                "left",
            )
        },
    }

    def post_operation(
        operation_id: str,
        summary: str,
        description: str,
        properties: dict[str, Any],
        required: list[str],
        *,
        consequential: bool = False,
    ) -> dict[str, Any]:
        return {
            "post": {
                "operationId": operation_id,
                "summary": summary,
                "description": description,
                "x-openai-isConsequential": consequential,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": properties,
                                "required": required,
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Successful operation",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": True,
                                }
                            }
                        },
                    },
                    "400": {"description": "Invalid request"},
                    "401": {"description": "Missing or invalid bearer token"},
                    "502": {"description": "Local Anki service unavailable"},
                },
            }
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Private AI Anki Tutor",
            "description": (
                "Private, narrow bridge to the user's local Tutor engine and Anki. "
                "Review recording is durable; scheduler sync is dry-run by default."
            ),
            "version": "0.1.0",
        },
        "servers": [{"url": base_url.rstrip("/")}],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/v1/due-cards": post_operation(
                "getDueCards",
                "Read due Anki cards",
                "Read teacher-facing due cards. Never changes Anki scheduling.",
                {
                    "deck": {"type": "string", "default": "000-WuCai Inbox"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 5,
                    },
                },
                [],
            ),
            "/v1/study-session": post_operation(
                "getStudySession",
                "Load candidates and derive the active learning queue",
                (
                    "Load the immutable candidate batch and durable triage state. "
                    "Use mode=triage for compact classification content. After "
                    "triage is persisted, use mode=tutoring to preload the compact "
                    "active tutoring batch before Voice Mode. Never changes Anki."
                ),
                {
                    "session_id": {
                        "type": ["string", "null"],
                        "pattern": "^study_[0-9a-f]{32}$",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["full", "triage", "tutoring"],
                        "default": "full",
                    },
                    "card_id": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                    },
                },
                [],
            ),
            "/v1/tutor-context": post_operation(
                "getTutorContext",
                "Restore durable Tutor context",
                (
                    "Restore compact teaching memory for one card from local durable "
                    "events, independent of the ChatGPT conversation."
                ),
                {"card_id": {"type": "integer", "minimum": 1}},
                ["card_id"],
            ),
            "/v1/triage-results": post_operation(
                "recordTriageResults",
                "Persist one batch of Teacher Triage results",
                (
                    "Persist treatments for untriaged candidate cards in one local "
                    "append-only batch. Never changes the StudySession or Anki."
                ),
                {
                    "session_id": {
                        "type": "string",
                        "pattern": "^study_[0-9a-f]{32}$",
                    },
                    "results": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 100,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "card_id",
                                "treatment",
                                "source",
                                "reason",
                            ],
                            "properties": {
                                "card_id": {"type": "integer", "minimum": 1},
                                "treatment": {
                                    "type": "string",
                                    "enum": [
                                        "reference",
                                        "understand",
                                        "remember",
                                        "apply",
                                        "practice",
                                        "ignore",
                                    ],
                                },
                                "source": {
                                    "type": "string",
                                    "enum": ["teacher", "learner_override"],
                                },
                                "reason": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
                ["session_id", "results"],
            ),
            "/v1/next-step": post_operation(
                "decideTutorNextStep",
                "Choose and persist the next teaching step",
                (
                    "Apply the lightweight Tutor policy to one learner answer. "
                    "Persists Tutor state but never changes Anki scheduling."
                ),
                {
                    "card_id": {"type": "integer", "minimum": 1},
                    "session_id": {
                        "type": ["string", "null"],
                        "pattern": "^study_[0-9a-f]{32}$",
                    },
                    "note_id": {"type": ["integer", "null"]},
                    "learner_answer": {"type": "string", "minLength": 1},
                    "assessment": {
                        "type": "string",
                        "enum": ["correct", "incorrect", "partial", "unknown"],
                    },
                    "was_prompted": {"type": "boolean", "default": False},
                    "consecutive_incorrect": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                    },
                    "question_type": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "concept",
                            "abstract",
                            "process",
                            "application",
                            "decision",
                            "causal",
                        ],
                        "default": "concept",
                    },
                    "has_personal_context": {"type": "boolean", "default": False},
                    "stable_mastery_evidence": {
                        "type": "boolean",
                        "default": False,
                    },
                    "learner_rejects_mastery": {
                        "type": "boolean",
                        "default": False,
                    },
                },
                ["card_id", "learner_answer", "assessment"],
            ),
            "/v1/review-result": post_operation(
                "recordReviewResult",
                "Durably record one completed card interaction",
                (
                    "Create exactly one idempotent ReviewEvent from the first unaided "
                    "attempt. This operation does not call Anki or change scheduling."
                ),
                {
                    "card_id": {"type": "integer", "minimum": 1},
                    "session_id": {
                        "type": ["string", "null"],
                        "pattern": "^study_[0-9a-f]{32}$",
                    },
                    "note_id": {"type": ["integer", "null"]},
                    "first_attempt_result": {
                        "type": "string",
                        "enum": ["succeeded", "failed", "not_attempted"],
                    },
                    "tutor_state": {"type": "string", "enum": states},
                    "hints_used": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                    },
                    "scheduler_snapshot": snapshot,
                },
                [
                    "card_id",
                    "first_attempt_result",
                    "tutor_state",
                    "scheduler_snapshot",
                ],
            ),
            "/v1/sync-reviews": post_operation(
                "syncPendingReviews",
                "Safely inspect or synchronize pending reviews",
                (
                    "Check durable pending ReviewEvents. dry_run defaults to true. "
                    "A real Anki scheduler review additionally requires the local "
                    "ANKI_REVIEW_WRITEBACK_ENABLED feature flag."
                ),
                {
                    "session_id": {
                        "type": ["string", "null"],
                        "pattern": "^study_[0-9a-f]{32}$",
                    },
                    "dry_run": {"type": "boolean", "default": True},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "default": 100,
                    },
                },
                [],
                consequential=True,
            ),
        },
        "components": {
            "schemas": {},
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            }
        },
    }


class ActionsRouter:
    """Authenticate and dispatch only allowlisted Tutor operations."""

    def __init__(self, token: str, service: Any = tutor_service) -> None:
        if not token:
            raise ValueError("Actions bearer token must not be empty")
        self._token = token
        self._service = service
        self._routes: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
            "/v1/due-cards": (
                service.get_due_cards,
                {"deck": service.DEFAULT_DECK, "limit": 5},
            ),
            "/v1/study-session": (service.get_study_session, {}),
            "/v1/tutor-context": (service.get_tutor_context, {}),
            "/v1/triage-results": (service.record_triage_results, {}),
            "/v1/next-step": (service.decide_tutor_next_step, {}),
            "/v1/review-result": (service.record_review_result, {}),
            "/v1/sync-reviews": (
                service.sync_pending_reviews,
                {"dry_run": True, "limit": 100},
            ),
        }

    def authorized(self, authorization: str | None) -> bool:
        if not authorization or not authorization.startswith("Bearer "):
            return False
        supplied = authorization.removeprefix("Bearer ").strip()
        return bool(supplied) and hmac.compare_digest(supplied, self._token)

    def dispatch(self, path: str, payload: dict[str, Any]) -> Any:
        route = self._routes.get(path)
        if route is None:
            raise KeyError(path)
        operation, defaults = route
        arguments = {**defaults, **payload}
        return operation(**arguments)


def make_handler(router: ActionsRouter) -> type[BaseHTTPRequestHandler]:
    class ActionsRequestHandler(BaseHTTPRequestHandler):
        server_version = "VoiceMasteryTutorActions/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Keep normal request logs but never include authorization headers/bodies.
            super().log_message(format, *args)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlsplit(self.path).path
            if path == "/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "anki_writeback_enabled": bool(
                            tutor_service.ANKI_REVIEW_WRITEBACK_ENABLED
                        ),
                    },
                )
                return
            if path == "/openapi.json":
                configured = os.environ.get("ACTIONS_PUBLIC_BASE_URL", "").strip()
                forwarded_proto = self.headers.get("X-Forwarded-Proto", "https")
                host = self.headers.get("Host", "")
                base_url = configured or f"{forwarded_proto}://{host}"
                self._send_json(HTTPStatus.OK, _openapi_schema(base_url))
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlsplit(self.path).path
            if not router.authorized(self.headers.get("Authorization")):
                self._send_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "missing_or_invalid_bearer_token"},
                )
                return

            content_length = self.headers.get("Content-Length")
            try:
                length = int(content_length or "0")
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_length"})
                return
            if length < 0 or length > MAX_REQUEST_BYTES:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "request_too_large"},
                )
                return

            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                result = router.dispatch(path, payload)
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            except (TypeError, ValueError) as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request", "detail": str(exc)},
                )
                return
            except RuntimeError as exc:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "local_service_unavailable", "detail": str(exc)},
                )
                return
            except Exception:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "internal_error"},
                )
                return

            self._send_json(HTTPStatus.OK, result)

        def _send_json(self, status: HTTPStatus, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ActionsRequestHandler


def create_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    token: str | None = None,
    service: Any = tutor_service,
) -> ThreadingHTTPServer:
    router = ActionsRouter(token or load_actions_token(), service=service)
    return ThreadingHTTPServer((host, port), make_handler(router))


def main() -> None:
    host = os.environ.get("ACTIONS_HOST", DEFAULT_HOST)
    port = int(os.environ.get("ACTIONS_PORT", str(DEFAULT_PORT)))
    server = create_server(host=host, port=port)
    print(
        f"Private Actions adapter listening on http://{host}:{port}; "
        f"Anki writeback enabled={tutor_service.ANKI_REVIEW_WRITEBACK_ENABLED}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
