"""Modelo da urna (UE2013, UE2015, UE2020, UE2022) de cada seção do 1º turno de 2026.

O CSV do BU publicado pelo TSE não traz o modelo. O BU binário (ASN.1) traz, e o certificado digital da urna também. O
projeto DataUrnas-BR (https://github.com/alissonlinneker/DataUrnas-BR, licença MIT) decodificou os BUs binários de
todas as seções e conferiu o modelo com o certificado. Esta etapa baixa a tabela de seções dele numa versão fixa e confere
com o nosso BU: a seção e o número interno da urna precisam bater.

Como o modelo é uma propriedade da urna física, a tabela também guarda o modelo por número de urna, que serve para o 2º
turno (a maioria das seções usa a mesma urna nos dois turnos).

Uso:
    uv run modelo-urna
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import duckdb

from .config import PROCESSED
from .download import session

VERSAO = "12f0433bd20882d305dd7b9e4987d6dcf3b321a9"  # commit de 15/10/2026
URL = f"https://raw.githubusercontent.com/alissonlinneker/DataUrnas-BR/{VERSAO}/data/parquet/2026/secoes_2026.parquet"
SAIDA = PROCESSED / "modelo_urna.parquet"


def main(argv: list[str] | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="dataurnas_") as tmp:
        arq = Path(tmp) / "secoes_2026.parquet"
        with session.get(URL, timeout=300) as r:
            r.raise_for_status()
            arq.write_bytes(r.content)
        con = duckdb.connect()
        # seções agregadas a outra não têm BU próprio nem modelo
        con.sql(f"""
            CREATE TABLE du AS
            SELECT upper(uf) AS uf, cd_mun::INT AS cd_municipio, zona::INT AS nr_zona, secao::INT AS nr_secao,
                   numero_interno_urna AS nr_urna, modelo_urna
            FROM read_parquet('{arq}') WHERE modelo_urna IS NOT NULL
        """)
    nosso = PROCESSED / "secoes_1t.parquet"
    conf = con.execute(f"""
        SELECT count(*) AS secoes, count(du.nr_urna) AS casadas,
               count(*) FILTER (du.nr_urna = TRY_CAST(s.nr_urna_efetivada AS BIGINT)) AS mesma_urna
        FROM read_parquet('{nosso}') s LEFT JOIN du USING (uf, cd_municipio, nr_zona, nr_secao)
    """).fetchall()[0]
    print(f"seções do nosso BU: {conf[0]:,}; com modelo: {conf[1]:,}; mesmo número de urna: {conf[2]:,}")
    if conf[2] < 0.99 * conf[0]:
        raise SystemExit("a tabela do DataUrnas-BR não confere com o BU do TSE; nada foi gravado")
    if con.execute("SELECT count(DISTINCT modelo_urna) FROM du GROUP BY nr_urna ORDER BY 1 DESC LIMIT 1").fetchall()[0][0] > 1:
        raise SystemExit("um mesmo número de urna aparece com dois modelos; nada foi gravado")
    con.sql(f"COPY (SELECT * FROM du ORDER BY ALL) TO '{SAIDA}'")
    print(f"gravado {SAIDA}")
    print(con.sql("SELECT modelo_urna, count(*) AS secoes FROM du GROUP BY 1 ORDER BY 1"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
