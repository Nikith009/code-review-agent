from fakes import PATCH_AUTH

from review_agent.diff import from_github_file, parse_patch


def test_parse_patch_tracks_new_line_numbers():
    lines = parse_patch(PATCH_AUTH)
    added = [(ln.new_line, ln.text.strip()) for ln in lines if ln.kind == "+"]
    assert added[0] == (11, "query = f\"SELECT * FROM users WHERE name = '{user}'\"")
    assert [n for n, _ in added] == [11, 12, 13]

    removed = [ln for ln in lines if ln.kind == "-"]
    assert removed[0].old_line == 11 and removed[0].new_line is None


def test_commentable_lines_cover_added_and_context():
    diff = from_github_file({"filename": "a.py", "patch": PATCH_AUTH, "additions": 3})
    assert diff.added_lines == {11, 12, 13}
    assert diff.commentable_lines == set(range(10, 17))


def test_multiple_hunks_and_no_newline_marker():
    patch = "@@ -1,2 +1,2 @@\n-a\n+b\n c\n\\ No newline at end of file\n@@ -20 +20,2 @@\n x\n+y"
    diff = from_github_file({"filename": "f.txt", "patch": patch})
    assert diff.added_lines == {1, 21}
    assert 20 in diff.commentable_lines


def test_render_shows_gutter():
    diff = from_github_file({"filename": "a.py", "patch": PATCH_AUTH})
    rendered = diff.render().splitlines()
    assert rendered[0].startswith("@@")
    assert any(line.startswith("   11 + ") for line in rendered)
    # removed lines have an empty gutter
    assert any(line.startswith("      - ") for line in rendered)


def test_binary_file_has_no_lines():
    diff = from_github_file({"filename": "logo.png", "status": "added"})
    assert diff.patch is None and diff.lines == []
