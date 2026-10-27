"""Coleta os dados para cruzar emendas parlamentares com o desempenho eleitoral dos deputados federais.

Fontes:
    Portal da Transparência  emendas parlamentares (valor por emenda e município; pagamentos por mês e favorecido)
    TSE                      candidatos a deputado federal e votos por município, 2022 e 2026
    Câmara dos Deputados     deputados, votações nominais, orientações de bancada e frentes parlamentares (57ª legislatura)

Saídas (em data/processed/legislativo):
    emendas.parquet               uma linha por emenda × localidade
    emendas_pagamentos.parquet    pagamentos por emenda, mês e favorecido (com o código IBGE do município do favorecido)
    candidatos_depfed.parquet     candidatos a deputado federal, 2022 e 2026
    votos_depfed_municipio.parquet votos por candidato e município (código TSE), 2022 e 2026
    camara_deputados.parquet, camara_votacoes.parquet, camara_votos.parquet, camara_orientacoes.parquet,
    camara_frentes.parquet
    ligacao_deputados.parquet     um deputado da Câmara (56ª/57ª legislatura) por linha, com o candidato do TSE em 2022
                                  e 2026 e o código de autor das emendas
    ligacao_autores_emendas.parquet  autor da emenda (código e nome) -> deputado da Câmara
    ligacao_municipios.parquet    código de município do TSE <-> código do IBGE

Uso:
    uv run coletar-legislativo
"""

from __future__ import annotations

import difflib
import re
import shutil
import sys
import unicodedata
import tempfile
import zipfile
from pathlib import Path

import duckdb
from tqdm import tqdm

from .config import PROCESSED, RAW
from .download import session

URL_EMENDAS = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
URL_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/{tabela}/{tabela}_{ano}.zip"
URL_IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_CAMARA = "https://dadosabertos.camara.leg.br/arquivos/{tabela}/csv/{tabela}{sufixo}.csv"
ANOS_ELEICAO = (2022, 2026)
ANOS_LEGISLATURA = (2023, 2024, 2025, 2026)  # 57ª legislatura
CD_CARGO_DEPUTADO_FEDERAL = "6"
ANO_INICIO_EMENDAS = 2023  # só se ligam autores com emendas a partir deste ano (orçamentos da 57ª legislatura)

SAIDA = PROCESSED / "legislativo"


def _csv(sep: str = ";", encoding: str = "latin-1") -> str:
    return f"read_csv(?, delim='{sep}', quote='\"', encoding='{encoding}', header=true, all_varchar=true)"


def _int(col: str) -> str:
    # O nullif impede o DuckDB 2.0 de empurrar o TRY_CAST para dentro do leitor de CSV, onde ele vira um CAST
    # estrito e falha em valores como "Sem informação".
    return f"TRY_CAST(nullif({col}, '') AS INT)"


def _reais(col: str) -> str:
    """'1.234,56' -> 1234.56"""
    return f"TRY_CAST(replace(replace({col}, '.', ''), ',', '.') AS DOUBLE)"


SELECT_EMENDAS = f"""
SELECT
    "Código da Emenda"                      AS cd_emenda,
    {_int('"Ano da Emenda"')}        AS ano,
    "Tipo de Emenda"                        AS tipo,
    "Código do Autor da Emenda"             AS cd_autor,
    "Nome do Autor da Emenda"               AS nm_autor,
    "Número da emenda"                      AS nr_emenda,
    "Localidade de aplicação do recurso"    AS localidade,
    {_int('"Código Município IBGE"')} AS cd_municipio_ibge,
    "Município"                             AS nm_municipio,
    "UF"                                    AS nm_uf,
    "Nome Função"                           AS funcao,
    "Nome Subfunção"                        AS subfuncao,
    "Nome Programa"                         AS programa,
    "Nome Ação"                             AS acao,
    {_reais('"Valor Empenhado"')}           AS valor_empenhado,
    {_reais('"Valor Liquidado"')}           AS valor_liquidado,
    {_reais('"Valor Pago"')}                AS valor_pago,
    {_reais('"Valor Restos A Pagar Inscritos"')}  AS valor_rap_inscrito,
    {_reais('"Valor Restos A Pagar Cancelados"')} AS valor_rap_cancelado,
    {_reais('"Valor Restos A Pagar Pagos"')}      AS valor_rap_pago
FROM {_csv()}
"""

