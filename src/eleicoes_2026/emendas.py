"""Tabelas de análise das emendas parlamentares dos deputados federais (dados de `uv run coletar-legislativo`).

A unidade principal é o deputado federal eleito em 2022: quanto ele destinou em emendas individuais na 57ª legislatura
(2023–2026), para onde, como votou na Câmara e o que aconteceu com ele na eleição de 2026.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from .config import PROCESSED

LEG = PROCESSED / "legislativo"
# A emenda do orçamento do ano N é apresentada em N−1: as de 2023 foram feitas pela legislatura anterior, e só os
# veteranos as têm. A partir de 2024 todos os eleitos em 2022 tiveram a mesma cota.
ANO_INICIO = 2024
ULTIMO_MES_ANTES_DA_ELEICAO = (2026, 9)  # 1º turno em 4/10/2026
FATIA_BASE = 0.5  # base eleitoral: menor conjunto de municípios que soma metade dos votos do deputado em 2022


def _t(nome: str) -> str:
    return f"read_parquet('{LEG / nome}.parquet')"


def pagamentos(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Pagamentos de emendas individuais dos orçamentos de 2024 a 2026 feitos até o mês anterior à eleição, com o
    deputado autor.

    Inclui restos a pagar; o ano da emenda vem da tabela principal. O autor se liga por código e nome: quem assume o
    mandato herda o código de autor do antecessor, mas as emendas trazem o nome de quem as apresentou.
    """
    con = con or duckdb.connect()
    ano, mes = ULTIMO_MES_ANTES_DA_ELEICAO
    return con.sql(f"""
        WITH ano_emenda AS (SELECT cd_emenda, min(ano) AS ano_emenda FROM {_t('emendas')} GROUP BY ALL)
        SELECT p.cd_emenda, e.ano_emenda, p.tipo, p.ano_pagamento, p.mes_pagamento, p.favorecido, p.natureza_juridica,
               p.uf_favorecido, p.cd_municipio_ibge, p.valor, a.id_camara
        FROM {_t('emendas_pagamentos')} p
        JOIN ano_emenda e USING (cd_emenda)
        LEFT JOIN {_t('ligacao_autores_emendas')} a USING (cd_autor, nm_autor)
        WHERE p.tipo LIKE 'Emenda Individual%' AND e.ano_emenda >= {ANO_INICIO}
          AND (p.ano_pagamento, p.mes_pagamento) <= ({ano}, {mes})
    """).df()


