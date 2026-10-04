"""Export reusable definitions without executing notebook examples.

Notebooks are the source of truth. Only explicitly listed definition cells are
exported, so importing a module never opens sample files or calls a model.
"""

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "docx": ("workshops/word/clean-pure-text.ipynb", [1, 6]),
    "html": ("workshops/html/clean-html.ipynb", [1, 2, 5, 8]),
    "email": ("workshops/email/clean-email.ipynb", [1, 2, 6]),
    "pptx": ("workshops/ppt/clean-ppt.ipynb", [1, 2, 7]),
    "img": ("workshops/img/clean-image.ipynb", [1, 2, 3]),
    "audio": ("workshops/media/clean-audio.ipynb", [1, 2]),
    "xlsx": ("workshops/xlsx/clean-data.ipynb", [1]),
    "pdf_text": ("workshops/pdf/纯文本.pdf/clean-pure-text.ipynb", [1, 2]),
    "pdf_scan": ("workshops/pdf/扫描.pdf/clean-scan-pdf.ipynb", [1, 2]),
    "pdf_mixed": ("workshops/pdf/图文混排.pdf/clean-mixed-pdf.ipynb", [1]),
}


def module_source(name: str) -> str:
    relative_path, cell_indices = NOTEBOOKS[name]
    notebook = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    parts = []
    for index in cell_indices:
        cell = notebook["cells"][index]
        if cell["cell_type"] != "code":
            raise ValueError(f"Expected definition code cell: {relative_path}:{index}")
        source = "".join(cell["source"])
        if name == "html" and index == 8:
            # The caption cell also contains an interactive preview. Keep only
            # its import and function definitions, not notebook variables.
            nodes = ast.parse(source).body
            source = "\n\n".join(
                ast.get_source_segment(source, node)
                for node in nodes
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))
            )
        parts.append(source.strip())
    result = (
        f'"""Generated from {relative_path}; edit the notebook, then re-export."""\n\n'
        + "\n\n".join(parts)
        + "\n"
    )
    compile(result, f"_extracted/{name}.py", "exec")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check exports without writing")
    args = parser.parse_args()
    stale = []
    for name in NOTEBOOKS:
        target = ROOT / "_extracted" / f"{name}.py"
        source = module_source(name)
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != source:
                stale.append(str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(exist_ok=True)
            target.write_text(source, encoding="utf-8", newline="\n")
    if stale:
        raise SystemExit("Exports need updating: " + ", ".join(stale))
    print("Notebook exports are up to date." if args.check else "Exported 10 modules.")


if __name__ == "__main__":
    main()
