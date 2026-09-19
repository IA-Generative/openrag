"""Unit tests for ``scripts/reembed_bge_m3.py``.

The tool is loaded by path, like the numbered Milvus migrations it borrows its
rebuild helpers from. Milvus is an in-memory fake that actually stores rows, so
the tests check the state a run leaves behind rather than the calls it made.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_VECTOR_KEYS = ("vector", "sparse")


@pytest.fixture(scope="module")
def tool():
    sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("reembed_bge_m3", _SCRIPTS_DIR / "reembed_bge_m3.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses resolve their annotations through sys.modules
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPTS_DIR))
    return module


@pytest.fixture(scope="module")
def helpers(tool):
    return tool._load_rebuild_helpers()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

SOURCE = "openrag"
TARGET = "openrag_bge_m3_rebuild"
BACKUP = "openrag_gemma2_backup"
ASIDE = "openrag_bge_m3_rolled_back"
MODEL = "bge-m3"


def _desc(*, dim: int = 8, version: str | None = "2", properties: dict[str, str] | None = None) -> dict[str, Any]:
    """A describe_collection payload in the shape pymilvus returns one."""
    props = dict(properties or {})
    if version is not None:
        props["openrag.schema_version"] = version
    return {
        "fields": [
            {"name": "_id", "params": {}},
            {"name": "text", "params": {"max_length": 65535, "enable_analyzer": "true"}},
            {"name": "partition", "params": {"max_length": 65535}},
            {"name": "file_id", "params": {"max_length": 65535}},
            {"name": "vector", "params": {"dim": dim}},
            {"name": "created_at", "params": {}},
            {"name": "sparse", "params": {}},
        ],
        "properties": props,
    }


def _row(rid: int, text: str, partition: str = "p1", **extra: Any) -> dict[str, Any]:
    return {
        "_id": rid,
        "text": text,
        "partition": partition,
        "file_id": f"f{rid}",
        "created_at": None,
        "vector": [0.5] * 8,
        "sparse": {1: 0.3},
        "page": rid,
        "prev_section_id": None,
        **extra,
    }


class _SchemaRecorder:
    def __init__(self) -> None:
        self.fields: list[dict[str, Any]] = []

    def add_field(self, **kwargs) -> None:
        self.fields.append(kwargs)

    def add_function(self, function) -> None:
        pass


class _IndexRecorder:
    def add_index(self, **kwargs) -> None:
        pass


class _Iterator:
    def __init__(self, rows: list[dict[str, Any]], size: int) -> None:
        self._pages = [rows[i : i + size] for i in range(0, len(rows), size)]

    def next(self) -> list[dict[str, Any]]:
        return self._pages.pop(0) if self._pages else []

    def close(self) -> None:
        pass


class _FakeMilvus:
    """In-memory Milvus: collections are ``{_id: row}`` dicts."""

    def __init__(self, rows: list[dict[str, Any]], *, source_desc: dict[str, Any] | None = None) -> None:
        self.data: dict[str, dict[int, dict[str, Any]]] = {SOURCE: {r["_id"]: r for r in rows}}
        self.descs: dict[str, dict[str, Any]] = {SOURCE: source_desc or _desc()}
        self.renames: list[tuple[str, str]] = []
        self.rename_failures: set[str] = set()
        self.released: list[str] = []
        self.loaded: list[str] = []
        self.calls: list[str] = []
        self.on_flush = None
        self._schema = _SchemaRecorder()

    # -- introspection ------------------------------------------------
    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.data

    def describe_collection(self, collection_name: str) -> dict[str, Any]:
        return self.descs[collection_name]

    def load_collection(self, collection_name: str) -> None:
        self.loaded.append(collection_name)

    def release_collection(self, collection_name: str) -> None:
        self.released.append(collection_name)

    def list_indexes(self, collection_name: str) -> list[str]:
        return ["vector"]

    def describe_index(self, collection_name: str, index_name: str) -> dict[str, Any]:
        return {"pending_index_rows": 0}

    @staticmethod
    def _project(row: dict[str, Any], output_fields: list[str]) -> dict[str, Any]:
        if "$meta" in output_fields:
            return {k: v for k, v in row.items() if k not in _VECTOR_KEYS or k in output_fields}
        return {k: v for k, v in row.items() if k in output_fields}

    def query(self, collection_name: str, filter: str, output_fields: list[str]) -> list[dict[str, Any]]:  # noqa: A002
        rows = self.data[collection_name]
        if output_fields == ["count(*)"]:
            return [{"count(*)": len(rows)}]
        assert filter.startswith("_id in "), filter
        ids = ast.literal_eval(filter[len("_id in ") :])
        return [self._project(rows[i], output_fields) for i in ids if i in rows]

    def query_iterator(self, collection_name: str, filter: str, batch_size: int, output_fields: list[str]) -> _Iterator:  # noqa: A002
        assert "vector" not in output_fields, "a full scan must not haul the dense vectors"
        rows = [self._project(r, output_fields) for r in self.data[collection_name].values()]
        return _Iterator(copy.deepcopy(rows), batch_size)

    # -- mutation -----------------------------------------------------
    def create_schema(self, **kwargs) -> _SchemaRecorder:
        self._schema = _SchemaRecorder()
        return self._schema

    def prepare_index_params(self) -> _IndexRecorder:
        return _IndexRecorder()

    def create_collection(self, collection_name: str, **kwargs) -> None:
        fields = []
        for f in kwargs["schema"].fields:
            params = {k: f[k] for k in ("dim", "max_length") if k in f}
            fields.append({"name": f["field_name"], "params": params})
        self.data[collection_name] = {}
        self.descs[collection_name] = {"fields": fields, "properties": {}}
        self.calls.append(f"create:{collection_name}")

    def insert(self, collection_name: str, data: list[dict[str, Any]]) -> None:
        for row in data:
            assert row["_id"] not in self.data[collection_name], "insert over a live primary key"
            self.data[collection_name][row["_id"]] = copy.deepcopy(row)
        self.calls.append(f"insert:{collection_name}:{len(data)}")

    def delete(self, collection_name: str, filter: str) -> None:  # noqa: A002
        for rid in ast.literal_eval(filter[len("_id in ") :]):
            self.data[collection_name].pop(rid, None)

    def flush(self, collection_name: str) -> None:
        if self.on_flush is not None:
            hook, self.on_flush = self.on_flush, None
            hook()

    def alter_collection_properties(self, collection_name: str, properties: dict[str, str]) -> None:
        self.descs[collection_name]["properties"].update(properties)
        self.calls.append(f"alter:{collection_name}:{','.join(sorted(properties))}")

    def drop_collection_properties(self, collection_name: str, property_keys: list[str]) -> None:
        for key in property_keys:
            self.descs[collection_name]["properties"].pop(key, None)
        self.calls.append(f"drop_props:{collection_name}:{','.join(property_keys)}")

    def rename_collection(self, old_name: str, new_name: str) -> None:
        self.calls.append(f"rename:{old_name}->{new_name}")
        if old_name in self.rename_failures:
            raise RuntimeError(f"rename of {old_name} refused")
        self.renames.append((old_name, new_name))
        self.data[new_name] = self.data.pop(old_name)
        self.descs[new_name] = self.descs.pop(old_name)


def _vector_for(text: str, dim: int = 1024) -> list[float]:
    seed = hashlib.sha256(text.encode()).digest()
    return [(seed[i % len(seed)] + 1) / 256.0 for i in range(dim)]


class _FakeEmbedder:
    """Deterministic: the same text always lands on the same vector."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.requests = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.requests += 1
        self.seen.extend(texts)
        return [_vector_for(t) for t in texts]


