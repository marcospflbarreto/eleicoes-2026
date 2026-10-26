"""Converte os zips de BU em tabelas Parquet só com o cargo Presidente.

Saídas (em data/processed):
    bu_presidente_{t}t.parquet  formato longo: uma linha por (seção, votável)
    secoes_{t}t.parquet         formato largo: uma linha por seção, uma coluna por candidato

Uso:
    uv run processar              # processa tudo o que já foi baixado
    uv run processar --turno 1
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
from tqdm import tqdm

from .config import CD_CARGO_PRESIDENTE, INTERIM, PROCESSED, RAW, REGIAO

CHAVE = ["turno", "uf", "cd_municipio", "nr_zona", "nr_secao"]

SELECT_BU = f"""
SELECT
    NR_TURNO::INT                                  AS turno,
    SG_UF                                          AS uf,
    CD_MUNICIPIO::INT                              AS cd_municipio,
    NM_MUNICIPIO                                   AS nm_municipio,
    NR_ZONA::INT                                   AS nr_zona,
    NR_SECAO::INT                                  AS nr_secao,
    TRY_CAST(NR_LOCAL_VOTACAO AS INT)              AS nr_local_votacao,
    TRY_CAST(QT_APTOS AS INT)                      AS qt_aptos,
    TRY_CAST(QT_COMPARECIMENTO AS INT)             AS qt_comparecimento,
    TRY_CAST(QT_ABSTENCOES AS INT)                 AS qt_abstencoes,
    TRY_CAST(CD_TIPO_URNA AS INT)                  AS cd_tipo_urna,
    DS_TIPO_URNA                                   AS ds_tipo_urna,
    TRY_CAST(CD_TIPO_VOTAVEL AS INT)               AS cd_tipo_votavel,
    DS_TIPO_VOTAVEL                                AS ds_tipo_votavel,
    TRY_CAST(NR_VOTAVEL AS INT)                    AS nr_votavel,
    NM_VOTAVEL                                     AS nm_votavel,
    SG_PARTIDO                                     AS sg_partido,
    TRY_CAST(QT_VOTOS AS INT)                      AS qt_votos,
    NULLIF(NR_URNA_EFETIVADA, '#NULO#')            AS nr_urna_efetivada,
    NULLIF(CD_CARGA_1_URNA_EFETIVADA, '#NULO#')    AS cd_carga_1,
    NULLIF(CD_CARGA_2_URNA_EFETIVADA, '#NULO#')    AS cd_carga_2,
    NULLIF(CD_FLASHCARD_URNA_EFETIVADA, '#NULO#')  AS cd_flashcard,
    TRY_CAST(DT_CARGA_URNA_EFETIVADA AS TIMESTAMP) AS dt_carga_urna,
    NULLIF(DS_SECOES_AGREGADAS, '#NULO#')          AS ds_secoes_agregadas,
    TRY_CAST(DT_ABERTURA AS TIMESTAMP)             AS dt_abertura,
    TRY_CAST(DT_ENCERRAMENTO AS TIMESTAMP)         AS dt_encerramento,
    TRY_CAST(DT_EMISSAO_BU AS TIMESTAMP)           AS dt_emissao_bu,
    TRY_CAST(DT_BU_RECEBIDO AS TIMESTAMP)          AS dt_bu_recebido,
    TRY_CAST(QT_ELEI_BIOM_SEM_HABILITACAO AS INT)  AS qt_biom_sem_hab,
    TRY_CAST(NR_JUNTA_APURADORA AS INT)            AS nr_junta,
    TRY_CAST(NR_TURMA_APURADORA AS INT)            AS nr_turma
