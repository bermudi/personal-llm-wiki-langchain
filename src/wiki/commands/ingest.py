"""wiki ingest — process a raw source file."""

from __future__ import annotations

from pathlib import Path

from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel

from wiki.agent import create_wiki_agent
from wiki.config import validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware

console = Console()


def _parse_approval(approval: str) -> set[str]:
    """Parse the approval flag into a set of gate names."""
    if approval == "none":
        return set()
    return {g.strip() for g in approval.split(",") if g.strip()}


def run_ingest(path: str, approval: str) -> None:
    cwd = validate_wiki_dir()

    # Validate source file exists
    source_path = cwd / path
    if not source_path.exists():
        console.print(f"[red]Error: Source file not found: {path}[/red]")
        raise SystemExit(1)

    gates = _parse_approval(approval)

    # Build middleware
    middleware = [create_linter_middleware()]

    # Determine which tools need HITL interrupts
    interrupt_on = {}
    if "page" in gates:
        interrupt_on["write_file"] = {"allowed_decisions": ["approve", "reject"]}
    if "commit" in gates:
        interrupt_on["git_commit"] = {"allowed_decisions": ["approve", "reject"]}
    if interrupt_on:
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    middleware = [m for m in middleware if m is not None]

    # Create agent with checkpointer (needed for HITL interrupts)
    checkpointer = MemorySaver()
    agent = create_wiki_agent(
        checkpointer=checkpointer,
        middleware=middleware,
    )

    # Read source content
    source_content = source_path.read_text(encoding="utf-8")
    word_count = len(source_content.split())

    # Build the ingest prompt
    prompt = f"""Ingest the source file at `{path}` into the wiki.

The source is {word_count} words long. {'It is long enough to benefit from chunking (use split_source first).' if word_count > 10000 else 'Process it directly without chunking.'}

Steps:
1. Read the source file
2. Read wiki/index.md to orient yourself
3. {"Split the source, extract chunks, group them, synthesize groups into pages." if word_count > 10000 else "Analyze the content and identify knowledge worth capturing."}
4. Create or update wiki pages in wiki/
5. Update wiki/index.md with new entries
6. Append to wiki/log.md with a dated entry
7. Commit all changes atomically
"""

    config = {"configurable": {"thread_id": f"ingest-{source_path.stem}"}}

    # Plan approval gate
    if "plan" in gates:
        # First, let the agent analyze and present a plan
        plan_prompt = prompt + "\n\nFirst, present your plan for what pages to create/update. Do NOT make any changes yet — just describe what you plan to do."
        console.print(Panel("Planning...", style="bold blue"))
        result = agent.invoke(
            {"messages": [{"role": "user", "content": plan_prompt}]},
            config=config,
        )
        plan_text = result["messages"][-1].content
        console.print(Panel(plan_text, title="Agent Plan", border_style="cyan"))

        approve = input("\nApprove plan? [y/N]: ").strip().lower()
        if approve != "y":
            console.print("[yellow]Ingest cancelled.[/yellow]")
            return

        # Now execute
        execute_prompt = "The plan is approved. Proceed with the full ingestion now. Follow all steps."
        result = agent.invoke(
            {"messages": [{"role": "user", "content": execute_prompt}]},
            config=config,
        )
    else:
        # No plan gate — just run
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
        )

    # Handle any HITL interrupts during execution
    while "__interrupt__" in result:
        interrupt_info = result["__interrupt__"]
        console.print(Panel(str(interrupt_info), title="Approval Required", border_style="yellow"))

        approve = input("Approve? [y/N]: ").strip().lower()
        if approve == "y":
            result = agent.invoke(
                Command(resume={"decisions": [{"type": "approve"}]}),
                config=config,
            )
        else:
            result = agent.invoke(
                Command(resume={"decisions": [{"type": "reject", "feedback": "User rejected this action."}]}),
                config=config,
            )

    # Print final result
    final_message = result["messages"][-1].content
    console.print(Panel(final_message, title="Ingest Complete", border_style="green"))
