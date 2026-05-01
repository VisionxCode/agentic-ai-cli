from __future__ import annotations

from pathlib import Path

from app.job_logging import log_tool_usage


def _path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def scoped_source_path(source_root: Path, path: str | Path) -> Path:
    root = source_root.resolve()
    raw_path = Path(path)
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    resolved = candidate.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Path {path} is outside the session source root.")
    return resolved


def _resolve_path(path: str | Path, source_root: Path | None = None) -> Path:
    if source_root is not None:
        return scoped_source_path(source_root, path)
    return _path(path)


def _read_lines(path: str | Path, source_root: Path | None = None) -> list[str]:
    return _resolve_path(path, source_root).read_text(encoding="utf-8").splitlines(keepends=True)


def _write_lines(path: str | Path, lines: list[str], source_root: Path | None = None) -> None:
    _resolve_path(path, source_root).write_text("".join(lines), encoding="utf-8")


def read_html_line_range(
    path: str, start_line: int, end_line: int, *, source_root: Path | None = None
) -> str:
    """Read a 1-indexed inclusive line range from an HTML file."""
    file_path = _resolve_path(path, source_root)
    lines = _read_lines(file_path)
    start = max(1, start_line)
    end = min(len(lines), end_line)
    log_tool_usage("read_html_lines", path=file_path, start_line=start, end_line=end)
    if start > end:
        return ""
    return "\n".join(
        f"{number}: {lines[number - 1].rstrip()}" for number in range(start, end + 1)
    )


def replace_html_line_range(
    path: str,
    start_line: int,
    end_line: int,
    replacement: str,
    *,
    source_root: Path | None = None,
) -> str:
    """Replace a 1-indexed inclusive line range in an HTML file."""
    file_path = _resolve_path(path, source_root)
    lines = _read_lines(file_path)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        log_tool_usage(
            "replace_html_lines",
            path=file_path,
            start_line=start_line,
            end_line=end_line,
            changed=False,
        )
        return f"No replacement made: invalid range {start_line}-{end_line}."
    new_lines = replacement.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines[-1] = f"{new_lines[-1]}\n"
    if not new_lines:
        new_lines = []
    lines[start_line - 1 : end_line] = new_lines
    _write_lines(file_path, lines)
    log_tool_usage(
        "replace_html_lines",
        path=file_path,
        start_line=start_line,
        end_line=end_line,
        replacement_chars=len(replacement),
        changed=True,
    )
    return f"Replaced lines {start_line}-{end_line}."


def insert_after_line(
    path: str, line_number: int, content: str, *, source_root: Path | None = None
) -> str:
    """Insert content after a 1-indexed line number in an HTML file."""
    file_path = _resolve_path(path, source_root)
    lines = _read_lines(file_path)
    if line_number < 0 or line_number > len(lines):
        log_tool_usage(
            "insert_html_after_line",
            path=file_path,
            line_number=line_number,
            changed=False,
        )
        return f"No insertion made: invalid line {line_number}."
    new_lines = content.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines[-1] = f"{new_lines[-1]}\n"
    lines[line_number:line_number] = new_lines
    _write_lines(file_path, lines)
    log_tool_usage(
        "insert_html_after_line",
        path=file_path,
        line_number=line_number,
        inserted_chars=len(content),
        changed=True,
    )
    return f"Inserted after line {line_number}."


def build_html_file_tools(source_root: Path | None = None) -> list:
    try:
        from agents import function_tool
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    @function_tool
    def read_html_file(path: str) -> str:
        """Read an HTML source file from the session source root."""
        file_path = _resolve_path(path, source_root)
        content = file_path.read_text(encoding="utf-8")
        log_tool_usage("read_html_file", path=file_path, chars=len(content))
        return content

    @function_tool
    def search_html_file(path: str, query: str) -> list[str]:
        """Search an HTML source file in the session source root and return matching numbered lines."""
        file_path = _resolve_path(path, source_root)
        matches = []
        for number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
            if query.lower() in line.lower():
                matches.append(f"{number}: {line}")
        log_tool_usage("search_html_file", path=file_path, query=query, matches=len(matches))
        return matches

    @function_tool
    def read_html_lines(path: str, start_line: int, end_line: int) -> str:
        """Read a numbered line range before deciding an edit."""
        return read_html_line_range(path, start_line, end_line, source_root=source_root)

    @function_tool
    def replace_html_lines(path: str, start_line: int, end_line: int, replacement: str) -> str:
        """Replace a numbered line range. Prefer this for revisions."""
        return replace_html_line_range(
            path, start_line, end_line, replacement, source_root=source_root
        )

    @function_tool
    def insert_html_after_line(path: str, line_number: int, content: str) -> str:
        """Insert HTML/CSS after a numbered line. Prefer this for additions."""
        return insert_after_line(path, line_number, content, source_root=source_root)

    @function_tool
    def write_html_file(path: str, content: str) -> str:
        """Write the full HTML source file under the session source root."""
        file_path = _resolve_path(path, source_root)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        log_tool_usage("write_html_file", path=file_path, chars=len(content), changed=True)
        return "HTML file written."

    @function_tool
    def list_source_files(directory: str) -> list[str]:
        """List files under the session source root, including CSS and JavaScript files."""
        root = _resolve_path(directory, source_root)
        files = [
            str(path.relative_to(root)).replace("\\", "/")
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]
        log_tool_usage("list_source_files", path=root, matches=len(files))
        return files

    @function_tool
    def read_text_file(path: str) -> str:
        """Read any text source file under the session source root."""
        file_path = _resolve_path(path, source_root)
        content = file_path.read_text(encoding="utf-8")
        log_tool_usage("read_text_file", path=file_path, chars=len(content))
        return content

    @function_tool
    def write_text_file(path: str, content: str) -> str:
        """Write any text source file under the session source root."""
        file_path = _resolve_path(path, source_root)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        log_tool_usage("write_text_file", path=file_path, chars=len(content), changed=True)
        return "Text file written."

    return [
        read_html_file,
        search_html_file,
        read_html_lines,
        replace_html_lines,
        insert_html_after_line,
        write_html_file,
        list_source_files,
        read_text_file,
        write_text_file,
    ]