SELECT_PAGAMENTOS = f"""
SELECT
    "Código da Emenda"           AS cd_emenda,
    "Código do Autor da Emenda"  AS cd_autor,
    "Nome do Autor da Emenda"    AS nm_autor,
    "Tipo de Emenda"             AS tipo,
    {_int('substr("Ano/Mês", 1, 4)')} AS ano_pagamento,
    {_int('substr("Ano/Mês", 5, 2)')} AS mes_pagamento,
    "Código do Favorecido"       AS cd_favorecido,
    "Favorecido"                 AS favorecido,
    "Natureza Jurídica"          AS natureza_juridica,
    "Tipo Favorecido"            AS tipo_favorecido,
    "UF Favorecido"              AS uf_favorecido,
    "Município Favorecido"       AS municipio_favorecido,
    {_reais('"Valor Recebido"')} AS valor
FROM {_csv()}
"""

SELECT_CANDIDATOS = f"""
SELECT
    ANO_ELEICAO::INT AS ano, SG_UF AS uf, SQ_CANDIDATO AS sq_candidato, NR_CANDIDATO AS nr_candidato,
    NM_CANDIDATO AS nm_candidato, NM_URNA_CANDIDATO AS nm_urna, NR_CPF_CANDIDATO AS cpf,
    TRY_STRPTIME(DT_NASCIMENTO, '%d/%m/%Y')::DATE AS dt_nascimento,
    SG_PARTIDO AS sg_partido, SG_FEDERACAO AS sg_federacao, DS_SITUACAO_CANDIDATURA AS situacao_candidatura,
    DS_GENERO AS genero, DS_GRAU_INSTRUCAO AS grau_instrucao, DS_COR_RACA AS cor_raca, DS_OCUPACAO AS ocupacao,
    DS_SIT_TOT_TURNO AS resultado
FROM {_csv()}
WHERE CD_CARGO = '{CD_CARGO_DEPUTADO_FEDERAL}'
"""

SELECT_VOTOS = f"""
SELECT
    ANO_ELEICAO::INT AS ano, SG_UF AS uf, CD_MUNICIPIO::INT AS cd_municipio_tse, NM_MUNICIPIO AS nm_municipio,
    SQ_CANDIDATO AS sq_candidato, SG_PARTIDO AS sg_partido,
    sum({_int('QT_VOTOS_NOMINAIS_VALIDOS')}) AS votos
FROM {_csv()}
WHERE CD_CARGO = '{CD_CARGO_DEPUTADO_FEDERAL}'
GROUP BY ALL
"""


def _baixar(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
    tmp.replace(dest)
    return dest


def _do_zip(con: duckdb.DuckDBPyConnection, zip_path: Path, membro: str, sql: str):
    """Extrai um CSV do zip num diretório temporário próprio e roda `sql` sobre ele."""
    with tempfile.TemporaryDirectory(prefix="legis_") as tmp, zipfile.ZipFile(zip_path) as z:
        csv = Path(tmp) / "dados.csv"
        with z.open(membro) as src, csv.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
        return con.sql(sql, params=[str(csv)]).df()


def _gravar(df, nome: str) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SAIDA / f"{nome}.parquet", index=False)
    print(f"   {nome}: {len(df):,} linhas")


def emendas(con) -> None:
    print("Portal da Transparência: emendas parlamentares")
    z = _baixar(URL_EMENDAS, RAW / "emendas" / "EmendasParlamentares.zip")
    _gravar(_do_zip(con, z, "EmendasParlamentares.csv", SELECT_EMENDAS), "emendas")
    pag = _do_zip(con, z, "EmendasParlamentares_PorFavorecido.csv", SELECT_PAGAMENTOS)
    # Município do favorecido -> código IBGE. Cuidado: quando o favorecido é um intermediário (ex.: Banco do Brasil,
    # em Brasília, em parte das transferências com finalidade definida), esse não é o município beneficiado.
    ibge = _municipios_ibge()
    chave = ibge["uf"] + "|" + ibge["nm_municipio_ibge"].map(normalizar)
    pag["cd_municipio_ibge"] = (pag["uf_favorecido"].astype(str) + "|" + pag["municipio_favorecido"].map(normalizar)).map(
        dict(zip(chave, ibge["cd_municipio_ibge"]))
    ).astype("Int64")
    _gravar(pag, "emendas_pagamentos")


