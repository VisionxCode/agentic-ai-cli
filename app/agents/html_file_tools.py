from __future__ import annotations

from pathlib import Path


def _path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _read_lines(path: str) -> list[str]:
    return _path(path).read_text(encoding="utf-8").splitlines(keepends=True)


def _write_lines(path: str, lines: list[str]) -> None:
    _path(path).write_text("".join(lines), encoding="utf-8")


def read_html_line_range(path: str, start_line: int, end_line: int) -> str:
    """Read a 1-indexed inclusive line range from an HTML file."""
    lines = _read_lines(path)
    start = max(1, start_line)
    end = min(len(lines), end_line)
    if start > end:
        return ""
    return "\n".join(
        f"{number}: {lines[number - 1].rstrip()}" for number in range(start, end + 1)
    )


def replace_html_line_range(path: str, start_line: int, end_line: int, replacement: str) -> str:
    """Replace a 1-indexed inclusive line range in an HTML file."""
    lines = _read_lines(path)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        return f"No replacement made: invalid range {start_line}-{end_line}."
    new_lines = replacement.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines[-1] = f"{new_lines[-1]}\n"
    if not new_lines:
        new_lines = []
    lines[start_line - 1 : end_line] = new_lines
    _write_lines(path, lines)
    return f"Replaced lines {start_line}-{end_line}."


def insert_after_line(path: str, line_number: int, content: str) -> str:
    """Insert content after a 1-indexed line number in an HTML file."""
    lines = _read_lines(path)
    if line_number < 0 or line_number > len(lines):
        return f"No insertion made: invalid line {line_number}."
    new_lines = content.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines[-1] = f"{new_lines[-1]}\n"
    lines[line_number:line_number] = new_lines
    _write_lines(path, lines)
    return f"Inserted after line {line_number}."


def build_html_file_tools() -> list:
    try:
        from agents import function_tool
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    @function_tool
    def read_html_file(path: str) -> str:
        """Read an HTML source file from disk."""
        return _path(path).read_text(encoding="utf-8")

    @function_tool
    def search_html_file(path: str, query: str) -> list[str]:
        """Search an HTML source file and return matching numbered line snippets."""
        matches = []
        for number, line in enumerate(_path(path).read_text(encoding="utf-8").splitlines(), 1):
            if query.lower() in line.lower():
                matches.append(f"{number}: {line}")
        return matches

    @function_tool
    def read_html_lines(path: str, start_line: int, end_line: int) -> str:
        """Read a numbered line range before deciding an edit."""
        return read_html_line_range(path, start_line, end_line)

    @function_tool
    def replace_html_lines(path: str, start_line: int, end_line: int, replacement: str) -> str:
        """Replace a numbered line range. Prefer this for revisions."""
        return replace_html_line_range(path, start_line, end_line, replacement)

    @function_tool
    def insert_html_after_line(path: str, line_number: int, content: str) -> str:
        """Insert HTML/CSS after a numbered line. Prefer this for additions."""
        return insert_after_line(path, line_number, content)

    @function_tool
    def write_html_file(path: str, content: str) -> str:
        """Write the full HTML source file. Use only for the first draft or unusable files."""
        file_path = _path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return "HTML file written."

    return [
        read_html_file,
        search_html_file,
        read_html_lines,
        replace_html_lines,
        insert_html_after_line,
        write_html_file,
    ]
