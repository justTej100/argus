from __future__ import annotations

import pytest

from ai.clients import GeminiAPIError, _post_json


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._body = body or {'error': {'message': 'unavailable'}}

    def json(self) -> dict:
        return self._body


class _FakeHttp:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls = 0

    async def post(self, *_args, **_kwargs) -> _FakeResponse:
        idx = min(self.calls, len(self.statuses) - 1)
        code = self.statuses[idx]
        self.calls += 1
        body = {'ok': True} if code < 400 else {'error': {'message': 'unavailable'}}
        return _FakeResponse(code, body)


@pytest.mark.asyncio
async def test_post_json_retries_503_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHttp([503, 503, 200])

    class _Client:
        async def __aenter__(self):
            return fake

        async def __aexit__(self, *_args):
            return None

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr('ai.clients.httpx.AsyncClient', lambda **_kw: _Client())
    monkeypatch.setattr('ai.clients.asyncio.sleep', fast_sleep)

    result = await _post_json('http://test', headers={}, payload={'x': 1}, retries=4)
    assert result == {'ok': True}
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_post_json_raises_after_exhausted_503(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHttp([503, 503, 503, 503])

    class _Client:
        async def __aenter__(self):
            return fake

        async def __aexit__(self, *_args):
            return None

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr('ai.clients.httpx.AsyncClient', lambda **_kw: _Client())
    monkeypatch.setattr('ai.clients.asyncio.sleep', fast_sleep)

    with pytest.raises(GeminiAPIError) as exc_info:
        await _post_json('http://test', headers={}, payload={}, retries=4)
    assert exc_info.value.status_code == 503
    assert '503' in str(exc_info.value)
