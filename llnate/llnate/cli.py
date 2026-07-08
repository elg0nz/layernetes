"""The llnate command-line interface."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import typer

from . import __version__, api, config, project, scaffold

app = typer.Typer(
    name="llnate",
    help="Build, ship, and host CrewAI agents on the Learning Layer cloud.",
    no_args_is_help=True,
)

plugin_app = typer.Typer(help="Coding-assistant integration.", no_args_is_help=True)
app.add_typer(plugin_app, name="plugin")

POLL_INTERVAL_SECONDS = 2  # frozen by the ll-api contract
PUSH_TIMEOUT_SECONDS = 15 * 60
# How long a pre-existing Failed status may linger after a push before we
# report it as this deploy's failure (CI needs time to report the new sha).
STALE_FAILURE_GRACE_SECONDS = 150


def _fail(message: str) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _run_git(args: list[str], cwd: Path | None = None, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, **kwargs)


def _head_short_sha() -> str:
    """First 7 chars of HEAD — matches the deploy workflow's ``${GITHUB_SHA::7}``,
    which is the sha CI reports back and the operator deploys."""
    result = _run_git(["rev-parse", "HEAD"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()[:7]


def _sha_matches(reported: str, target: str) -> bool:
    """True when two short SHAs name the same commit (prefix-compatible, so a
    length mismatch between CI's and ours never causes a false negative)."""
    if not reported or not target:
        return False
    return reported.startswith(target) or target.startswith(reported)


def _require_login() -> dict:
    cfg = config.load()
    if not cfg.get("token") or not cfg.get("username"):
        raise _fail("not logged in -- run `llnate login` first")
    return cfg


def _cr_name(username: str) -> str:
    """LLAgent CR name for this project.

    Prefers `.llnate.toml`'s `agent_name` (written by `login`, and
    hand-writable for recovery -- see `project.py`); falls back to
    <username>-<current directory name> for projects predating that file.
    """
    saved = project.load().get("agent_name")
    return saved or f"{username}-{Path.cwd().name}"


def _client(cfg: dict | None = None) -> api.Client:
    token = (cfg or {}).get("token")
    return api.Client(config.api_url(), token=token)


# ---------------------------------------------------------------------------
# init / plugin install
# ---------------------------------------------------------------------------


@app.command()
def init(name: str = typer.Argument(..., help="Name of the new agent project directory.")):
    """Scaffold a new LLAgent project: CrewAI crew, Dockerfile, CI workflow."""
    root = Path(name)
    if root.exists():
        raise _fail(f"{name} already exists")
    root.mkdir(parents=True)
    created = scaffold.create_project(root, name)

    if shutil.which("git") is None:
        raise _fail("git not found on PATH (required to initialize the project repo)")
    for git_args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        [
            "-c", "user.name=llnate",
            "-c", "user.email=llnate@learninglayer.ai",
            # The scaffold commit is authored by llnate, not the user, so
            # never invoke their signing setup (which may prompt or block).
            "-c", "commit.gpgsign=false",
            "commit", "-q", "-m", "Scaffold LLAgent project (llnate init)",
        ],
    ):
        result = _run_git(git_args, cwd=root)
        if result.returncode != 0:
            raise _fail(f"git {' '.join(git_args)} failed in {root}")

    typer.echo(f"Created LLAgent project '{name}':")
    for path in created:
        typer.echo(f"  {path}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {name}")
    typer.echo("  llnate plugin install   # wire up AI coding hooks")
    typer.echo("  llnate login            # provision your cloud repo + keys")