def governismo(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Fração dos votos Sim/Não de cada deputado que seguiu a orientação do Governo, 2023–2026."""
    con = con or duckdb.connect()
    return con.sql(f"""
        SELECT v.deputado_id AS id_camara, count(*) AS n_votacoes_gov,
               avg((v.voto = o.orientacao)::INT) AS governismo
        FROM {_t('camara_votos')} v
        JOIN {_t('camara_orientacoes')} o USING (idVotacao)
        WHERE o.siglaBancada = 'Governo' AND o.orientacao IN ('Sim', 'Não') AND v.voto IN ('Sim', 'Não')
        GROUP BY ALL
    """).df()


def base_eleitoral(con: duckdb.DuckDBPyConnection | None = None, ano: int = 2022) -> pd.DataFrame:
    """Municípios (código IBGE) que formam a base de cada candidato: os mais votados até somar FATIA_BASE dos votos."""
    con = con or duckdb.connect()
    return con.sql(f"""
        WITH v AS (
            SELECT v.sq_candidato, m.cd_municipio_ibge, v.votos,
                   sum(v.votos) OVER (PARTITION BY v.sq_candidato ORDER BY v.votos DESC
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS acumulado_antes,
                   sum(v.votos) OVER (PARTITION BY v.sq_candidato) AS total
            FROM {_t('votos_depfed_municipio')} v
            JOIN {_t('ligacao_municipios')} m USING (uf, cd_municipio_tse)
            WHERE v.ano = {ano} AND v.votos > 0
        )
        SELECT sq_candidato, cd_municipio_ibge, votos / total AS fatia_votos
        FROM v WHERE coalesce(acumulado_antes, 0) < {FATIA_BASE} * total
    """).df()


def painel_deputados() -> pd.DataFrame:
    """Uma linha por deputado eleito em 2022 (titular), com emendas, votação, governismo, receitas de campanha e
    resultado em 2026."""
    con = duckdb.connect()
    dep = con.sql(f"""
        SELECT id_camara, nome, uf, idLegislaturaInicial::INT < 57 AS veterano, sq_candidato_2022, sg_partido_2022, resultado_2022,
               sq_candidato_2026, sg_partido_2026, resultado_2026
        FROM {_t('ligacao_deputados')} WHERE resultado_2022 LIKE 'ELEITO%'
    """).df()

    votos = con.sql(f"""
        SELECT ano, uf, sq_candidato, sum(votos) AS votos,
               sum(votos) / sum(sum(votos)) OVER (PARTITION BY ano, uf) AS fatia_uf
        FROM {_t('votos_depfed_municipio')} GROUP BY ano, uf, sq_candidato
    """).df()
    for ano in (2022, 2026):
        v = votos[votos["ano"] == ano][["sq_candidato", "votos", "fatia_uf"]]
        dep = dep.merge(v.add_suffix(f"_{ano}"), left_on=f"sq_candidato_{ano}", right_on=f"sq_candidato_{ano}", how="left")

    pag = pagamentos(con)
    pag = pag[pag["id_camara"].notna()]
    base = base_eleitoral(con).merge(dep[["sq_candidato_2022", "id_camara"]], left_on="sq_candidato", right_on="sq_candidato_2022")
    pag = pag.merge(base[["id_camara", "cd_municipio_ibge"]].assign(na_base=True), on=["id_camara", "cd_municipio_ibge"], how="left")
    pag["na_base"] = pag["na_base"].fillna(False).astype(bool)
    pag["com_municipio"] = pag["cd_municipio_ibge"].notna() & ~pag["favorecido"].str.contains("BANCO DO BRASIL", na=False)
    pag["especial"] = pag["tipo"].str.contains("Especiais")
    pag["ano_eleitoral"] = pag["ano_pagamento"] == 2026

    v = pag.assign(
        v_especial=pag["valor"] * pag["especial"],
        v_2026=pag["valor"] * pag["ano_eleitoral"],
        v_com_mun=pag["valor"] * pag["com_municipio"],
        v_base=pag["valor"] * (pag["com_municipio"] & pag["na_base"]),
    ).groupby("id_camara")[["valor", "v_especial", "v_2026", "v_com_mun", "v_base"]].sum()
    em = pd.DataFrame({
        "emendas_pagas": v["valor"],
        "pct_especial": v["v_especial"] / v["valor"],
        "pct_pago_2026": v["v_2026"] / v["valor"],
        "pct_na_base": v["v_base"] / v["v_com_mun"],
        # orçamentos (2024–2026) com emenda própria paga: quem se licenciou (ministro, secretário) tem menos
        "anos_com_emendas": pag.groupby("id_camara")["ano_emenda"].nunique(),
    }).reset_index()
    n_base = base.groupby("id_camara").size().rename("n_municipios_base").reset_index()
    dep = (dep.merge(em, on="id_camara", how="left").merge(governismo(con), on="id_camara", how="left")
              .merge(n_base, on="id_camara", how="left"))
    dep["emendas_pagas"] = dep["emendas_pagas"].fillna(0)

    rec = pd.read_parquet(LEG / "receitas_depfed.parquet")[["sq_candidato", "tipo_prestacao", "receitas", "receitas_fefc"]]
    dep = dep.merge(rec.rename(columns={"sq_candidato": "sq_candidato_2026", "tipo_prestacao": "tipo_prestacao_2026",
                                        "receitas": "receitas_2026", "receitas_fefc": "receitas_fefc_2026"}),
                    on="sq_candidato_2026", how="left")
    dep["pct_fefc_2026"] = dep["receitas_fefc_2026"].fillna(0) / dep["receitas_2026"]

    dep["concorreu_2026"] = dep["sq_candidato_2026"].notna()
    dep["reeleito"] = dep["resultado_2026"].fillna("").str.startswith("ELEITO")
    dep["mudou_partido"] = dep["concorreu_2026"] & (dep["sg_partido_2026"] != dep["sg_partido_2022"])
    # candidatura barrada ou anulada fica com 0 voto válido: sem crescimento definido
    dep["crescimento_votos"] = np.log(dep["votos_2026"].where(dep["votos_2026"] > 0) / dep["votos_2022"])
    return dep
