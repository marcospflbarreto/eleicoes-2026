"""Baixa o perfil do eleitorado por seção (idade, escolaridade) e o cadastro de locais de votação do TSE.

Esses dados não vêm no BU, mas explicam diferenças legítimas entre seções do mesmo prédio: seções novas
costumam receber eleitores jovens e transferidos (ex.: universitários), seções com acessibilidade concentram
idosos etc.

Saídas (em data/processed):
    perfil_secao.parquet   uma linha por seção: aptos no cadastro, % de 16–24 anos, % de 60+ anos,
                           % com ensino superior (completo ou incompleto)
    locais_votacao.parquet uma linha por seção e turno: tipo de local, acessibilidade, seção agregada

Uso:
    uv run perfil
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
from tqdm import tqdm

from .config import ANO, PROCESSED, RAW, UFS
from .download import session

BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_PERFIL = BASE + "/perfil_eleitor_secao/perfil_eleitor_secao_{ano}_{uf}.zip"
URL_LOCAIS = BASE + "/eleitorado_locais_votacao/eleitorado_local_votacao_{ano}.zip"
DESTINO = RAW / "eleitorado"

CSV = "read_csv(?, delim=';', quote='\"', encoding='latin-1', header=true, all_varchar=true)"

SELECT_PERFIL = f"""
SELECT
    SG_UF AS uf, CD_MUNICIPIO::INT AS cd_municipio, NR_ZONA::INT AS nr_zona, NR_SECAO::INT AS nr_secao,
    sum(QT_ELEITORES::INT) AS qt_cadastro,
    sum(QT_ELEITORES::INT) FILTER (WHERE CD_FAIXA_ETARIA::INT BETWEEN 1600 AND 2499) AS qt_16_24,
    sum(QT_ELEITORES::INT) FILTER (WHERE CD_FAIXA_ETARIA::INT >= 6064) AS qt_60_mais,
    sum(QT_ELEITORES::INT) FILTER (WHERE DS_GRAU_ESCOLARIDADE LIKE 'SUPERIOR%') AS qt_superior
FROM {CSV}
GROUP BY ALL
"""

SELECT_LOCAIS = f"""
SELECT
    NR_TURNO::INT AS turno, SG_UF AS uf, CD_MUNICIPIO::INT AS cd_municipio, NR_ZONA::INT AS nr_zona,
    NR_SECAO::INT AS nr_secao, NM_LOCAL_VOTACAO AS nm_local_votacao, DS_TIPO_LOCAL AS ds_tipo_local,
    DS_SITU_SECAO_ACESSIBILIDADE AS ds_acessibilidade, DS_TIPO_SECAO_AGREGADA AS ds_tipo_secao_agregada
FROM {CSV}
"""


def _baixar(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
    tmp.replace(dest)
    return dest


def _csv_do_zip(zip_path: Path, tmp: str, sufixo: str) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(sufixo.lower())]
        if len(nomes) != 1:
            raise RuntimeError(f"{zip_path.name}: esperado 1 arquivo *{sufixo}, encontrado {nomes}")
        csv = Path(tmp) / "dados.csv"
        with z.open(nomes[0]) as src, csv.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
    return csv


def main(argv: list[str] | None = None) -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    partes = []
    for uf in tqdm([u for u in UFS if u != "ZZ"], desc="perfil por seção", unit="UF"):
        z = _baixar(URL_PERFIL.format(ano=ANO, uf=uf), DESTINO / f"perfil_eleitor_secao_{ANO}_{uf}.zip")
        with tempfile.TemporaryDirectory(prefix="perfil_") as tmp:
            partes.append(con.sql(SELECT_PERFIL, params=[str(_csv_do_zip(z, tmp, ".csv"))]).df())
    perfil = pd.concat(partes, ignore_index=True)
    for c in ("qt_16_24", "qt_60_mais", "qt_superior"):
        perfil[c] = perfil[c].fillna(0).astype("int32")
    perfil.to_parquet(PROCESSED / "perfil_secao.parquet", index=False)
    print(f"perfil: {len(perfil):,} seções")

    z = _baixar(URL_LOCAIS.format(ano=ANO), DESTINO / f"eleitorado_local_votacao_{ANO}.zip")
    with tempfile.TemporaryDirectory(prefix="locais_") as tmp:
        locais = con.sql(SELECT_LOCAIS, params=[str(_csv_do_zip(z, tmp, "_BRASIL.csv"))]).df()
    locais.to_parquet(PROCESSED / "locais_votacao.parquet", index=False)
    print(f"locais de votação: {len(locais):,} linhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
