"""End-to-end tests for the wiki CLI — no LLM calls, just tool and CLI verification."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent


def run_wiki(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the wiki CLI in a subprocess."""
    return subprocess.run(
        ["uv", "run", "--project", str(PROJECT_DIR), "wiki", *args],
        capture_output=True,
        text=True,
        cwd=cwd or PROJECT_DIR,
    )


def fresh_wiki() -> Path:
    """Create a fresh temp dir and init a wiki there."""
    tmp = Path(tempfile.mkdtemp(prefix="wiki-test-"))
    run_wiki("init", cwd=tmp)
    return tmp


def test_init_creates_structure():
    tmp = Path(tempfile.mkdtemp(prefix="wiki-test-"))
    try:
        result = run_wiki("init", cwd=tmp)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        assert (tmp / "raw").is_dir()
        assert (tmp / "wiki").is_dir()
        assert (tmp / "scratch").is_dir()
        assert (tmp / "wiki" / "index.md").exists()
        assert (tmp / "wiki" / "log.md").exists()
        assert (tmp / ".gitignore").exists()

        # Verify initial commit
        log = subprocess.run(["git", "log", "--oneline"], capture_output=True, text=True, cwd=tmp)
        assert "bootstrap: initial workspace" in log.stdout

        print("✓ test_init_creates_structure")
    finally:
        shutil.rmtree(tmp)


def test_init_idempotent():
    tmp = Path(tempfile.mkdtemp(prefix="wiki-test-"))
    try:
        run_wiki("init", cwd=tmp)
        result = run_wiki("init", cwd=tmp)
        assert "Already a wiki directory" in result.stdout
        print("✓ test_init_idempotent")
    finally:
        shutil.rmtree(tmp)


def test_wiki_detection():
    tmp = Path(tempfile.mkdtemp(prefix="wiki-test-"))
    try:
        result = run_wiki("query", "test", cwd=tmp)
        assert result.returncode == 1
        assert "Not a wiki directory" in result.stderr
        print("✓ test_wiki_detection")
    finally:
        shutil.rmtree(tmp)


def test_filesystem_tools():
    tmp = fresh_wiki()
    try:
        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.tools.filesystem import read_file, write_file, edit_file, list_files, search_files

# write
result = write_file.invoke({{"path": "wiki/test-page.md", "content": "# Test\\n\\nHello world."}})
assert "Wrote" in result, f"write failed: {{result}}"

# read
result = read_file.invoke({{"path": "wiki/test-page.md"}})
assert "Hello world" in result, f"read failed: {{result}}"

# edit
result = edit_file.invoke({{"path": "wiki/test-page.md", "old_text": "Hello world.", "new_text": "Hello universe."}})
assert "Edited" in result, f"edit failed: {{result}}"

# verify
result = read_file.invoke({{"path": "wiki/test-page.md"}})
assert "Hello universe" in result

# list
result = list_files.invoke({{"directory": "wiki"}})
assert "test-page.md" in result

# search
result = search_files.invoke({{"pattern": "universe"}})
assert "universe" in result

print("✓ test_filesystem_tools")
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_DIR / "src")
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Tool test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_git_tools():
    tmp = fresh_wiki()
    try:
        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.tools.git import git_status, git_commit, git_log
from wiki.tools.filesystem import write_file

# Status should be clean after init commit
result = git_status.invoke({{}})
assert "clean" in result.lower(), f"Expected clean: {{result}}"

# Write a file and check status
write_file.invoke({{"path": "wiki/new-page.md", "content": "# New Page"}})
result = git_status.invoke({{}})
assert "new-page.md" in result, f"Expected dirty: {{result}}"

# Commit
result = git_commit.invoke({{"message": "test: add new page"}})
assert "Committed" in result, f"commit failed: {{result}}"

# Log
result = git_log.invoke({{"n": 5}})
assert "test: add new page" in result, f"log failed: {{result}}"
assert "bootstrap: initial workspace" in result

print("✓ test_git_tools")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Git tool test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_linter_middleware():
    tmp = fresh_wiki()
    try:
        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.middleware.linter import validate_index, validate_log

# Valid index
valid = "# Wiki Index\\n\\n## Concepts\\n\\n- [Test Page](test-page.md) — A test\\n"
assert validate_index(valid) is None

# Duplicate index entry
dup = "# Wiki Index\\n\\n## Concepts\\n\\n- [Test Page](test-page.md) — A test\\n- [Test Page](test-page.md) — Same\\n"
assert "Duplicate" in validate_index(dup)

# Valid log append
original = "# Wiki Log\\n\\n"
valid_log = "# Wiki Log\\n\\n## [2026-04-13] ingest | test\\n- Created pages\\n"
assert validate_log(valid_log, original) is None

# Log with no bullets
no_bullets = "# Wiki Log\\n\\n## [2026-04-13] ingest | test\\n"
assert "bullet" in validate_log(no_bullets, original).lower()

print("✓ test_linter_middleware")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Linter test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_chunking_split():
    tmp = fresh_wiki()
    try:
        # Create a long source
        long_text = "\n\n".join([f"Paragraph {i}. " + "word " * 500 for i in range(20)])
        (tmp / "raw" / "test-long.md").write_text(long_text)

        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.tools.chunking import split_source

result = split_source.invoke({{"path": "raw/test-long.md", "chunk_size": 2000}})
print(result)
assert "chunk" in result.lower(), f"Expected chunks: {{result}}"
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Split test failed: {result.stderr}"
        assert "chunk" in result.stdout.lower(), f"Expected chunks: {result.stdout}"
        print("✓ test_chunking_split")
    finally:
        shutil.rmtree(tmp)