def tse(con) -> None:
    import pandas as pd

    print("TSE: candidatos e votos por município (deputado federal)")
    cands, votos = [], []
    for ano in tqdm(ANOS_ELEICAO, desc="TSE", unit="eleição"):
        z = _baixar(URL_TSE.format(tabela="consulta_cand", ano=ano), RAW / "tse" / f"consulta_cand_{ano}.zip")
        cands.append(_do_zip(con, z, f"consulta_cand_{ano}_BRASIL.csv", SELECT_CANDIDATOS))
        tabela = "votacao_candidato_munzona"
        z = _baixar(URL_TSE.format(tabela=tabela, ano=ano), RAW / "tse" / f"{tabela}_{ano}.zip")
        votos.append(_do_zip(con, z, f"{tabela}_{ano}_BRASIL.csv", SELECT_VOTOS))
    _gravar(pd.concat(cands, ignore_index=True), "candidatos_depfed")
    _gravar(pd.concat(votos, ignore_index=True), "votos_depfed_municipio")


def camara(con) -> None:
    import pandas as pd

    print("Câmara dos Deputados: deputados, votações, orientações e frentes")
    pasta = RAW / "camara"

    def ler(tabela: str, sufixo: str = ""):
        arq = _baixar(URL_CAMARA.format(tabela=tabela, sufixo=sufixo), pasta / f"{tabela}{sufixo}.csv")
        return con.sql(f"SELECT * FROM {_csv(encoding='utf-8')}", params=[str(arq)]).df()

    _gravar(ler("deputados"), "camara_deputados")
    for tabela, nome in (("votacoes", "camara_votacoes"), ("votacoesVotos", "camara_votos"),
                         ("votacoesOrientacoes", "camara_orientacoes")):
        partes = [ler(tabela, f"-{ano}") for ano in tqdm(ANOS_LEGISLATURA, desc=tabela, unit="ano")]
        _gravar(pd.concat(partes, ignore_index=True), nome)
    _gravar(ler("frentesDeputados"), "camara_frentes")


# --------------------------------------------------------------------------- ligações entre as bases


def normalizar(nome) -> str:
    """'José D'Ávila  Jr.' -> 'JOSE D AVILA JR' (sem acento, só letras maiúsculas e espaços simples)."""
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z]", " ", s).split())


def _autor_atual(nome: str) -> str:
    """'DEP. FULANO' -> 'FULANO'; 'FULANO (EX-PARLAMENTAR BELTRANO, NOS TERMOS ...)' -> 'FULANO'."""
    return normalizar(re.sub(r"^DEP\.?\s+", "", nome.split("(")[0].strip()))


def _autor_original(nome: str) -> str | None:
    m = re.search(r"\(EX-PARLAMENTAR ([^,)]+)", nome)
    return normalizar(m.group(1)) if m else None


SUFIXOS_FAMILIA = {"FILHO", "JUNIOR", "JR", "NETO", "SOBRINHO"}
# autores cujo nome nas emendas não bate com nenhum nome da Câmara
APELIDOS_AUTOR = {"YURY DO PAREDAO": "YURY BRUNO"}