def _rows(n: int = 5) -> list[dict[str, Any]]:
    return [_row(i, f"texte {i}", partition="p1" if i % 2 else "p2") for i in range(1, n + 1)]


def _scalars(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in _VECTOR_KEYS}


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_dry_run_build_changes_nothing(tool, helpers):
    client, embedder = _FakeMilvus(_rows()), _FakeEmbedder()

    plan = tool.build(client, helpers, embedder, SOURCE, MODEL, dry_run=True)

    assert len(plan.to_embed) == 5
    assert not client.has_collection(TARGET)
    assert embedder.seen == []


def test_build_creates_a_1024_dimension_target_marked_as_ours(tool, helpers):
    client = _FakeMilvus(_rows())

    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert helpers._vector_dim(client.describe_collection(TARGET)) == 1024
    props = client.describe_collection(TARGET)["properties"]
    assert props[tool.REEMBED_MODEL_PROPERTY] == MODEL
    assert props[helpers.ALLOW_INSERT_AUTO_ID] == "true"
    # The source description is only read: its own dimension must survive.
    assert helpers._vector_dim(client.describe_collection(SOURCE)) == 8


def test_build_keeps_ids_and_fields_and_recomputes_the_vector(tool, helpers):
    client = _FakeMilvus(_rows())

    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert set(client.data[TARGET]) == set(client.data[SOURCE])
    for rid, source_row in client.data[SOURCE].items():
        target_row = client.data[TARGET][rid]
        assert _scalars(target_row) == _scalars(source_row)
        assert target_row["vector"] == _vector_for(source_row["text"])
        assert "sparse" not in target_row  # a BM25 function output: Milvus regenerates it