def test_chunk_review_graph():
    """Verify the LangGraph chunk review flow groups semantically similar chunks."""
    import json
    import re

    tmp = fresh_wiki()
    try:
        source_text = (
            "# Trust One\n\n" + "trust community institution " * 120
            + "\n\n# Power\n\n" + "power hierarchy authority " * 120
            + "\n\n# Trust Two\n\n" + "trust legitimacy confidence " * 120
        )
        (tmp / "raw" / "graph-source.md").write_text(source_text, encoding="utf-8")

        script = f"""
import json
import re
import sys
sys.path.insert(0, \"{PROJECT_DIR / "src"}\")
from pathlib import Path
from wiki.ingest_graph import run_chunk_review_graph

class FakeResponse:
    def __init__(self, content: str):
        self.content = content

class FakeModel:
    def invoke(self, prompt: str):
        if \"TASK: CHUNK_SUMMARY_JSON\" in prompt:
            chunk_id = re.search(r\"chunk_id: (chunk-\\d+)\", prompt).group(1)
            text = prompt.split(\"TEXT:\\n\", 1)[1].lower()
            if \"power\" in text:
                payload = {{
                    \"summary\": \"Discussion of hierarchy and authority.\",
                    \"topics\": [\"power\", \"authority\"],
                    \"entities\": [],
                    \"claims\": [\"Power concentrates through hierarchy\"],
                    \"quotes\": [],
                    \"mixed_topics\": False,
                    \"split_recommendation\": \"keep\",
                    \"confidence\": 0.9,
                }}
            else:
                payload = {{
                    \"summary\": \"Discussion of institutional trust and legitimacy.\",
                    \"topics\": [\"trust\", \"legitimacy\"],
                    \"entities\": [],
                    \"claims\": [\"Trust is built socially\"],
                    \"quotes\": [],
                    \"mixed_topics\": False,
                    \"split_recommendation\": \"keep\",
                    \"confidence\": 0.92,
                }}
            payload[\"chunk_id\"] = chunk_id
            return FakeResponse(json.dumps(payload))

        if \"TASK: GROUP_REVIEW_JSON\" in prompt:
            payload = {{
                \"decision\": \"accept\",
                \"review_notes\": [\"Trust sections form one theme across distant chunks.\"],
                \"groups\": [
                    {{
                        \"title_hint\": \"institutional trust\",
                        \"chunk_ids\": [\"chunk-001\", \"chunk-003\"],
                        \"rationale\": \"Both chunks discuss trust and legitimacy.\",
                        \"confidence\": 0.94,
                    }},
                    {{
                        \"title_hint\": \"authority structures\",
                        \"chunk_ids\": [\"chunk-002\"],
                        \"rationale\": \"This chunk is a standalone discussion of power.\",
                        \"confidence\": 0.9,
                    }},
                ],
                \"retry_reason\": None,
                \"focus_chunk_ids\": [],
            }}
            return FakeResponse(json.dumps(payload))

        if \"TASK: SYNTHESIZE_GROUP_PAGE\" in prompt:
            title = re.search(r\"title_hint: (.+)\", prompt).group(1).strip()
            return FakeResponse(
                f\"# {{title.title()}}\\n\\n## Context\\n\\nDrafted from grouped chunks.\\n\\n## Analysis\\n\\nSynthesized content.\\n\\n## Source references\\n\\n- grouped chunks\\n\"
            )

        raise AssertionError(f\"Unexpected prompt: {{prompt[:120]}}\")

class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lower = text.lower()
            if \"power\" in lower:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([1.0, 0.0, 0.0])
        return vectors

result = run_chunk_review_graph(
    path=\"raw/graph-source.md\",
    chunk_size=120,
    max_retries=1,
    model=FakeModel(),
    embeddings=FakeEmbeddings(),
)

assert result.chunk_count >= 3, result
assert len(result.draft_paths) == 2, result
assert any(path.endswith(\"institutional-trust.md\") for path in result.draft_paths), result.draft_paths
assert any(path.endswith(\"authority-structures.md\") for path in result.draft_paths), result.draft_paths
assert Path(result.artifact_dir, \"review.json\").exists()
assert Path(result.artifact_dir, \"candidate-groups.json\").exists()
print(\"✓ test_chunk_review_graph\")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Chunk review graph test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_chunk_review_graph_observability():
    """Verify chunk review graph logs every model call and embedding call to SQLite."""
    import json
    import re
    import sqlite3

    tmp = fresh_wiki()
    try:
        source_text = (
            "# Trust\n\n" + "trust community " * 80
            + "\n\n# Power\n\n" + "power authority " * 80
        )
        (tmp / "raw" / "obs-source.md").write_text(source_text, encoding="utf-8")

        script = f"""
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, \"{PROJECT_DIR / "src"}\")
from wiki.ingest_graph import run_chunk_review_graph
from wiki.observability import ObsStore

class FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.additional_kwargs = {{}}
        self.usage_metadata = {{"input_tokens": 10, "output_tokens": 5}}