def _achar_deputado(nome: str, ano_max: int, uf: str | None, dep) -> tuple[str | None, str | None]:
    """Deputado da Câmara para um autor de emenda: (id_camara, método) ou (None, None) se não for deputado.

    A emenda do ano N é apresentada no ano N-1, então emendas de 2023 são da 56ª legislatura; isso desempata
    homônimos (ex.: dois "Átila Lira").
    """
    leg = 56 if ano_max <= 2023 else 57
    for col, metodo in (("nome_norm", "nome parlamentar"), ("civil_norm", "nome civil")):
        c = dep[dep[col] == nome]
        if len(c) > 1:
            c = c[c["idLegislaturaFinal"].astype(int) >= leg]
            c = c[c["idLegislaturaInicial"].astype(int) <= leg]
        if len(c) == 1:
            return c["id_camara"].iat[0], metodo
    # Grafia diferente ("PAULO FOLETTO" x "PAULO FOLLETTO") ou um nome contido no outro ("FAUSTO SANTOS JR." x
    # "FAUSTO JR."). Para evitar trocar pai por filho ("OTTO ALENCAR", senador, x "OTTO ALENCAR FILHO", deputado),
    # só aceita candidato único, da mesma UF para onde o autor mandou a maior parte das emendas, e cujos nomes não
    # diferem só por FILHO/JUNIOR/NETO.
    if uf is None:
        return None, None
    c = dep[(dep["uf"] == uf) & (dep["idLegislaturaFinal"].astype(int) >= leg)]
    if c.empty:
        return None, None
    tokens = set(nome.split())

    def mesma_geracao(n: str) -> bool:  # um tem FILHO/JUNIOR/NETO e o outro não: provavelmente pai e filho
        return (set(n.split()) & SUFIXOS_FAMILIA) == (tokens & SUFIXOS_FAMILIA)

    def compativel(n: str) -> bool:
        t = set(n.split())
        if not mesma_geracao(n):
            return False
        return difflib.SequenceMatcher(None, n, nome).ratio() >= 0.9 or (len(t) >= 2 and (t <= tokens or tokens <= t))

    # o nome do autor também pode estar contido no nome civil ("RAFAEL BENTO" x "RAFAEL BENTO PEREIRA", o "Rafael Fera")
    no_civil = c["civil_norm"].map(lambda n: len(tokens) >= 2 and tokens <= set(n.split()) and mesma_geracao(n)).astype(bool)
    c = c[c["nome_norm"].map(compativel).astype(bool) | no_civil]
    if len(c) == 1:
        return c["id_camara"].iat[0], "nome parecido, mesma UF"
    return None, None


