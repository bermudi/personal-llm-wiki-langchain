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


def test_agent_construction():
    """Verify the agent can be constructed without errors."""
    tmp = fresh_wiki()
    try:
        script = f"""
import sys
sys.path.insert(0, "{PROJECT_DIR / "src"}")
from wiki.agent import create_wiki_agent, get_all_tools

tools = get_all_tools()
assert len(tools) == 13, f"Expected 13 tools, got {{len(tools)}}"

# Verify all tools have names
for t in tools:
    assert t.name, f"Tool missing name: {{t}}"

tool_names = [t.name for t in tools]
assert "read_file" in tool_names
assert "search_wiki" in tool_names
assert "split_source" in tool_names
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


def test_parse_dotenv():
    """Verify _parse_dotenv handles KEY=VALUE, comments, quotes, export prefix."""
    from pathlib import Path
    import tempfile

    from wiki.config import _parse_dotenv

    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "secrets.env"
        env_file.write_text(
            "# Bot tokens\n"
            "TELEGRAM_BOT_TOKEN=123456:ABC-DEF\n"
            '\n'
            'POE_API_KEY="sk-quoted-key"\n'
            "export OPENROUTER_API_KEY='or-single-quotes'\n"
            "BARE_VALUE=no-quotes\n"
            "  SPACED_KEY  =  spaced-value  \n"
            "INVALID_LINE_NO_EQUALS\n"
        )

        result = _parse_dotenv(env_file)

        assert result["TELEGRAM_BOT_TOKEN"] == "123456:ABC-DEF"
        assert result["POE_API_KEY"] == "sk-quoted-key"
        assert result["OPENROUTER_API_KEY"] == "or-single-quotes"
        assert result["BARE_VALUE"] == "no-quotes"
        assert result["SPACED_KEY"] == "spaced-value"
        assert "INVALID_LINE_NO_EQUALS" not in result
        assert "" not in result  # blank lines skipped
        print("✓ test_parse_dotenv")


def test_load_secrets_env_populates_os_environ():
    """Verify .wiki/secrets.env is loaded into os.environ on demand."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import load_secrets_env

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        secrets = wiki_dir / ".wiki" / "secrets.env"
        secrets.parent.mkdir(parents=True, exist_ok=True)
        secrets.write_text("TELEGRAM_BOT_TOKEN=file-token\nPOE_API_KEY=file-key\n")

        # Remove from env to ensure clean state
        with patch.dict(os.environ, {}, clear=True):
            # Point cwd at our temp wiki
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                # Reset the loaded flag so it re-reads
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

                load_secrets_env()

                assert os.environ["TELEGRAM_BOT_TOKEN"] == "file-token"
                assert os.environ["POE_API_KEY"] == "file-key"
                print("✓ test_load_secrets_env_populates_os_environ")


def test_load_secrets_env_clobbers_existing():
    """Verify .wiki/secrets.env values override existing env vars (file wins)."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import load_secrets_env

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        secrets = wiki_dir / ".wiki" / "secrets.env"
        secrets.parent.mkdir(parents=True, exist_ok=True)
        secrets.write_text("TELEGRAM_BOT_TOKEN=from-file\n")

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "from-shell"}, clear=True):
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

                load_secrets_env()

                assert os.environ["TELEGRAM_BOT_TOKEN"] == "from-file"
                print("✓ test_load_secrets_env_clobbers_existing")


def test_load_secrets_env_no_file_is_noop():
    """Verify load_secrets_env is a no-op when .wiki/secrets.env doesn't exist."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import load_secrets_env

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        # No .wiki/secrets.env created

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

                load_secrets_env()  # should not raise

                assert "TELEGRAM_BOT_TOKEN" not in os.environ
                print("✓ test_load_secrets_env_no_file_is_noop")


def test_require_telegram_bot_token_from_file():
    """Verify require_telegram_bot_token reads from .wiki/secrets.env."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import require_telegram_bot_token

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        secrets = wiki_dir / ".wiki" / "secrets.env"
        secrets.parent.mkdir(parents=True, exist_ok=True)
        secrets.write_text("TELEGRAM_BOT_TOKEN=tok-from-file\n")

        with patch.dict(os.environ, {}, clear=True):
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

                token = require_telegram_bot_token()
                assert token == "tok-from-file"
                print("✓ test_require_telegram_bot_token_from_file")


def test_require_telegram_bot_token_from_env_fallback():
    """Verify TELEGRAM_BOT_TOKEN env var works when no secrets.env exists."""
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from wiki.config import require_telegram_bot_token

    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok-from-env"}, clear=True):
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

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
            with patch("wiki.config.Path.cwd", return_value=wiki_dir):
                import wiki.config as cfg
                cfg._SECRETS_LOADED = False

                try:
                    require_telegram_bot_token()
                    assert False, "Should have raised SystemExit"
                except SystemExit as exc:
                    assert exc.code == 1
                    print("✓ test_require_telegram_bot_token_missing_exits")


def test_split_telegram_text():
    """Verify Telegram replies are chunked safely."""
    from wiki.telegram_client import split_telegram_text

    text = ("hello world\n" * 500).strip()
    chunks = split_telegram_text(text, limit=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)
    print("✓ test_split_telegram_text")


if __name__ == "__main__":
    print("Running wiki CLI tests...\n")
    test_init_creates_structure()
    test_init_idempotent()
    test_wiki_detection()
    test_filesystem_tools()
    test_git_tools()
    test_linter_middleware()
    test_chunking_split()
    test_parse_dotenv()
    test_load_secrets_env_populates_os_environ()
    test_load_secrets_env_clobbers_existing()
    test_load_secrets_env_no_file_is_noop()
    test_require_telegram_bot_token_from_file()
    test_require_telegram_bot_token_from_env_fallback()
    test_require_telegram_bot_token_missing_exits()
    test_agent_construction()
    test_observability_store()
    test_observability_init_run()
    test_persistent_checkpointer_roundtrip()
    test_telegram_state_store_and_rotation()
    test_split_telegram_text()
    print("\nAll tests passed!")