class FakeModel:
    def invoke(self, prompt: str):
        if \"TASK: CHUNK_SUMMARY_JSON\" in prompt:
            chunk_id = re.search(r\"chunk_id: (chunk-\\d+)\", prompt).group(1)
            text = prompt.split(\"TEXT:\\n\", 1)[1].lower()
            if \"power\" in text:
                payload = {{
                    \"summary\": \"About power.\",
                    \"topics\": [\"power\"],
                    \"entities\": [],
                    \"claims\": [],
                    \"quotes\": [],
                    \"mixed_topics\": False,
                    \"split_recommendation\": \"keep\",
                    \"confidence\": 0.9,
                }}
            else:
                payload = {{
                    \"summary\": \"About trust.\",
                    \"topics\": [\"trust\"],
                    \"entities\": [],
                    \"claims\": [],
                    \"quotes\": [],
                    \"mixed_topics\": False,
                    \"split_recommendation\": \"keep\",
                    \"confidence\": 0.9,
                }}
            payload[\"chunk_id\"] = chunk_id
            return FakeResponse(json.dumps(payload))

        if \"TASK: GROUP_REVIEW_JSON\" in prompt:
            return FakeResponse(json.dumps({{
                \"decision\": \"accept\",
                \"review_notes\": [\"Looks good.\"],
                \"groups\": [
                    {{\"title_hint\": \"trust\", \"chunk_ids\": [\"chunk-001\"], \"rationale\": \"Trust.\", \"confidence\": 0.9}},
                ],
                \"retry_reason\": None,
                \"focus_chunk_ids\": [],
            }}))

        if \"TASK: SYNTHESIZE_GROUP_PAGE\" in prompt:
            title = re.search(r\"title_hint: (.+)\", prompt).group(1).strip()
            return FakeResponse(f\"# {{title.title()}}\\n\\nDraft page.\\n\")

        raise AssertionError(f\"Unexpected prompt\")

class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]] * len(texts)

# Set up obs store in a temp file
db_path = Path(\"{tmp}/.wiki/obs.db\")
obs = ObsStore(db_path)

result = run_chunk_review_graph(
    path=\"raw/obs-source.md\",
    chunk_size=80,
    max_retries=0,
    model=FakeModel(),
    embeddings=FakeEmbeddings(),
    obs_store=obs,
    run_id=\"test-obs-run-123\",
)
obs.close()

# Verify obs tables
conn = sqlite3.connect(str(db_path))

runs = conn.execute(\"SELECT id, command FROM obs_runs\").fetchall()
assert len(runs) == 1
assert runs[0][0] == \"test-obs-run-123\"
assert runs[0][1] == \"chunk-review\"

model_calls = conn.execute(\"SELECT turn, response FROM obs_model_calls ORDER BY turn\").fetchall()
assert len(model_calls) >= 3, f\"Expected >= 3 model calls, got {{len(model_calls)}}\"

tool_calls = conn.execute(\"SELECT tool_name FROM obs_tool_calls\").fetchall()
assert any(tc[0] == \"embed_documents\" for tc in tool_calls), f\"Expected embed_documents tool call, got: {{tool_calls}}\"

messages = conn.execute(\"SELECT role FROM obs_messages\").fetchall()
roles = [m[0] for m in messages]
# Should have user + assistant pairs for each model call
assert \"user\" in roles
assert \"assistant\" in roles

conn.close()
print(\"✓ test_chunk_review_graph_observability\")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Obs test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_agent_construction():
    """Verify the agent can be constructed without errors."""
    tmp = fresh_wiki()
    try:
        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.agent import create_wiki_agent, get_all_tools

tools = get_all_tools()
assert len(tools) == 11, f"Expected 11 tools, got {{len(tools)}}"

# Verify all tools have names
for t in tools:
    assert t.name, f"Tool missing name: {{t}}"

tool_names = [t.name for t in tools]
assert "read_file" in tool_names
assert "search_wiki" in tool_names
assert "split_source" in tool_names
assert "review_long_source" in tool_names
assert "git_commit" in tool_names

print("✓ test_agent_construction")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Agent construction test failed: {result.stderr}"
        print(result.stdout.strip())
    finally:
        shutil.rmtree(tmp)


def test_observability_store():
    """Verify ObsStore creates tables and inserts records."""
    import tempfile
    from wiki.observability import ObsStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / ".wiki" / "obs.db"
        store = ObsStore(db_path)

        # Insert a run
        store.insert_run(run_id="test-run", thread_id="t1", command="chat", model="gpt-5.4-mini", reasoning_effort="xhigh")

        # Insert a model call
        store.insert_model_call(
            run_id="test-run",
            turn=1,
            system_msg="You are a wiki agent.",
            messages_in=[{"role": "user", "content": "hello"}],
            tools_available=["read_file", "write_file"],
            response="Hi there!",
            reasoning="User said hello, I should respond.",
            tool_calls=[{"name": "read_file", "args": {"path": "wiki/index.md"}, "id": "tc1"}],
            usage={"input_tokens": 10, "output_tokens": 5},
            duration_ms=1234,
        )

        # Insert a tool call
        store.insert_tool_call(
            run_id="test-run",
            turn=1,
            tool_call_id="tc1",
            tool_name="read_file",
            arguments={"path": "wiki/index.md"},
            result="# Wiki Index",
            duration_ms=50,
        )

        # Insert a message
        store.insert_message(run_id="test-run", role="user", content="hello")
        store.insert_message(run_id="test-run", role="assistant", content="Hi there!")

        store.close()

        # Verify with raw SQL
        import sqlite3
        conn = sqlite3.connect(str(db_path))

        runs = conn.execute("SELECT * FROM obs_runs").fetchall()
        assert len(runs) == 1
        assert runs[0][0] == "test-run"

        model_calls = conn.execute("SELECT * FROM obs_model_calls").fetchall()
        assert len(model_calls) == 1
        assert model_calls[0][7] == "Hi there!"  # response
        assert model_calls[0][8] == "User said hello, I should respond."  # reasoning
        assert model_calls[0][11] == 1234  # duration_ms

        tool_calls = conn.execute("SELECT * FROM obs_tool_calls").fetchall()
        assert len(tool_calls) == 1
        assert tool_calls[0][4] == "read_file"  # tool_name
        assert tool_calls[0][-2] == 50  # duration_ms

        messages = conn.execute("SELECT * FROM obs_messages ORDER BY id").fetchall()
        assert len(messages) == 2
        assert messages[0][2] == "user"
        assert messages[1][2] == "assistant"

        conn.close()
        print("✓ test_observability_store")


def test_observability_init_run():
    """Verify init_run creates the DB and a run record."""
    import tempfile
    from wiki.observability import init_run

    with tempfile.TemporaryDirectory() as tmp:
        # Monkey-patch validate_wiki_dir and get_obs_db_path
        import wiki.observability as obs_mod
        original_fn = obs_mod.get_obs_db_path

        def mock_get_obs_db_path(cwd=None):
            p = Path(tmp) / ".wiki" / "obs.db"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

        obs_mod.get_obs_db_path = mock_get_obs_db_path
        try:
            store, run_id = init_run("ingest", "thread-123")
            assert len(run_id) == 32  # uuid hex

            # Verify run was inserted
            import sqlite3
            conn = sqlite3.connect(str(mock_get_obs_db_path()))
            runs = conn.execute("SELECT command, thread_id FROM obs_runs").fetchall()
            assert len(runs) == 1
            assert runs[0][0] == "ingest"
            assert runs[0][1] == "thread-123"
            conn.close()

            store.close()
            print("✓ test_observability_init_run")
        finally:
            obs_mod.get_obs_db_path = original_fn


def test_observable_embeddings():
    """Verify ObservableEmbeddings logs embed_documents and embed_query to SQLite."""
    import sqlite3
    import tempfile
    from wiki.observability import ObsStore, ObservableEmbeddings

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "obs.db"
        store = ObsStore(db_path)
        store.insert_run(run_id="emb-test", thread_id="t1", command="test", model="embed", reasoning_effort=None)

        class FakeInner:
            def embed_documents(self, texts):
                return [[1.0, 0.0]] * len(texts)
            def embed_query(self, text):
                return [0.5, 0.5]

        obs_emb = ObservableEmbeddings(FakeInner(), obs_store=store, run_id="emb-test")

        # embed_documents
        vecs = obs_emb.embed_documents(["hello", "world"])
        assert len(vecs) == 2
        assert vecs[0] == [1.0, 0.0]

        # embed_query
        qvec = obs_emb.embed_query("test query")
        assert qvec == [0.5, 0.5]

        store.close()

        # Verify DB
        conn = sqlite3.connect(str(db_path))
        tool_calls = conn.execute("SELECT tool_name, arguments, duration_ms FROM obs_tool_calls ORDER BY id").fetchall()
        assert len(tool_calls) == 2
        assert tool_calls[0][0] == "embed_documents"
        assert tool_calls[1][0] == "embed_query"
        conn.close()
        print("✓ test_observable_embeddings")


def test_observable_embeddings_passthrough():
    """ObservableEmbeddings with no obs_store should pass through transparently."""
    from wiki.observability import ObservableEmbeddings

    class FakeInner:
        def embed_documents(self, texts):
            return [[1.0]] * len(texts)
        def embed_query(self, text):
            return [0.5]
        custom_attr = "present"

    obs_emb = ObservableEmbeddings(FakeInner())
    assert obs_emb.embed_documents(["a"]) == [[1.0]]
    assert obs_emb.embed_query("q") == [0.5]
    assert obs_emb.custom_attr == "present"
    print("✓ test_observable_embeddings_passthrough")


def test_reindex_observability():
    """Verify wiki reindex logs embedding calls to SQLite."""
    import sqlite3

    tmp = fresh_wiki()
    try:
        # Create some wiki pages to index
        wiki_dir = tmp / "wiki"
        (wiki_dir / "trust.md").write_text("# Trust\nTrust is important.", encoding="utf-8")
        (wiki_dir / "power.md").write_text("# Power\nPower dynamics.", encoding="utf-8")

        script = f"""
import sys
sys.path.insert(0, \"{PROJECT_DIR / "src"}\")
from wiki.observability import init_run, ObsStore, ObservableEmbeddings
from wiki.rag.chroma_store import reindex_all
from pathlib import Path
import unittest.mock as mock

# Fake embeddings so we don't need a real API key
class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[1.0, 0.0]] * len(texts)
    def embed_query(self, text):
        return [0.5, 0.5]

fake = FakeEmbeddings()
with mock.patch(\"wiki.rag.chroma_store.build_embeddings\", return_value=fake):
    store, run_id = init_run(\"reindex\", \"test-reindex\")
    count = reindex_all(obs_store=store, run_id=run_id)
    store.close()
print(f\"indexed={{count}} run={{run_id}}\")
"""
        result = subprocess.run(
            ["uv", "run", "--project", str(PROJECT_DIR), "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        assert result.returncode == 0, f"Reindex failed: {result.stderr}"
        assert "indexed=2" in result.stdout

        # Check obs DB
        db_path = tmp / ".wiki" / "obs.db"
        assert db_path.exists(), "obs.db should exist after reindex"
        conn = sqlite3.connect(str(db_path))

        runs = conn.execute("SELECT command FROM obs_runs").fetchall()
        assert any(r[0] == "reindex" for r in runs)

        tool_calls = conn.execute("SELECT tool_name FROM obs_tool_calls").fetchall()
        assert any(tc[0] == "embed_documents" for tc in tool_calls), f"Expected embed_documents, got: {tool_calls}"

        conn.close()
        print("✓ test_reindex_observability")
    finally:
        shutil.rmtree(tmp)


def test_persistent_checkpointer_roundtrip():
    """Verify persistent checkpoints survive process-like reopen."""
    import tempfile

    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    from wiki.checkpointing import PersistentCheckpointer

    class State(TypedDict):
        value: str

    def respond(state: State) -> dict:
        return {"value": state["value"] + "!"}

    def build_graph(checkpointer):
        builder = StateGraph(State)
        builder.add_node("respond", respond)
        builder.add_edge(START, "respond")
        builder.add_edge("respond", END)
        return builder.compile(checkpointer=checkpointer)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / ".wiki" / "checkpoints.sqlite"
        config = {"configurable": {"thread_id": "telegram:1:epoch:1"}}

        manager = PersistentCheckpointer(db_path)
        graph = build_graph(manager.saver)
        graph.invoke({"value": "ping"}, config)
        manager.close()

        manager = PersistentCheckpointer(db_path)
        graph = build_graph(manager.saver)
        state = graph.get_state(config)
        manager.close()

        assert state.values["value"] == "ping!"
        print("✓ test_persistent_checkpointer_roundtrip")


def test_telegram_state_store_and_rotation():
    """Verify Telegram state storage tracks cursors, sessions, epochs, and events."""
    import sqlite3
    import tempfile

    from wiki.telegram_state import TelegramStateStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / ".wiki" / "telegram.db"
        store = TelegramStateStore(db_path)

        assert store.get_cursor("bot") is None
        store.set_cursor("bot", 42)
        assert store.get_cursor("bot") == 42

        session = store.get_or_create_session(chat_id=123, chat_type="private", user_id=456)
        assert session.active_epoch == 1
        assert session.active_thread_id == "telegram:123:epoch:1"

        store.record_event(
            session=session,
            role="user",
            content="hello",
            telegram_update_id=1,
            telegram_message_id=2,
        )

        rotated = store.rotate_session(123, reason="manual-reset")
        assert rotated.active_epoch == 2
        assert rotated.active_thread_id == "telegram:123:epoch:2"

        store.close()

        conn = sqlite3.connect(str(db_path))
        epochs = conn.execute(
            "SELECT epoch, thread_id, close_reason FROM telegram_epochs ORDER BY epoch"
        ).fetchall()
        events = conn.execute(
            "SELECT role, content FROM telegram_events ORDER BY id"
        ).fetchall()
        conn.close()

        assert epochs == [
            (1, "telegram:123:epoch:1", "manual-reset"),
            (2, "telegram:123:epoch:2", None),
        ]
        assert events == [("user", "hello")]
        print("✓ test_telegram_state_store_and_rotation")


def test_dotenv_loading():
    """Verify .wiki/.env loads correctly via python-dotenv."""
    import os
    from pathlib import Path
    import tempfile

    from wiki.config import _load_dotenv_once

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp) / ".wiki"
        wiki_dir.mkdir()
        env_file = wiki_dir / ".env"
        env_file.write_text(
            "# Bot tokens\n"
            "TELEGRAM_BOT_TOKEN=123456:ABC-DEF\n"
            '\n'
            'POE_API_KEY="sk-quoted-key"\n'
            "OPENROUTER_API_KEY=or-bare-key\n"
        )

        # Patch cwd so config finds .wiki/.env
        import wiki.config
        wiki.config.set_wiki_root(Path(tmp))
        wiki.config._DOTENV_LOADED = False

        try:
            _load_dotenv_once()
            assert os.environ["TELEGRAM_BOT_TOKEN"] == "123456:ABC-DEF"
            assert os.environ["POE_API_KEY"] == "sk-quoted-key"
            assert os.environ["OPENROUTER_API_KEY"] == "or-bare-key"
            print("✓ test_dotenv_loading")
        finally:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("POE_API_KEY", None)
            os.environ.pop("OPENROUTER_API_KEY", None)
            wiki.config._wiki_root = None


def _reset_dotenv():
    """Reset the dotenv loaded flag so tests re-read the file."""
    import wiki.config as cfg
    cfg._DOTENV_LOADED = False


def test_dotenv_populates_os_environ():
    """Verify .wiki/.env is loaded into os.environ on demand."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        env_file = wiki_dir / ".wiki" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("TELEGRAM_BOT_TOKEN=file-token\nPOE_API_KEY=file-key\n")

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()
                from wiki.config import _load_dotenv_once
                _load_dotenv_once()

                assert os.environ["TELEGRAM_BOT_TOKEN"] == "file-token"
                assert os.environ["POE_API_KEY"] == "file-key"
                print("✓ test_dotenv_populates_os_environ")


def test_dotenv_clobbers_existing():
    """Verify .wiki/.env values override existing env vars (file wins)."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        env_file = wiki_dir / ".wiki" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("TELEGRAM_BOT_TOKEN=from-file\n")

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "from-shell"}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()
                from wiki.config import _load_dotenv_once
                _load_dotenv_once()

                assert os.environ["TELEGRAM_BOT_TOKEN"] == "from-file"
                print("✓ test_dotenv_clobbers_existing")


def test_dotenv_no_file_is_noop():
    """Verify dotenv loading is a no-op when .wiki/.env doesn't exist."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()
                from wiki.config import _load_dotenv_once
                _load_dotenv_once()  # should not raise

                assert "TELEGRAM_BOT_TOKEN" not in os.environ
                print("✓ test_dotenv_no_file_is_noop")


def test_require_telegram_bot_token_from_file():
    """Verify require_telegram_bot_token reads from .wiki/.env."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import require_telegram_bot_token

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        env_file = wiki_dir / ".wiki" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("TELEGRAM_BOT_TOKEN=tok-from-file\n")

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()

                token = require_telegram_bot_token()
                assert token == "tok-from-file"
                print("✓ test_require_telegram_bot_token_from_file")


def test_require_telegram_bot_token_from_env_fallback():
    """Verify TELEGRAM_BOT_TOKEN env var works when no .env file exists."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import require_telegram_bot_token

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok-from-env"}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()

                token = require_telegram_bot_token()
                assert token == "tok-from-env"
                print("✓ test_require_telegram_bot_token_from_env_fallback")


def test_require_telegram_bot_token_missing_exits():
    """Verify require_telegram_bot_token exits when token is nowhere."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import require_telegram_bot_token

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.get_wiki_root", return_value=wiki_dir):
                _reset_dotenv()

                try:
                    require_telegram_bot_token()
                    assert False, "Should have raised SystemExit"
                except SystemExit as exc:
                    assert exc.code == 1
                    print("✓ test_require_telegram_bot_token_missing_exits")


def test_slash_commands_help_and_unknown():
    """Verify shared slash command help/unknown handling across transports."""
    import tempfile

    from wiki.slash_commands import SlashCommandContext, build_chat_slash_registry, build_telegram_slash_registry

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        (wiki_dir / "raw").mkdir()
        (wiki_dir / "wiki").mkdir()
        (wiki_dir / "scratch").mkdir()

        chat_registry = build_chat_slash_registry()
        chat_ctx = SlashCommandContext(
            transport="chat",
            wiki_dir=wiki_dir,
            thread_id="chat-thread-1",
            model_name="gpt-5.4-mini",
            chat_base_url="https://api.poe.com/v1",
            reasoning_effort="low",
            use_responses_api=False,
            help_footer="Type normal text to chat with the wiki agent.",
        )

        help_result = chat_registry.dispatch("/help", chat_ctx)
        assert help_result is not None
        assert "/help" in help_result.reply
        assert "/new" in help_result.reply
        assert "/exit" in help_result.reply
        assert "Type normal text" in help_result.reply

        unknown_result = chat_registry.dispatch("/wat", chat_ctx)
        assert unknown_result is not None
        assert unknown_result.error is True
        assert "Unknown command '/wat'" in unknown_result.reply

        telegram_registry = build_telegram_slash_registry()
        telegram_ctx = SlashCommandContext(
            transport="telegram",
            wiki_dir=wiki_dir,
            thread_id="telegram:1:epoch:1",
            model_name="gpt-5.4-mini",
            chat_base_url="https://api.poe.com/v1",
            reasoning_effort="low",
            use_responses_api=False,
            help_footer="Files → ingest into the wiki.",
        )
        start_result = telegram_registry.dispatch("/start@MyWikiBot", telegram_ctx)
        assert start_result is not None
        assert "/exit" not in start_result.reply
        assert "Files → ingest" in start_result.reply
        print("✓ test_slash_commands_help_and_unknown")


def test_slash_commands_status():
    """Verify slash status summarizes the current wiki/session state."""
    from wiki.slash_commands import SlashCommandContext, build_shared_slash_registry

    tmp = fresh_wiki()
    try:
        (tmp / "wiki" / "trust.md").write_text("# Trust\n\nTrust matters.", encoding="utf-8")
        (tmp / "raw" / "notes.md").write_text("source text", encoding="utf-8")
        (tmp / "scratch" / "work.txt").write_text("temp", encoding="utf-8")
        (tmp / "wiki" / ".chroma").mkdir(parents=True, exist_ok=True)

        registry = build_shared_slash_registry()
        result = registry.dispatch(
            "/status",
            SlashCommandContext(
                transport="telegram",
                wiki_dir=tmp,
                thread_id="telegram:123:epoch:4",
                model_name="gpt-5.4-mini",
                chat_base_url="https://api.poe.com/v1",
                reasoning_effort="low",
                use_responses_api=False,
                session_id="telegram-private-123",
                active_epoch=4,
            ),
        )

        assert result is not None
        assert "Session: telegram-private-123" in result.reply
        assert "Epoch: 4" in result.reply
        assert "Thread: telegram:123:epoch:4" in result.reply
        assert "Pages: 1" in result.reply
        assert "Raw sources: 1" in result.reply
        assert "Scratch files: 1" in result.reply
        assert "Chroma index: present" in result.reply
        assert "Git: dirty" in result.reply
        print("✓ test_slash_commands_status")
    finally:
        shutil.rmtree(tmp)


def test_telegram_handle_update_slash_new():
    """Verify Telegram slash commands use the shared registry and rotate the session."""
    import os
    import tempfile
    from unittest.mock import MagicMock, patch

    from wiki.telegram_state import TelegramSession

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        (wiki_dir / "raw").mkdir()
        (wiki_dir / "wiki").mkdir()
        (wiki_dir / "scratch").mkdir()

        client = MagicMock()
        state_store = MagicMock()
        session = TelegramSession(
            session_id="telegram-private-42",
            chat_id=42,
            chat_type="private",
            user_id=7,
            active_epoch=1,
            active_thread_id="telegram:42:epoch:1",
        )
        rotated = TelegramSession(
            session_id="telegram-private-42",
            chat_id=42,
            chat_type="private",
            user_id=7,
            active_epoch=2,
            active_thread_id="telegram:42:epoch:2",
        )
        state_store.get_or_create_session.return_value = session
        state_store.rotate_session.return_value = rotated

        update = {
            "update_id": 999,
            "message": {
                "message_id": 123,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7},
                "text": "/new",
            },
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.commands.telegram._run_agent_turn") as mock_turn:
                from wiki.commands.telegram import _handle_update

                _handle_update(update, client, state_store, MagicMock(), MagicMock())

                mock_turn.assert_not_called()
                state_store.rotate_session.assert_called_once_with(42, reason="slash-command")
                sent = client.send_messages.call_args[0][1]
                assert "Started a fresh conversation thread" in sent
                assert "Epoch: 2" in sent
                assert "Thread: telegram:42:epoch:2" in sent
                print("✓ test_telegram_handle_update_slash_new")


def test_split_telegram_text():
    """Verify Telegram replies are chunked safely."""
    from wiki.telegram_client import split_telegram_text

    text = ("hello world\n" * 500).strip()
    chunks = split_telegram_text(text, limit=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)
    print("✓ test_split_telegram_text")


def test_telegram_download_file():
    """Verify TelegramClient.download_file writes the response body to disk."""
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from wiki.telegram_client import TelegramClient

    client = TelegramClient("fake-token")

    # Mock _request to return a file_path
    mock_result = {"file_path": "documents/abc.txt"}
    client._request = MagicMock(return_value=mock_result)  # type: ignore[method-assign]

    # Mock urlopen to return bytes
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"file contents here"
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "test.txt"
        with patch("wiki.telegram_client.request.urlopen", return_value=mock_resp):
            result = client.download_file("file-id-123", dest)

        assert result == dest
        assert dest.read_text() == "file contents here"
        print("✓ test_telegram_download_file")


def test_build_ingest_prompt():
    """Verify _build_short_prompt and _build_long_prompt generate the right prompts."""
    from wiki.commands.ingest import _build_short_prompt, _build_long_prompt
    from wiki.ingest_graph import ChunkReviewResult

    short = _build_short_prompt("raw/notes.md", "Hello world this is a note.", 5)
    assert "raw/notes.md" in short
    assert "5 words" in short
    assert "short enough to process directly" in short
    assert "Hello world this is a note" in short

    # Long prompt uses a pipeline result object
    result = ChunkReviewResult(
        source_path="raw/book.md",
        attempt=1,
        final_chunk_size=1500,
        chunk_count=42,
        decision="accept",
        artifact_dir="scratch/book/chunk-review/attempt-01",
        review_notes=["Groups look coherent."],
        draft_paths=["scratch/book/chunk-review/attempt-01/drafts/ch1.md"],
        group_titles=["chapter-1"],
    )
    long = _build_long_prompt("raw/book.md", result)
    assert "raw/book.md" in long
    assert "42" in long
    assert "chunk-review pipeline" in long
    assert "Draft Pages" in long
    assert "Draft file not found" in long  # path doesn't exist on disk

    # Test with a real draft file on disk
    tmp = Path(tempfile.mkdtemp(prefix="wiki-draft-test-"))
    try:
        draft_dir = tmp / "scratch" / "book" / "chunk-review" / "attempt-01" / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "ch1.md").write_text("# Chapter 1\n\nDraft content here.", encoding="utf-8")

        result_with_drafts = ChunkReviewResult(
            source_path="raw/book.md",
            attempt=1,
            final_chunk_size=1500,
            chunk_count=42,
            decision="accept",
            artifact_dir=str(tmp / "scratch" / "book" / "chunk-review" / "attempt-01"),
            review_notes=["Groups look coherent."],
            draft_paths=[str(draft_dir / "ch1.md")],
            group_titles=["chapter-1"],
        )
        long_with_files = _build_long_prompt("raw/book.md", result_with_drafts)
        assert "Draft content here" in long_with_files
    finally:
        shutil.rmtree(tmp)

    print("✓ test_build_ingest_prompt")


def test_handle_attachment_downloads_and_ingests():
    """Verify _handle_attachment downloads file and runs ingest turn."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki = Path(tmp)
        (wiki / "raw").mkdir()
        (wiki / "wiki").mkdir()
        (wiki / "scratch").mkdir()

        # Create a source file that download_file would write
        source_content = "# Test Source\n\nSome interesting content about things."

        mock_client = MagicMock()
        def fake_download(file_id, dest):
            dest.write_text(source_content, encoding="utf-8")
            return dest
        mock_client.download_file.side_effect = fake_download
        sent: list[str] = []
        mock_client.send_messages.side_effect = lambda cid, txt: sent.append(txt)

        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_session.active_thread_id = "telegram:42:epoch:1"

        mock_checkpointer = MagicMock()
        mock_model = MagicMock()

        # Patch cwd to our temp wiki
        with patch.dict(os.environ, {}, clear=True):
            import wiki.config as _wc
            _wc.set_wiki_root(wiki)
            try:
                with patch("wiki.commands.telegram._run_ingest_turn", return_value="Plan: create 2 pages.") as mock_ingest:
                    from wiki.commands.telegram import _handle_attachment

                    _handle_attachment(
                        message={"chat": {"id": 42}, "update_id": 99, "message_id": 100},
                        document={"file_id": "abc123", "file_name": "test-notes.md"},
                        photos=None,
                        caption="Please focus on the key arguments",
                        client=mock_client,
                        state_store=mock_store,
                        checkpointer=mock_checkpointer,
                        model=mock_model,
                        session=mock_session,
                    )

                    # File was downloaded
                    assert (wiki / "raw" / "test-notes.md").read_text() == source_content

                    # Ingest turn was called with prompt mentioning the file + caption
                    call_prompt = mock_ingest.call_args[1]["prompt"]
                    assert "raw/test-notes.md" in call_prompt
                    assert "key arguments" in call_prompt

                    # Confirmation message was sent
                    assert any("test-notes.md" in s for s in sent)
                    assert any("Plan: create 2 pages." in s for s in sent)

                    print("✓ test_handle_attachment_downloads_and_ingests")
            finally:
                _wc._wiki_root = None


def test_handle_attachment_binary_file_rejected():
    """Verify binary files get a graceful rejection message."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki = Path(tmp)
        (wiki / "raw").mkdir()
        (wiki / "wiki").mkdir()
        (wiki / "scratch").mkdir()

        mock_client = MagicMock()
        def fake_download(file_id, dest):
            dest.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG header
            return dest
        mock_client.download_file.side_effect = fake_download
        sent: list[str] = []
        mock_client.send_messages.side_effect = lambda cid, txt: sent.append(txt)

        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_checkpointer = MagicMock()
        mock_model = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            import wiki.config as _wc
            _wc.set_wiki_root(wiki)
            try:
                from wiki.commands.telegram import _handle_attachment

                _handle_attachment(
                    message={"chat": {"id": 42}, "update_id": 99, "message_id": 100},
                    document={"file_id": "abc123", "file_name": "photo.png"},
                    photos=None,
                    caption="",
                    client=mock_client,
                    state_store=mock_store,
                    checkpointer=mock_checkpointer,
                    model=mock_model,
                    session=mock_session,
                )

                # Should get a rejection about non-text file
                assert any("not a text file" in s.lower() or "non-text" in s.lower() for s in sent)
                print("✓ test_handle_attachment_binary_file_rejected")
            finally:
                _wc._wiki_root = None


def test_handle_attachment_mixed_files():
    """Verify mixed text+binary: text files ingested, binary skipped."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        wiki = Path(tmp)
        (wiki / "raw").mkdir()
        (wiki / "wiki").mkdir()
        (wiki / "scratch").mkdir()

        mock_client = MagicMock()
        text_content = "# Notes\n\nSome text content."

        # Document download returns text, photo download returns binary
        def fake_download(file_id, dest):
            if file_id == "doc-id":
                dest.write_text(text_content, encoding="utf-8")
            else:
                dest.write_bytes(b"\x89PNG\r\n\x1a\n")
            return dest
        mock_client.download_file.side_effect = fake_download
        sent: list[str] = []
        mock_client.send_messages.side_effect = lambda cid, txt: sent.append(txt)

        mock_store = MagicMock()
        mock_session = MagicMock()
        mock_session.active_thread_id = "telegram:42:epoch:1"
        mock_checkpointer = MagicMock()
        mock_model = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            import wiki.config as _wc
            _wc.set_wiki_root(wiki)
            try:
                with patch("wiki.commands.telegram._run_ingest_turn", return_value="Plan: 1 page.") as mock_ingest:
                    from wiki.commands.telegram import _handle_attachment

                    # Message with both a text document and a photo
                    _handle_attachment(
                        message={"chat": {"id": 42}, "update_id": 99, "message_id": 100},
                        document={"file_id": "doc-id", "file_name": "notes.md"},
                        photos=[{"file_id": "photo-id", "file_size": 1000}],
                        caption="",
                        client=mock_client,
                        state_store=mock_store,
                        checkpointer=mock_checkpointer,
                        model=mock_model,
                        session=mock_session,
                    )

                    # Ingest was called (text document was valid)
                    mock_ingest.assert_called_once()
                    call_prompt = mock_ingest.call_args[1]["prompt"]
                    # Only the text file should appear in the prompt
                    assert "notes.md" in call_prompt
                    assert "photo_" not in call_prompt
                    # Binary was skipped — rejection message sent
                    assert any("non-text" in s.lower() for s in sent)
                    print("✓ test_handle_attachment_mixed_files")
            finally:
                _wc._wiki_root = None


def test_agent_invoke_with_mock_model():
    """Verify create_wiki_agent returns a callable graph that processes a message."""
    from unittest.mock import MagicMock, PropertyMock

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    tmp = fresh_wiki()
    try:
        # FakeChatModel that returns a fixed response regardless of input.
        # Must support bind_tools() (returns self) and invoke() (returns AIMessage).
        class FakeChatModel(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "fake"

            def _generate(self, messages, *, stop=None, run_manager=None, **kwargs):
                from langchain_core.outputs import ChatGeneration, ChatResult
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="I read the wiki. Looks good!"))])

            def bind_tools(self, tools, **kwargs):
                return self

        model = FakeChatModel()

        from wiki.agent import create_wiki_agent

        agent = create_wiki_agent(model=model)

        result = agent.invoke({"messages": [HumanMessage(content="Read wiki/index.md and summarize it.")]})

        # Result should contain messages
        assert "messages" in result
        messages = result["messages"]
        assert len(messages) >= 2, f"Expected >= 2 messages (in + out), got {len(messages)}"

        # First message should be our input
        assert isinstance(messages[0], HumanMessage)

        # The model should have produced an AIMessage
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        assert len(ai_messages) >= 1, "Expected at least one AIMessage in output"

        # The fake model's response should appear in the output
        assert any("Looks good" in m.content for m in ai_messages if isinstance(m.content, str))

        print("✓ test_agent_invoke_with_mock_model")
    finally:
        shutil.rmtree(tmp)


