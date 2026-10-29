"""The scientist-facing skill must not drift from the commands it tells Claude to run.

Every `<isaac> ...` command written in the skill's files must name a subcommand that exists in the
local CLI's parser, and every `--flag` written on that command line must be one of that
subcommand's options. The skill is instructions, so this is the only thing standing between a
renamed flag and a Claude that confidently runs a command that fails.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
from pathlib import Path

import pytest

from isaac_api.local_import import extract as extract_module
from isaac_api.local_import.cli import build_parser, main as cli_main

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / ".claude" / "skills" / "isaac-historical-import"
FILES = [SKILL / "SKILL.md", *sorted((SKILL / "reference").glob("*.md"))]
SPAN = re.compile(r"`([^`\n]*<isaac> [^`\n]*)`")


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _flags(parser: argparse.ArgumentParser) -> set[str]:
    return {o for a in parser._actions for o in a.option_strings if o.startswith("--")}


def _resolve(words: list[str]) -> tuple[argparse.ArgumentParser, list[str]]:
    top = _subparsers(build_parser())
    command = words[0]
    assert command in top, f"`isaac {command}` does not exist in this build"
    node = top[command]
    rest = words[1:]
    # follow nested subcommands (`bundle template export`) as deep as the parser goes
    while inner := _subparsers(node):
        assert rest and rest[0] in inner, f"`isaac {command} {rest[:1]}` is not a subcommand ({sorted(inner)})"
        node, rest = inner[rest[0]], rest[1:]
    return node, rest


def _commands():
    for path in FILES:
        for span in SPAN.findall(path.read_text(encoding="utf-8")):
            after = span.split("<isaac> ", 1)[1]
            words = [w for w in re.split(r"\s+", after) if w]
            yield path.name, span, words


def test_the_skill_has_the_expected_shape():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: isaac-historical-import\ndescription: ")
    assert len(text.splitlines()) <= 250
    for ref in re.findall(r"`reference/([a-z0-9-]+\.md)`", text):
        assert (SKILL / "reference" / ref).is_file(), ref
    assert len(list(_commands())) >= 25, "the command scan found almost nothing; the pattern is broken"


@pytest.mark.parametrize(("name", "span", "words"), list(_commands()), ids=lambda v: v if isinstance(v, str) and len(v) < 60 else None)
def test_every_command_in_the_skill_exists_with_its_flags(name, span, words):
    command = [w for w in words if not w.startswith(("-", "<", "[", "(", "'", '"', "\\"))]
    node, _ = _resolve(command)
    written = set(re.findall(r"--[a-z][a-z-]*", span))
    unknown = written - _flags(node) - {"--help"}
    assert not unknown, f"{name}: `{span}` uses {sorted(unknown)} which this command does not take"


def test_the_skill_only_ever_uploads_as_a_dry_run_and_never_names_a_key():
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for span in SPAN.findall(text):
            if "bundle upload" in span:
                assert "--dry-run" in span, f"{path.name}: `{span}` is not a dry run"
        assert "ISAAC_PORTAL_TOKEN" not in text and "Bearer" not in text


def test_a_renamed_flag_would_be_caught(tmp_path):
    node, _ = _resolve(["bundle", "decide"])
    assert "--targets-file" in _flags(node) and "--no-such-flag" not in _flags(node)
    with pytest.raises(AssertionError):
        _resolve(["bundle", "no-such-subcommand"])


# --- the live CLI: every command and flag the skill names must show up in `--help` ----------


def _help_text(argv: list[str]) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = cli_main([*argv, "--help"])
    assert code == 0, f"`isaac {' '.join(argv)} --help` exited {code}"
    return buffer.getvalue()


@pytest.mark.parametrize(("name", "span", "words"), list(_commands()), ids=lambda v: v if isinstance(v, str) and len(v) < 60 else None)
def test_every_flag_the_skill_writes_is_in_the_live_help(name, span, words):
    command = [w for w in words if not w.startswith(("-", "<", "[", "(", "'", '"', "\\"))]
    _, rest = _resolve(command)
    argv = command[: len(command) - len(rest)]
    help_text = _help_text(argv)
    for flag in set(re.findall(r"--[a-z][a-z-]*", span)):
        assert flag in help_text or flag == "--help", f"{name}: `{span}` writes {flag}, which `isaac {' '.join(argv)} --help` does not show"


#: Short forms the skill uses without the `<isaac>` prefix (`decide --target ...`).
SHORT = re.compile(r"`((?:decide|annotate|excerpt|reveal|crosscheck-plan|questions|group|process|build-records|validate|export|upload) --[^`\n]*)`")


def test_short_form_commands_use_real_flags():
    seen = 0
    for path in FILES:
        for span in SHORT.findall(path.read_text(encoding="utf-8")):
            sub = span.split()[0]
            argv = [sub] if sub == "process" else ["bundle", sub]
            help_text = _help_text(argv)
            for flag in set(re.findall(r"--[a-z][a-z-]*", span)):
                assert flag in help_text, f"{path.name}: `{span}` uses {flag}, not shown by `isaac {' '.join(argv)} --help`"
            seen += 1
    assert seen >= 4, "the short-form scan found almost nothing; the pattern is broken"


def test_the_extractor_commands_use_real_flags():
    flags = {o for a in extract_module.build_parser()._actions for o in a.option_strings if o.startswith("--")}
    seen = 0
    for path in FILES:
        for span in re.findall(r"`([^`\n]*isaac_api\.local_import\.extract[^`\n]*)`", path.read_text(encoding="utf-8")):
            unknown = set(re.findall(r"--[a-z][a-z-]*", span)) - flags
            assert not unknown, f"{path.name}: `{span}` uses {sorted(unknown)}"
            seen += 1
    assert seen >= 2


def test_every_flag_named_anywhere_in_the_skill_exists_in_some_command():
    known = {"--help"} | {o for a in extract_module.build_parser()._actions for o in a.option_strings}

    def walk(parser):
        known.update(o for a in parser._actions for o in a.option_strings)
        for child in _subparsers(parser).values():
            walk(child)

    walk(build_parser())
    skill_flags = {"--test-marker", "--qc-status", "--blocking-only", "--question", "--only", "--field"}
    assert skill_flags <= known, "the live CLI lacks a flag the skill relies on"
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for flag in set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", text)):
            if flag in {"--install-skill", "--with-processing", "--skip-processing", "--skip-portal"}:
                continue  # scripts/setup_isaac_local.sh options, not isaac options
            assert flag in known, f"{path.name} names {flag}, which no command takes"


def test_the_skill_keeps_the_test_marker_away_from_scientists():
    text = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
    assert "--test-marker" in text and "Never use `build-records --test-marker` with a real scientist" in text
    assert "--blocking-only" in text and "applies to" in text and "--qc-status" in text
    assert "record_contract.json" in text and "What an ISAAC record is" in text


def _positional_choices(sub: str) -> set[str]:
    node = _subparsers(build_parser())["bundle"]
    parser = _subparsers(node)[sub]
    for action in parser._actions:
        if action.choices and action.dest in ("kind",):
            return set(action.choices)
    return set()


def test_every_list_and_show_kind_the_skill_names_exists_in_the_live_cli():
    seen = 0
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for sub, rest in re.findall(r"bundle (list|show) <bundle> ([^`\n]+)", text):
            first = re.split(r"\s", rest.strip())[0]
            for kind in re.split(r"\\?\|", first):
                kind = kind.strip("`.,;")
                if not re.fullmatch(r"[a-z][a-z-]*", kind):
                    continue
                assert kind in _positional_choices(sub), f"{path.name}: `bundle {sub} <bundle> {kind}` is not a kind the live CLI accepts ({sorted(_positional_choices(sub))})"
                seen += 1
    assert seen >= 6


def test_no_example_approves_a_processing_result_without_a_qc_status():
    for path in FILES:
        for span in re.findall(r"`([^`\n]*--decision approve(?![_\w])[^`\n]*)`", path.read_text(encoding="utf-8")):
            assert "--qc-status" in span, f"{path.name}: `{span}` approves without --qc-status"


def test_the_skill_forbids_writing_bundle_files_and_inferred_decisions():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "You do not write files." in text and "bundle.json" in text.split("You do not write files.")[1][:200]
    assert "answer the scientist gave in THIS conversation" in text
    assert "record_groups.json" not in text


def test_the_skill_never_tells_claude_to_write_inside_the_bundle_folder():
    for path in FILES:
        text = " ".join(path.read_text(encoding="utf-8").split())
        for bad in re.findall(r"(?:write|save|put|create)[^.`]{0,60}(?:in|into|to|inside) the bundle folder", text, flags=re.I):
            raise AssertionError(f"{path.name}: tells Claude to write in the bundle folder: {bad!r}")
    questions = (SKILL / "reference" / "questions-and-decisions.md").read_text(encoding="utf-8")
    assert "mktemp" in questions and "OUTSIDE the bundle folder" in questions


def test_the_calibration_decision_is_in_the_skill_with_real_flags():
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "approve_calibration" in skill and "--element" in skill and "--edge" in skill and "No answer, no shift" in skill
    help_text = _help_text(["bundle", "decide"])
    for flag in ("--element", "--edge"):
        assert flag in help_text
    assert "approve_calibration" in (SKILL / "reference" / "commands.md").read_text(encoding="utf-8")
    assert "approve_calibration" in (SKILL / "reference" / "grouping-and-processing.md").read_text(encoding="utf-8")