def ligar_deputados():
    """Liga cada deputado da Câmara ao seu registro de candidato no TSE (2022 e 2026) e ao autor das emendas.

    Câmara -> TSE: nome civil + data de nascimento. Quando não bate exato (nome civil grafado diferente),
    usa a mesma data de nascimento e UF com o nome civil ou de urna mais parecido (similaridade >= 0,6) e, por
    fim, o mesmo nome civil ou de urna na mesma UF.
    Emendas -> Câmara: nome do autor contra o nome parlamentar (os autores que sobram são senadores e bancadas).
    """
    import pandas as pd

    dep = pd.read_parquet(SAIDA / "camara_deputados.parquet")
    dep = dep[dep["idLegislaturaFinal"].astype(int) >= 56].copy()
    dep["id_camara"] = dep["uri"].str.rsplit("/", n=1).str[1]
    dep["nome_norm"] = dep["nome"].map(normalizar)
    dep["civil_norm"] = dep["nomeCivil"].map(normalizar)
    dep["dt_nascimento"] = pd.to_datetime(dep["dataNascimento"].replace("", None))
    votos = pd.read_parquet(SAIDA / "camara_votos.parquet", columns=["deputado_id", "deputado_siglaUf", "deputado_siglaPartido", "dataHoraVoto"])
    ult = votos.sort_values("dataHoraVoto").groupby("deputado_id").last()
    dep["uf"] = dep["id_camara"].map(ult["deputado_siglaUf"])
    dep["partido_camara"] = dep["id_camara"].map(ult["deputado_siglaPartido"])

    cand = pd.read_parquet(SAIDA / "candidatos_depfed.parquet")
    cand["civil_norm"] = cand["nm_candidato"].map(normalizar)
    cand["urna_norm"] = cand["nm_urna"].map(normalizar)
    cand["dt_nascimento"] = pd.to_datetime(cand["dt_nascimento"])
    # o mesmo candidato pode ter mais de uma linha (substituição, recurso): fica a de candidatura deferida
    cand["_ordem"] = (~cand["situacao_candidatura"].eq("APTO")).astype(int)
    cand = cand.sort_values("_ordem").drop_duplicates(["ano", "cpf"])

    for ano in ANOS_ELEICAO:
        c = cand[cand["ano"] == ano]
        exato = c.drop_duplicates(["civil_norm", "dt_nascimento"], keep=False).set_index(["civil_norm", "dt_nascimento"])
        chave = pd.MultiIndex.from_frame(dep[["civil_norm", "dt_nascimento"]])
        sq = pd.Series(exato["sq_candidato"].reindex(chave).to_numpy(), index=dep.index)
        metodo = pd.Series(sq.notna().map({True: "nome+nascimento", False: None}), index=dep.index)
        por_nasc = c.groupby("dt_nascimento")
        for i in dep.index[sq.isna() & dep["dt_nascimento"].notna()]:
            if dep.at[i, "dt_nascimento"] not in por_nasc.groups:
                continue
            g = por_nasc.get_group(dep.at[i, "dt_nascimento"])
            if pd.notna(dep.at[i, "uf"]):
                g = g[g["uf"] == dep.at[i, "uf"]]
            if g.empty:
                continue
            def parecido(a: str, b: str) -> float:
                return difflib.SequenceMatcher(None, a, b).ratio()
            sim = pd.concat([g["civil_norm"].map(lambda n: parecido(n, dep.at[i, "civil_norm"])),
                             g["urna_norm"].map(lambda n: parecido(n, dep.at[i, "nome_norm"]))], axis=1).max(axis=1)
            if sim.max() >= 0.6:
                sq[i], metodo[i] = g.loc[sim.idxmax(), "sq_candidato"], "nascimento+nome parecido"
        # último recurso (data de nascimento divergente entre as bases): mesmo nome civil ou de urna, na mesma UF
        for col_dep, col_tse in (("civil_norm", "civil_norm"), ("nome_norm", "urna_norm")):
            unico = c.drop_duplicates(["uf", col_tse], keep=False).set_index(["uf", col_tse])["sq_candidato"]
            falta = sq.isna() & dep["uf"].notna()
            achado = unico.reindex(pd.MultiIndex.from_frame(dep.loc[falta, ["uf", col_dep]])).to_numpy()
            sq[falta], metodo[falta] = achado, pd.Series(achado, index=dep.index[falta]).notna().map({True: "UF+nome", False: None})
        dep[f"sq_candidato_{ano}"], dep[f"ligacao_tse_{ano}"] = sq, metodo
        dep = dep.merge(
            c.set_index("sq_candidato")[["cpf", "sg_partido", "resultado"]].add_suffix(f"_{ano}"),
            left_on=f"sq_candidato_{ano}", right_index=True, how="left",
        )

    em = pd.read_parquet(SAIDA / "emendas.parquet", columns=["cd_autor", "nm_autor", "ano", "nm_uf"])
    autores = em.groupby(["cd_autor", "nm_autor"])["ano"].agg(["min", "max"]).reset_index()
    autores = autores[autores["max"] >= ANO_INICIO_EMENDAS]
    sigla = _municipios_ibge().drop_duplicates("nm_uf").set_index("nm_uf")["uf"]
    sigla.index = sigla.index.map(normalizar)
    em["uf"] = em["nm_uf"].map(normalizar).map(sigla)
    uf_autor = em.dropna(subset=["uf"]).groupby(["cd_autor", "nm_autor"])["uf"].agg(lambda s: s.mode().iat[0])
    autores["uf_emendas"] = pd.MultiIndex.from_frame(autores[["cd_autor", "nm_autor"]]).map(uf_autor.to_dict().get)
    autores["autor_norm"] = autores["nm_autor"].map(_autor_atual).replace(APELIDOS_AUTOR)
    autores["autor_original_norm"] = autores["nm_autor"].map(_autor_original)
    achados = [_achar_deputado(n, m, u, dep) for n, m, u in zip(autores["autor_norm"], autores["max"], autores["uf_emendas"])]
    autores["id_camara"] = [a for a, _ in achados]
    autores["ligacao"] = [b for _, b in achados]
    autores["id_camara_original"] = [
        _achar_deputado(n, m, u, dep)[0] if isinstance(n, str) else None
        for n, m, u in zip(autores["autor_original_norm"], autores["max"], autores["uf_emendas"])
    ]
    cods = autores.dropna(subset=["id_camara"]).groupby("id_camara")["cd_autor"].agg(lambda s: sorted(set(s)))
    dep["cd_autor_emendas"] = dep["id_camara"].map(cods)

    dep["dt_nascimento"] = dep["dt_nascimento"].dt.date
    cols = ["id_camara", "nome", "nomeCivil", "dt_nascimento", "uf", "partido_camara", "idLegislaturaInicial",
            "idLegislaturaFinal", "cd_autor_emendas"]
    cols += [c for c in dep.columns if c.endswith(("_2022", "_2026"))]
    _gravar(dep[cols].rename(columns={"nomeCivil": "nome_civil"}), "ligacao_deputados")
    _gravar(autores, "ligacao_autores_emendas")