@plugin_app.command("install")
def plugin_install():
    """Install CrewAI "Build with AI" hooks for your coding assistant (MVP stub)."""
    target = Path.cwd() / "CLAUDE.md"
    target.write_text(scaffold.CLAUDE_MD, encoding="utf-8")
    typer.echo(f"Wrote {target}")
    typer.echo(
        "CLAUDE.md points your coding assistant at AGENTS.md -- the source of\n"
        "truth for this project's runtime contract and the llnate workflow\n"
        "(both scaffolded by `llnate init`). Full CrewAI 'Build with AI' wiring\n"
        "(https://github.com/crewAIInc/crewAI#build-with-ai) is post-MVP."
    )


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def _embed_credentials(clone_url: str, username: str, token: str) -> str:
    parts = urlsplit(clone_url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{quote(username, safe='')}:{quote(token, safe='')}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _set_remote(remote_url: str) -> None:
    if _run_git(["rev-parse", "--git-dir"], capture_output=True).returncode != 0:
        raise _fail("current directory is not a git repository -- run `llnate init` first")
    if _run_git(["remote", "get-url", "layernetes"], capture_output=True).returncode == 0:
        result = _run_git(["remote", "set-url", "layernetes", remote_url], capture_output=True)
    else:
        result = _run_git(["remote", "add", "layernetes", remote_url], capture_output=True)
    if result.returncode != 0:
        raise _fail(f"could not configure git remote: {result.stderr.decode().strip()}")


@app.command()
def login(
    username: str = typer.Option(None, "--username", "-u", envvar="LLNATE_USERNAME"),
    password: str = typer.Option(None, "--password", "-p", envvar="LLNATE_PASSWORD"),
):
    """Log in to the Learning Layer cloud and provision this agent's repo."""
    if username is None:
        username = typer.prompt("Username")
    if password is None:
        password = typer.prompt("Password", hide_input=True)

    api_url = config.api_url()
    with api.Client(api_url) as anon:
        try:
            auth = anon.login(username, password)
        except api.ApiError as exc:
            raise _fail(str(exc))

    token = auth["token"]
    username = auth.get("username", username)
    config.update(api_url=api_url, username=username, token=token)
    typer.echo(f"Logged in as {username} ({api_url})")

    agent_name = Path.cwd().name
    with api.Client(api_url, token=token) as client:
        try:
            agent = client.create_agent(agent_name)
        except api.ApiError as exc:
            raise _fail(f"could not provision agent '{agent_name}': {exc}")

    age_public_key = agent.get("age_public_key")
    if age_public_key:
        config.update(age_public_key=age_public_key)
        typer.echo(f"age public key: {age_public_key}")

    if agent.get("name"):
        project.save(agent_name=agent["name"])

    clone_url = agent["clone_url"]
    _set_remote(_embed_credentials(clone_url, username, token))
    typer.echo(f"Provisioned repo: {agent.get('repo', agent_name)}")
    typer.echo(f"Remote 'layernetes' -> {clone_url}")
    typer.echo("Next: `llnate keys` to encrypt credentials, commit, and deploy.")


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------

SOPS_YAML_TEMPLATE = """\
creation_rules:
  - path_regex: (^|/)keys\\.env$
    input_type: dotenv
    output_type: dotenv
    age: {age_public_key}
"""


def _collect_pairs(pairs: list[str] | None) -> list[str]:
    collected: list[str] = []
    if pairs:
        for pair in pairs:
            key, sep, _ = pair.partition("=")
            if not sep or not key:
                raise _fail(f"expected KEY=VALUE, got: {pair!r}")
            collected.append(pair)
        return collected

    typer.echo("Enter credentials as KEY=VALUE (empty line to finish):")
    while True:
        line = typer.prompt("", default="", show_default=False, prompt_suffix="> ").strip()
        if not line:
            break
        key, sep, _ = line.partition("=")
        if not sep or not key:
            typer.echo("  expected KEY=VALUE, try again")
            continue
        collected.append(line)
    return collected


@app.command()
def keys(pairs: list[str] = typer.Argument(None, help="KEY=VALUE pairs to encrypt.")):
    """Encrypt credentials into keys.env, commit them, and push/deploy."""
    cfg = _require_login()

    age_public_key = cfg.get("age_public_key")
    if not age_public_key:
        with _client(cfg) as client:
            try:
                age_public_key = client.me()["age_public_key"]
            except api.ApiError as exc:
                raise _fail(f"could not fetch your age public key: {exc}")
        config.update(age_public_key=age_public_key)

    if shutil.which("sops") is None:
        raise _fail(
            "the `sops` binary is required but was not found on PATH.\n"
            "Install it first: https://github.com/getsops/sops "
            "(macOS: `brew install sops`)"
        )

    collected = _collect_pairs(pairs)
    if not collected:
        raise _fail("no credentials given; nothing to encrypt")

    plaintext = "\n".join(collected) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix="llnate-keys-", suffix=".env")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(plaintext)
        result = subprocess.run(
            [
                "sops", "--encrypt",
                "--input-type", "dotenv",
                "--output-type", "dotenv",
                "--age", age_public_key,
                tmp_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise _fail(f"sops failed: {result.stderr.strip()}")
        Path("keys.env").write_text(result.stdout, encoding="utf-8")
    finally:
        # Never leave plaintext on disk, success or failure.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    Path(".sops.yaml").write_text(
        SOPS_YAML_TEMPLATE.format(age_public_key=age_public_key), encoding="utf-8"
    )
    typer.echo(f"Encrypted {len(collected)} credential(s) into keys.env")
    typer.echo("Wrote .sops.yaml (so `sops keys.env` edits keep working)")

    _run_git(["add", "keys.env", ".sops.yaml"])
    commit = _run_git(["commit", "-m", "Update encrypted keys.env"], capture_output=True, text=True)
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            typer.echo("keys.env unchanged; nothing to commit.")
        else:
            raise _fail(f"git commit failed: {commit.stderr.strip()}")
    else:
        typer.echo("Committed keys.env")

    push()


# ---------------------------------------------------------------------------
# push / status / delete
# ---------------------------------------------------------------------------


def _print_summary(url: str) -> None:
    base = url.rstrip("/")
    typer.echo(f"  HTTP: {base}")
    typer.echo(f"  MCP:  {base}/mcp")
    typer.echo(f"  Docs: {base}/docs")
    typer.echo("\nTry it:")
    typer.echo(f"""  curl -s -X POST {base}/kickoff \\
    -H 'Content-Type: application/json' \\
    -d '{{"inputs": {{"question": "How many berries in strawberry?"}}}}'""")
    typer.echo("\nAdd to Claude Code:")
    typer.echo(f"  claude mcp add --transport http agent {base}/mcp")


@app.command()
def push():
    """Deploy: push to the cloud repo, then follow the build until it is live."""
    cfg = _require_login()
    cr_name = _cr_name(cfg["username"])

    # The revision we're about to ship. Until the platform reports THIS sha,
    # any phase it returns (a stale Ready or Failed, with the previous
    # revision's URL) belongs to an earlier deploy and must be ignored.
    target_sha = _head_short_sha()

    typer.echo("Pushing to layernetes remote...")
    # Streamed: git inherits stdout/stderr.
    result = _run_git(["push", "layernetes", "HEAD:main"])
    if result.returncode != 0:
        raise _fail("git push failed")

    typer.echo(f"Waiting for {cr_name} to deploy (polling every {POLL_INTERVAL_SECONDS}s)...")
    start = time.monotonic()
    deadline = start + PUSH_TIMEOUT_SECONDS
    last_phase = None
    stale_notice_shown = False
    building_notice_shown = False
    with _client(cfg) as client:
        while True:
            try:
                status = client.agent_status(cr_name)
            except api.ApiError as exc:
                raise _fail(str(exc))
            phase = status.get("phase", "Unknown")

            if target_sha and "sha" in status:
                # Precise gate: trust phase only once the platform reports our
                # revision's sha. Before CI's build callback lands, the status
                # still describes the previous revision (this is the bug fix:
                # a leftover Ready/Failed no longer ends the push early).
                if not _sha_matches(status.get("sha", ""), target_sha):
                    if not building_notice_shown:
                        typer.echo("  building new revision...")
                        building_notice_shown = True
                    if time.monotonic() >= deadline:
                        raise _fail("timed out waiting for CI to build the new revision")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
            elif (
                # Legacy ll-api that doesn't report a sha: fall back to the
                # best-effort stale-Failed grace window.
                phase == "Failed"
                and last_phase is None
                and time.monotonic() - start < STALE_FAILURE_GRACE_SECONDS
            ):
                if not stale_notice_shown:
                    typer.echo("  previous revision had failed; waiting for the new build...")
                    stale_notice_shown = True
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            if phase != last_phase:
                if last_phase is not None and sys.stdout.isatty():
                    typer.echo()  # finish the in-place line before a new phase
                typer.echo(f"  phase: {phase}")
                last_phase = phase
            elif sys.stdout.isatty():
                sys.stdout.write(f"\r  phase: {phase} ({int(deadline - time.monotonic())}s left)")
                sys.stdout.flush()

            if phase == "Ready":
                typer.echo("\nAgent is live:")
                _print_summary(status.get("url", ""))
                return
            if phase == "Failed":
                raise _fail(f"deploy failed: {status.get('message') or '(no detail)'}")
            if time.monotonic() >= deadline:
                raise _fail("timed out after 15 minutes waiting for the agent to become Ready")
            time.sleep(POLL_INTERVAL_SECONDS)


@app.command()
def status():
    """Print this agent's current deploy status."""
    cfg = _require_login()
    cr_name = _cr_name(cfg["username"])
    with _client(cfg) as client:
        try:
            info = client.agent_status(cr_name)
        except api.ApiError as exc:
            raise _fail(str(exc))
    typer.echo(f"{cr_name}: {info.get('phase', 'Unknown')}")
    if info.get("message"):
        typer.echo(f"  message: {info['message']}")
    if info.get("url"):
        _print_summary(info["url"])
    if info.get("phase") == "Failed":
        raise typer.Exit(code=1)


@app.command()
def delete(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Tear down this agent: delete the LLAgent, its namespace, and repo."""
    cfg = _require_login()
    cr_name = _cr_name(cfg["username"])
    if not yes:
        typer.confirm(
            f"Delete agent '{cr_name}' (cloud repo, deployment, and URL)?", abort=True
        )
    with _client(cfg) as client:
        try:
            client.delete_agent(cr_name)
        except api.ApiError as exc:
            raise _fail(str(exc))
    typer.echo(f"Deleted {cr_name}")


@app.callback(invoke_without_command=True)
def _main(
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
):
    if version:
        typer.echo(f"llnate {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
