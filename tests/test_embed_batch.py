from __future__ import annotations

import pytest

from ai import clients


@pytest.mark.asyncio
async def test_embed_many_batches(monkeypatch: pytest.MonkeyPatch) -> None:
  calls: list[int] = []

  async def fake_embed_batch(texts: list[str]) -> list[list[float]]:
      calls.append(len(texts))
      return [[float(index), 1.0] for index in range(len(texts))]

  monkeypatch.setattr(clients, 'embed_batch', fake_embed_batch)

  vectors = await clients.embed_many(['a', 'b', 'c'], batch_size=2)
  assert len(vectors) == 3
  assert calls == [2, 1]