def _municipios_ibge():
    """Municípios do IBGE (código, nome, sigla e nome da UF), com cópia local em data/raw/ibge."""
    import json

    import pandas as pd
    import requests

    arq = RAW / "ibge" / "municipios.json"
    if not arq.exists():
        r = requests.get(URL_IBGE, timeout=60)  # sem a sessão do projeto: o IBGE recusa (HTTP 400) User-Agent com acento
        r.raise_for_status()
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(r.text, encoding="utf-8")
    linhas = []
    for m in json.loads(arq.read_text(encoding="utf-8")):
        reg = m.get("microrregiao") or {}
        uf = (reg.get("mesorregiao") or {}).get("UF") or m["regiao-imediata"]["regiao-intermediaria"]["UF"]
        linhas.append({"cd_municipio_ibge": int(m["id"]), "nm_municipio_ibge": m["nome"], "uf": uf["sigla"], "nm_uf": uf["nome"]})
    return pd.DataFrame(linhas)


# Municípios cujo nome no TSE difere do nome no IBGE (UF|nome normalizado no TSE -> idem no IBGE).
NOMES_TSE_IBGE = {"RR|SAO LUIZ": "RR|SAO LUIZ DO ANAUA", "RN|BOA SAUDE": "RN|JANUARIO CICCO"}


def ligar_municipios():
    """Código de município do TSE <-> IBGE, por UF + nome normalizado (com correções para nomes diferentes)."""
    import pandas as pd

    ibge = _municipios_ibge().drop(columns="nm_uf")
    ibge["k"] = ibge["uf"] + "|" + ibge["nm_municipio_ibge"].map(normalizar)
    tse_m = pd.read_parquet(SAIDA / "votos_depfed_municipio.parquet", columns=["uf", "cd_municipio_tse", "nm_municipio"])
    tse_m = tse_m[tse_m["uf"] != "ZZ"].drop_duplicates(["cd_municipio_tse"])
    tse_m["k"] = tse_m["uf"] + "|" + tse_m["nm_municipio"].map(normalizar)
    tse_m["k"] = tse_m["k"].replace(NOMES_TSE_IBGE)
    lig = tse_m.merge(ibge.drop(columns="uf"), on="k", how="left")
    faltam = lig["cd_municipio_ibge"].isna()
    if faltam.any():  # grafias diferentes: nome do IBGE mais parecido na mesma UF
        for i in lig.index[faltam]:
            g = ibge[ibge["uf"] == lig.at[i, "uf"]]
            nome = lig.at[i, "k"]
            sim = g["k"].map(lambda k: difflib.SequenceMatcher(None, k, nome).ratio())
            if sim.max() >= 0.85:
                lig.at[i, "cd_municipio_ibge"] = g.loc[sim.idxmax(), "cd_municipio_ibge"]
                lig.at[i, "nm_municipio_ibge"] = g.loc[sim.idxmax(), "nm_municipio_ibge"]
    lig["cd_municipio_ibge"] = lig["cd_municipio_ibge"].astype("Int64")
    _gravar(lig.drop(columns="k"), "ligacao_municipios")


def main(argv: list[str] | None = None) -> int:
    con = duckdb.connect()
    emendas(con)
    tse(con)
    camara(con)
    print("Ligações entre as bases")
    ligar_municipios()
    ligar_deputados()
    return 0


if __name__ == "__main__":
    sys.exit(main())
