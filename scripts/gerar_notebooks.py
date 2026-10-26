"""Gera (e opcionalmente executa) os notebooks a partir das definições em nb_*.py.

Uso:
    uv run python scripts/gerar_notebooks.py            # só gera
    uv run python scripts/gerar_notebooks.py --executar # gera e executa, salvando as saídas
"""

import argparse
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import nb_adversarial  # noqa: E402
import nb_neutro  # noqa: E402

NOTEBOOKS = AQUI.parent / "notebooks"


def montar(mod) -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3 (eleicoes-2026)", "language": "python"}
    for tipo, src in mod.CELULAS:
        src = src.strip("\n")
        nb.cells.append(nbformat.v4.new_markdown_cell(src) if tipo == "md" else nbformat.v4.new_code_cell(src))
    return nb


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--executar", action="store_true")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--so", choices=["neutro", "adversarial"], help="gera apenas um dos notebooks")
    a = p.parse_args()
    NOTEBOOKS.mkdir(exist_ok=True)
    for mod in (nb_neutro, nb_adversarial):
        if a.so and a.so not in mod.__name__:
            continue
        nb = montar(mod)
        dest = NOTEBOOKS / mod.TITULO
        if a.executar:
            print(f"executando {dest.name}...")
            NotebookClient(nb, timeout=a.timeout, kernel_name="python3", resources={"metadata": {"path": str(NOTEBOOKS)}}).execute()
        nbformat.write(nb, dest)
        print(f"gravado {dest}")


if __name__ == "__main__":
    main()