def test_build_never_writes_to_the_source(tool, helpers):
    client = _FakeMilvus(_rows())
    before = copy.deepcopy(client.data[SOURCE])

    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.data[SOURCE] == before
    assert not any(c.split(":")[1] == SOURCE for c in client.calls)


def test_a_second_build_embeds_nothing(tool, helpers):
    client = _FakeMilvus(_rows())
    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)
    again = _FakeEmbedder()

    plan = tool.build(client, helpers, again, SOURCE, MODEL)

    assert plan.empty
    assert again.seen == []


def test_an_interrupted_build_resumes_where_it_stopped(tool, helpers):
    client = _FakeMilvus(_rows())
    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)
    for rid in (4, 5):  # as if the first run had died before these two
        del client.data[TARGET][rid]
    resumed = _FakeEmbedder()

    tool.build(client, helpers, resumed, SOURCE, MODEL)

    assert sorted(resumed.seen) == ["texte 4", "texte 5"]
    assert set(client.data[TARGET]) == {1, 2, 3, 4, 5}


def test_build_refuses_a_collection_it_did_not_create(tool, helpers):
    client = _FakeMilvus(_rows())
    client.data[TARGET] = {}
    client.descs[TARGET] = _desc(dim=1024)  # right name, right width, no marker

    with pytest.raises(tool.ReembedError, match="was not built by this tool"):
        tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)


def test_build_refuses_once_the_collection_was_swapped(tool, helpers):
    client = _FakeMilvus(_rows())
    client.data[BACKUP] = {}

    with pytest.raises(tool.ReembedError, match="already swapped"):
        tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)


# ---------------------------------------------------------------------------
# Catch-up: what changed in the source while the target was being built
# ---------------------------------------------------------------------------


def test_catch_up_adds_removes_and_refreshes(tool, helpers):
    client = _FakeMilvus(_rows())
    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    client.data[SOURCE][6] = _row(6, "texte 6")  # indexed meanwhile
    del client.data[SOURCE][1]  # deleted meanwhile
    client.data[SOURCE][2]["page"] = 99  # metadata edited in place, same _id
    client.data[SOURCE][3]["text"] = "texte 3 réécrit"  # text replaced in place
    catch_up = _FakeEmbedder()

    plan = tool.build(client, helpers, catch_up, SOURCE, MODEL)

    assert (plan.to_embed, plan.to_patch, plan.to_delete) == ([3, 6], [2], [1])
    assert sorted(catch_up.seen) == ["texte 3 réécrit", "texte 6"]  # the edited metadata cost no embedding
    assert set(client.data[TARGET]) == {2, 3, 4, 5, 6}
    assert client.data[TARGET][2]["page"] == 99
    assert client.data[TARGET][2]["vector"] == _vector_for("texte 2")
    assert client.data[TARGET][3]["vector"] == _vector_for("texte 3 réécrit")
    assert tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL).empty


