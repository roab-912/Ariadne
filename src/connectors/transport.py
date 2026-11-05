"""HTTP borné, sans URL ni secret dans les pièces ou erreurs exposées."""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field


class ProviderError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class Evidence(BaseModel):
    source: str
    retrieved_at: datetime
    request: dict
    response: dict | list | None = None
    error: str | None = None


@dataclass
class Budget:
    max_calls: int = 100
    max_seconds: float = 45
    max_bytes: int = 24 * 1024 * 1024
    calls: int = 0
    bytes_received: int = 0
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        value = self.max_seconds - (time.monotonic() - self.started)
        if value <= 0:
            raise ProviderError("time_budget_exhausted")
        return value

    def charge_call(self):
        self.remaining()
        if self.calls >= self.max_calls:
            raise ProviderError("call_budget_exhausted")
        self.calls += 1


class BoundedHTTP:
    def __init__(self, budget: Budget, transport=None, secrets: tuple[str, ...] = ()):
        self.budget = budget
        self.client = httpx.Client(transport=transport, follow_redirects=False, trust_env=False)
        self.artifacts: list[Evidence] = []
        self.secrets = tuple(value for value in secrets if value)

    def close(self):
        self.client.close()

    def redact(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[redacted]")
            return value
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {self.redact(key): self.redact(item) for key, item in value.items()}
        return value

    def fetch(self, method: str, url: str, *, source: str, request: dict, **kwargs):
        self.budget.charge_call()
        artifact = Evidence(source=source, retrieved_at=datetime.now(timezone.utc), request=request)
        self.artifacts.append(artifact)
        try:
            timeout = min(6.0, self.budget.remaining())
            with self.client.stream(method, url, timeout=timeout, **kwargs) as response:
                if response.status_code == 429:
                    raise ProviderError("provider_rate_limited")
                if response.status_code in (401, 403):
                    raise ProviderError("provider_access_denied")
                if response.status_code != 200:
                    raise ProviderError("provider_http_error")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    self.budget.remaining()
                    size += len(chunk)
                    self.budget.bytes_received += len(chunk)
                    if size > 4 * 1024 * 1024 or self.budget.bytes_received > self.budget.max_bytes:
                        raise ProviderError("response_size_budget_exhausted")
                    chunks.append(chunk)
                value = json.loads(b"".join(chunks))
                if not isinstance(value, (dict, list)):
                    raise ProviderError("provider_invalid_json")
                artifact.response = self.redact(value)
                return artifact.response
        except (httpx.TimeoutException, TimeoutError):
            artifact.error = "provider_timeout"
            raise ProviderError(artifact.error) from None
        except httpx.HTTPError:
            artifact.error = "provider_transport_error"
            raise ProviderError(artifact.error) from None
        except (ValueError, RecursionError):
            artifact.error = "provider_invalid_json"
            raise ProviderError(artifact.error) from None
        except ProviderError as error:
            artifact.error = error.reason
            raise