FROM read_csv(?, delim=';', quote='"', encoding='latin-1', header=true, all_varchar=true)
WHERE CD_CARGO_PERGUNTA = '{CD_CARGO_PRESIDENTE}'
"""

ATRIBUTOS_SECAO = [
    "nm_municipio", "nr_local_votacao", "qt_aptos", "qt_comparecimento", "qt_abstencoes",
    "cd_tipo_urna", "ds_tipo_urna", "nr_urna_efetivada", "cd_carga_1", "cd_carga_2", "cd_flashcard",
    "dt_carga_urna", "ds_secoes_agregadas", "dt_abertura", "dt_encerramento", "dt_emissao_bu",
    "dt_bu_recebido", "qt_biom_sem_hab", "nr_junta", "nr_turma",
]


def zip_para_parquet(zip_path: Path, saida: Path) -> None:
    """Extrai o CSV do zip (num diretório temporário próprio) e grava só o cargo Presidente."""
    with tempfile.TemporaryDirectory(prefix="bweb_") as tmp, zipfile.ZipFile(zip_path) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv") and "/" not in n.strip("/")]
        if len(csvs) != 1:
            raise RuntimeError(f"{zip_path.name}: esperado 1 CSV, encontrado {csvs}")
        csv = Path(tmp) / "bweb.csv"
        with z.open(csvs[0]) as src, csv.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
        con = duckdb.connect()
        rel = con.sql(SELECT_BU, params=[str(csv)])
        saida.parent.mkdir(parents=True, exist_ok=True)
        rel.write_parquet(str(saida), compression="zstd")
        con.close()


def montar_secoes(longo: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por seção, com uma coluna de votos por candidato + brancos/nulos."""
    attrs = longo.groupby(CHAVE, sort=False)[ATRIBUTOS_SECAO].first()
    rotulo = longo["nm_votavel"].astype(str).where(
        longo["cd_tipo_votavel"] == 1, longo["ds_tipo_votavel"].astype(str).str.upper()
    )
    votos = (
        longo.assign(rotulo=rotulo)
        .pivot_table(index=CHAVE, columns="rotulo", values="qt_votos", aggfunc="sum", fill_value=0)
        .astype("int32")
    )
    votos.columns.name = None
    candidatos = [c for c in votos.columns if c not in ("BRANCO", "NULO")]
    for col in ("BRANCO", "NULO"):
        if col not in votos:
            votos[col] = 0
    df = attrs.join(votos).reset_index()
    df["votos_validos"] = df[candidatos].sum(axis=1)
    df["votos_total"] = df["votos_validos"] + df["BRANCO"] + df["NULO"]
    df["regiao"] = df["uf"].map(REGIAO)
    df["sec_id"] = (
        df["uf"].astype(str) + "-" + df["cd_municipio"].astype(str) + "-" + df["nr_zona"].astype(str) + "-" + df["nr_secao"].astype(str)
    )
    df.attrs["candidatos"] = candidatos
    return df


def _ordem(z: Path) -> str:
    """bweb_1t_AC_051020261403 -> 202610051403 (carimbo ordenável)."""
    ts = z.stem.split("_")[3]
    return ts[4:8] + ts[2:4] + ts[0:2] + ts[8:]


def processar_turno(turno: int, refazer: bool = False) -> bool:
    zips = sorted((RAW / f"{turno}t").glob(f"bweb_{turno}t_*.zip"))
    if not zips:
        print(f"{turno}º turno: nenhum zip em {RAW / f'{turno}t'} (rode `uv run baixar`)")
        return False
    # se houver mais de uma versão da mesma UF, fica a de carimbo mais recente
    por_uf: dict[str, Path] = {}
    for z in sorted(zips, key=_ordem):
        por_uf[z.stem.split("_")[2]] = z
    parquets = []
    for uf, z in tqdm(sorted(por_uf.items()), desc=f"{turno}º turno", unit="UF"):
        out = INTERIM / f"{turno}t" / f"{z.stem}.parquet"
        if refazer or not out.exists():
            # remove versões antigas da mesma UF
            for velho in out.parent.glob(f"bweb_{turno}t_{uf}_*.parquet"):
                velho.unlink()
            zip_para_parquet(z, out)
        parquets.append(out)

    longo = pd.concat([pd.read_parquet(p) for p in parquets], ignore_index=True)
    for c in ("uf", "nm_municipio", "ds_tipo_urna", "ds_tipo_votavel", "nm_votavel", "sg_partido"):
        longo[c] = longo[c].astype("category")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    longo.to_parquet(PROCESSED / f"bu_presidente_{turno}t.parquet", index=False)
    secoes = montar_secoes(longo)
    secoes.to_parquet(PROCESSED / f"secoes_{turno}t.parquet", index=False)
    print(f"{turno}º turno: {len(por_uf)} UFs, {len(secoes):,} seções, {int(secoes['votos_total'].sum()):,} votos")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--turno", type=int, nargs="+", default=[1, 2], choices=[1, 2])
    p.add_argument("--refazer", action="store_true", help="reprocessa mesmo os parquet já existentes")
    a = p.parse_args(argv)
    for t in a.turno:
        processar_turno(t, a.refazer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