def test_a_row_deleted_between_scan_and_fetch_is_skipped(tool, helpers):
    client = _FakeMilvus(_rows(3))
    real_query = client.query

    def query(collection_name, filter, output_fields):  # noqa: A002
        if collection_name == SOURCE and output_fields != ["count(*)"]:
            client.data[SOURCE].pop(2, None)
        return real_query(collection_name, filter, output_fields)

    client.query = query

    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert set(client.data[TARGET]) == {1, 3}


def test_a_short_answer_from_the_embedder_inserts_nothing(tool, helpers):
    client = _FakeMilvus(_rows())

    class _Short(_FakeEmbedder):
        def embed(self, texts):
            return super().embed(texts)[:-1]

    with pytest.raises(tool.ReembedError, match="refusing to insert"):
        tool.build(client, helpers, _Short(), SOURCE, MODEL)

    assert client.data[TARGET] == {}


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


def _built(tool, helpers, rows=None) -> _FakeMilvus:
    client = _FakeMilvus(rows or _rows())
    tool.build(client, helpers, _FakeEmbedder(), SOURCE, MODEL)
    client.calls.clear()
    return client


def test_finalize_swaps_the_names_and_keeps_the_old_collection(tool, helpers):
    client = _built(tool, helpers)

    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.renames == [(SOURCE, BACKUP), (TARGET, SOURCE)]
    assert helpers._vector_dim(client.describe_collection(SOURCE)) == 1024
    assert helpers._vector_dim(client.describe_collection(BACKUP)) == 8
    assert len(client.data[SOURCE]) == len(client.data[BACKUP]) == 5
    assert client.released == [BACKUP]
    assert client.loaded[-1] == SOURCE


def test_finalize_keeps_the_schema_version_of_the_source(tool, helpers):
    """A different stamp would make the application refuse the collection."""
    client = _built(tool, helpers)

    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.describe_collection(SOURCE)["properties"]["openrag.schema_version"] == "2"


def test_auto_id_override_is_dropped_before_the_swap(tool, helpers):
    client = _built(tool, helpers)

    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    drop = client.calls.index(f"drop_props:{TARGET}:{helpers.ALLOW_INSERT_AUTO_ID}")
    assert drop < client.calls.index(f"rename:{SOURCE}->{BACKUP}")
    assert helpers.ALLOW_INSERT_AUTO_ID not in client.describe_collection(SOURCE)["properties"]


def test_finalize_catches_up_before_swapping(tool, helpers):
    client = _built(tool, helpers)
    client.data[SOURCE][6] = _row(6, "texte 6")
    del client.data[SOURCE][1]

    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert set(client.data[SOURCE]) == {2, 3, 4, 5, 6}
    assert client.data[SOURCE][6]["vector"] == _vector_for("texte 6")


def test_a_source_still_being_written_to_aborts_the_swap(tool, helpers):
    client = _built(tool, helpers)
    client.data[SOURCE][6] = _row(6, "texte 6")  # gives the catch-up something to flush
    client.on_flush = lambda: client.data[SOURCE].__setitem__(7, _row(7, "écrit pendant finalize"))

    with pytest.raises(tool.ReembedError, match="source changed during finalize"):
        tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.renames == []


def test_an_in_place_edit_during_finalize_aborts_the_swap(tool, helpers):
    """Same row count, different content: only the second comparison sees it."""
    client = _built(tool, helpers)
    client.data[SOURCE][6] = _row(6, "texte 6")
    client.on_flush = lambda: client.data[SOURCE][2].__setitem__("page", 1234)

    with pytest.raises(tool.ReembedError, match="still differ"):
        tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.renames == []


