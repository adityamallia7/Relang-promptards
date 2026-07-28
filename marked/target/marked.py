#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    marked_js = repo_root / "source" / "lib" / "marked.esm.js"
    node = shutil.which("node")
    if not node:
        sys.stderr.write("node not found in PATH\n")
        return 1

    data = sys.stdin.buffer.read()
    module_url = marked_js.resolve().as_uri() if hasattr(marked_js, "resolve") else str(marked_js)
    js_code = """
const { readFileSync } = require('node:fs');
(async () => {
  const { marked } = await import(process.argv[1]);
  const input = readFileSync(0, 'utf8');
  process.stdout.write(`${marked.parse(input)}\\n`);
})();
"""

    result = subprocess.run(
        [node, "-e", js_code, module_url],
        input=data,
        capture_output=True,
    )
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
