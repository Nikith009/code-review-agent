from fakes import PATCH_AUTH, FakeGitHub, ScriptedAnthropic, block

from review_agent.diff import from_github_file
from review_agent.reviewer import ClaudeReviewer, slice_lines


def pr():
    return FakeGitHub().get_pull("o", "r", 7)


def diff():
    return from_github_file({"filename": "app/auth.py", "patch": PATCH_AUTH})


def test_tool_loop_reads_a_file_then_reports():
    client = ScriptedAnthropic(
        [
            [block(type="tool_use", id="t1", name="read_file", input={"path": "app/db.py"})],
            [
                block(
                    type="tool_use",
                    id="t2",
                    name="report_findings",
                    input={
                        "findings": [
                            {
                                "line": 11,
                                "severity": "critical",
                                "category": "security",
                                "title": "SQL injection",
                                "body": "Use parameters.",
                                "confidence": 0.9,
                            }
                        ]
                    },
                )
            ],
        ]
    )
    reads = []
    reviewer = ClaudeReviewer(client=client)
    found = reviewer.review_file(pr(), "summary", diff(), lambda p: reads.append(p) or "a\nb\nc")

    assert reads == ["app/db.py"]
    assert [(f.line, f.title) for f in found] == [(11, "SQL injection")]

    second = client.calls[1]["messages"]
    tool_result = second[-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1"
    assert "    2  b" in tool_result["content"]


def test_last_step_forces_report_tool():
    reading = [block(type="tool_use", id="t", name="read_file", input={"path": "x"})]
    report = [block(type="tool_use", id="r", name="report_findings", input={"findings": []})]
    client = ScriptedAnthropic([reading, reading, report])
    found = ClaudeReviewer(client=client, max_steps=3).review_file(
        pr(), "s", diff(), lambda p: None
    )
    assert found == []
    assert "tool_choice" not in client.calls[0]
    assert client.calls[2]["tool_choice"] == {"type": "tool", "name": "report_findings"}
    assert "File not found" in client.calls[1]["messages"][-1]["content"][0]["content"]


def test_prose_reply_means_no_findings():
    client = ScriptedAnthropic([[block(type="text", text="Looks fine.")]])
    assert ClaudeReviewer(client=client).review_file(pr(), "s", diff(), lambda p: None) == []


def test_slice_lines_bounds():
    text = "\n".join(f"l{i}" for i in range(1, 11))
    out = slice_lines(text, 9, 50).splitlines()
    assert out == ["    9  l9", "   10  l10"]