def test_a_vector_on_the_wrong_row_aborts_the_swap(tool, helpers):
    client = _built(tool, helpers)
    client.data[TARGET][3]["vector"] = [1.0 if i % 2 else -1.0 for i in range(1024)]

    with pytest.raises(tool.ReembedError, match="does not match its own text"):
        tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.renames == []


def test_a_failed_swap_puts_the_original_collection_back(tool, helpers):
    client = _built(tool, helpers)
    client.rename_failures = {TARGET}

    with pytest.raises(RuntimeError, match="refused"):
        tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert helpers._vector_dim(client.describe_collection(SOURCE)) == 8
    assert client.has_collection(TARGET)


def test_a_load_that_fails_after_the_swap_is_not_reported_as_a_failure(tool, helpers):
    """Once the names are swapped, an error would tell the operator nothing was done."""
    client = _built(tool, helpers)
    real_load = client.load_collection

    def load(collection_name):
        if client.renames:
            raise RuntimeError("query node busy")
        real_load(collection_name)

    client.load_collection = load

    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)

    assert client.renames == [(SOURCE, BACKUP), (TARGET, SOURCE)]


def test_dry_run_finalize_changes_nothing(tool, helpers):
    client = _built(tool, helpers)
    client.data[SOURCE][6] = _row(6, "texte 6")

    tool.finalize(client, helpers, None, SOURCE, MODEL, dry_run=True)

    assert client.renames == []
    assert 6 not in client.data[TARGET]
    assert helpers.ALLOW_INSERT_AUTO_ID in client.describe_collection(TARGET)["properties"]


def test_finalize_without_a_built_target_fails(tool, helpers):
    with pytest.raises(tool.ReembedError, match="run `build` first"):
        tool.finalize(_FakeMilvus(_rows()), helpers, _FakeEmbedder(), SOURCE, MODEL)


def test_finalize_refuses_to_overwrite_an_existing_backup(tool, helpers):
    client = _built(tool, helpers)
    client.data[BACKUP] = {}

    with pytest.raises(tool.ReembedError, match="already exists"):
        tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def test_rollback_swaps_the_backup_back(tool, helpers):
    client = _built(tool, helpers)
    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)
    client.renames.clear()

    tool.rollback(client, helpers, SOURCE)

    assert client.renames == [(SOURCE, ASIDE), (BACKUP, SOURCE)]
    assert helpers._vector_dim(client.describe_collection(SOURCE)) == 8
    assert client.released[-1] == ASIDE


def test_dry_run_rollback_changes_nothing(tool, helpers):
    client = _built(tool, helpers)
    tool.finalize(client, helpers, _FakeEmbedder(), SOURCE, MODEL)
    client.renames.clear()

    tool.rollback(client, helpers, SOURCE, dry_run=True)

    assert client.renames == []


def test_rollback_without_a_backup_fails_loudly(tool, helpers):
    with pytest.raises(tool.ReembedError, match="nothing to roll back to"):
        tool.rollback(_FakeMilvus(_rows()), helpers, SOURCE)


# ---------------------------------------------------------------------------
# Embedding client
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status: int, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}
        self.text = "corps de la réponse"

    def json(self) -> dict[str, Any]:
        return self._body


def _ok(n: int, dim: int = 1024) -> _Response:
    # Out of order on purpose: the client must sort on `index`.
    data = [{"index": i, "embedding": [float(i)] * dim} for i in reversed(range(n))]
    return _Response(200, {"data": data})


class _Http:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any]) -> _Response:
        self.posts.append(json)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _client(tool, responses, *, max_rpm: int = 0, **kwargs):
    sleeps: list[float] = []
    http = _Http(responses)
    embedder = tool.GatewayEmbedder(
        "https://gateway.test/v1/", MODEL, "clé", http=http, sleep=sleeps.append, max_rpm=max_rpm, **kwargs
    )
    return embedder, http, sleeps


