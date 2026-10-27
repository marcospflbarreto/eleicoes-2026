"""Copia para docs/img os gráficos dos notebooks executados que aparecem no README.

Cada figura é achada por um trecho do código da célula que a gera, então continua certa se a ordem das células mudar.
Rode depois de `gerar_notebooks.py --executar`:
    uv run python scripts/figuras_readme.py
"""

import base64
from pathlib import Path

import nbformat

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "img"

FIGURAS = {
    "benford_simulacao.png": ("03_comparacao_2022.ipynb", "A.simular_digitos(df, REF"),
    "secoes_extremas.png": ("03_comparacao_2022.ipynb", 'S[["a favor", "contra"]].plot.barh'),
    "secoes_jovens.png": ("03_comparacao_2022.ipynb", "Seções com eleitorado mais jovem que o prédio"),
    "emendas_por_mes.png": ("04_emendas_reeleicao.ipynb", "Pagamentos de emendas por mês"),
    "emendas_base_reeleicao.png": ("04_emendas_reeleicao.ipynb", "concentração das emendas na base eleitoral (terços)"),
}


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    notebooks = {}
    for nome, (arq, trecho) in FIGURAS.items():
        nb = notebooks.setdefault(arq, nbformat.read(RAIZ / "notebooks" / arq, as_version=4))
        celulas = [c for c in nb.cells if c.cell_type == "code" and trecho in c.source]
        if len(celulas) != 1:
            raise SystemExit(f"{nome}: esperada 1 célula com {trecho!r} em {arq}, achadas {len(celulas)}")
        imagens = [o["data"]["image/png"] for o in celulas[0].outputs if "image/png" in o.get("data", {})]
        if not imagens:
            raise SystemExit(f"{nome}: a célula não tem imagem (o notebook {arq} foi executado?)")
        (DESTINO / nome).write_bytes(base64.b64decode(imagens[0]))
        print(f"gravado {DESTINO / nome}")


if __name__ == "__main__":
    main()