def test_embedder_returns_vectors_in_input_order(tool):
    embedder, http, _ = _client(tool, [_ok(3)])

    vectors = embedder.embed(["a", "b", "c"])

    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]
    assert http.posts == [{"model": MODEL, "input": ["a", "b", "c"]}]


def test_embedder_splits_into_bounded_batches(tool):
    embedder, http, _ = _client(tool, [_ok(32), _ok(32), _ok(6)])

    assert len(embedder.embed([str(i) for i in range(70)])) == 70
    assert [len(p["input"]) for p in http.posts] == [32, 32, 6]


def test_embedder_honours_retry_after_on_429(tool):
    embedder, http, sleeps = _client(tool, [_Response(429, headers={"Retry-After": "7"}), _ok(1)])

    assert len(embedder.embed(["a"])) == 1
    assert sleeps == [7.0]
    assert len(http.posts) == 2


def test_embedder_caps_an_absurd_retry_after(tool):
    embedder, _, sleeps = _client(tool, [_Response(429, headers={"Retry-After": "86400"}), _ok(1)])

    embedder.embed(["a"])

    assert sleeps == [300.0]


def test_embedder_retries_a_transport_error(tool):
    import httpx

    embedder, http, _ = _client(tool, [httpx.ConnectError("coupure"), _ok(1)])

    assert len(embedder.embed(["a"])) == 1
    assert len(http.posts) == 2


def test_embedder_gives_up_after_bounded_attempts(tool):
    embedder, http, _ = _client(tool, [_Response(503)] * 3, max_attempts=3)

    with pytest.raises(tool.ReembedError, match="still failing after 3 attempts"):
        embedder.embed(["a"])
    assert len(http.posts) == 3


def test_embedder_does_not_retry_a_client_error(tool):
    embedder, http, _ = _client(tool, [_Response(401), _ok(1)])

    with pytest.raises(tool.ReembedError, match="HTTP 401"):
        embedder.embed(["a"])
    assert len(http.posts) == 1


def test_embedder_fails_on_a_vector_count_mismatch(tool):
    embedder, _, _ = _client(tool, [_ok(2)])

    with pytest.raises(tool.ReembedError, match="2 vectors for 3 texts"):
        embedder.embed(["a", "b", "c"])


def test_embedder_fails_on_a_wrong_dimension(tool):
    embedder, _, _ = _client(tool, [_ok(1, dim=3584)])

    with pytest.raises(tool.ReembedError, match=r"dimension\(s\) \[3584\], expected 1024"):
        embedder.embed(["a"])


def test_embedder_paces_itself_under_the_request_budget(tool):
    now = [0.0]
    embedder, _, sleeps = _client(tool, [_ok(32), _ok(1)], max_rpm=120, clock=lambda: now[0])

    embedder.embed([str(i) for i in range(33)])

    assert sleeps == [0.5]  # 120 requests a minute: one every half second


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def test_with_vector_dim_does_not_touch_the_source_description(tool):
    source = _desc(dim=3584)

    resized = tool._with_vector_dim(source, 1024)

    assert [f["params"]["dim"] for f in resized["fields"] if f["name"] == "vector"] == [1024]
    assert [f["params"]["dim"] for f in source["fields"] if f["name"] == "vector"] == [3584]


def test_scan_fields_cover_dynamic_fields_but_no_vector(tool):
    assert tool._scalar_output_fields(_desc()) == ["_id", "text", "partition", "file_id", "created_at", "$meta"]


def test_fingerprint_ignores_the_vectors_only(tool):
    base = _row(1, "texte")

    assert tool._fingerprint(base) == tool._fingerprint({**base, "vector": [9.0], "sparse": {}})
    assert tool._fingerprint(base) != tool._fingerprint({**base, "page": 2})
