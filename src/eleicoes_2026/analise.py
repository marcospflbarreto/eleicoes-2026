"""Funções de análise compartilhadas pelos notebooks.

Tudo aqui opera sobre a tabela de seções (data/processed/secoes_{t}t.parquet), uma linha por
seção eleitoral, com colunas de votos por candidato.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .config import PROCESSED

CHAVE_SECAO = ["uf", "cd_municipio", "nr_zona", "nr_secao"]
CHAVE_LOCAL = ["uf", "cd_municipio", "nr_zona", "nr_local_votacao"]
NAO_CANDIDATOS = {"BRANCO", "NULO"}

# Os horários de abertura, encerramento e emissão do BU vêm no fuso LOCAL da seção. Como a votação
# abre às 8h de Brasília em todo o país, o fuso de cada município é inferido pela hora de abertura
# mais comum ali (ex.: 6h no AC e no oeste do AM => -2h). Um valor fixo por UF erraria no AM, que
# tem dois fusos. O exterior (ZZ) fica sem conversão.
HORA_ABERTURA_BSB = 8


# --------------------------------------------------------------------------- carga


def carregar_secoes(turno: int) -> pd.DataFrame | None:
    """Lê a tabela de seções de um turno; devolve None se o turno ainda não foi processado."""
    path = PROCESSED / f"secoes_{turno}t.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["comparecimento_pct"] = df["qt_comparecimento"] / df["qt_aptos"]
    hora = df["dt_abertura"].dt.hour
    moda = hora.groupby([df["uf"], df["cd_municipio"]], observed=True).transform(lambda h: h.mode().iat[0] if h.notna().any() else np.nan)
    df["fuso_inferido_h"] = (moda - HORA_ABERTURA_BSB).clip(-3, 1)
    fuso = pd.to_timedelta(df["fuso_inferido_h"].fillna(0), unit="h")
    for col in ("dt_abertura", "dt_encerramento", "dt_emissao_bu"):
        df[col + "_bsb"] = (df[col] - fuso).where(df["uf"] != "ZZ")
    return df


def candidatos(df: pd.DataFrame) -> list[str]:
    """Colunas de candidatos, ordenadas pelo total de votos (maior primeiro)."""
    meta = set(df.columns) - NAO_CANDIDATOS
    cols = [
        c for c in df.columns
        if c.isupper() and c not in NAO_CANDIDATOS and c in meta and pd.api.types.is_integer_dtype(df[c])
    ]
    return list(df[cols].sum().sort_values(ascending=False).index)


def principais(df: pd.DataFrame, n: int = 2) -> list[str]:
    return candidatos(df)[:n]


def resultado(df: pd.DataFrame, por: str | list[str] | None = None) -> pd.DataFrame:
    """Votos e % de votos válidos por candidato (opcionalmente agrupado)."""
    cands = candidatos(df)
    if por is None:
        tot = df[cands].sum()
        out = pd.DataFrame({"votos": tot, "pct_validos": tot / tot.sum() * 100})
        return out.sort_values("votos", ascending=False)
    g = df.groupby(por, observed=True)[cands].sum()
    return g.div(g.sum(axis=1), axis=0) * 100


def margem(df: pd.DataFrame) -> tuple[str, str, int]:
    """(vencedor, segundo, diferença de votos entre os dois)."""
    a, b = principais(df, 2)
    return a, b, int(df[a].sum() - df[b].sum())


# --------------------------------------------------------------------------- consistência


def checar_consistencia(df: pd.DataFrame) -> pd.DataFrame:
    """Testes aritméticos que todo BU deveria satisfazer. Retorna contagem de violações."""
    testes = {
        "comparecimento + abstenções = aptos": df["qt_comparecimento"] + df["qt_abstencoes"] != df["qt_aptos"],
        "votos (cand+branco+nulo) = comparecimento": df["votos_total"] != df["qt_comparecimento"],
        "comparecimento <= aptos": df["qt_comparecimento"] > df["qt_aptos"],
        "seção sem aptos": df["qt_aptos"].fillna(0) <= 0,
        "seção duplicada": df.duplicated(CHAVE_SECAO, keep=False),
        "BU emitido antes do encerramento": df["dt_emissao_bu"] < df["dt_encerramento"],
        "encerramento antes da abertura": df["dt_encerramento"] < df["dt_abertura"],
    }
    return pd.DataFrame(
        {"secoes_violando": {k: int(v.sum()) for k, v in testes.items()}}
    ).assign(pct=lambda d: d["secoes_violando"] / len(df) * 100)


# --------------------------------------------------------------------------- dígitos


def segundo_digito(contagens: pd.Series | np.ndarray) -> dict:
    """Teste de Benford para o 2º dígito (2BL, Mebane). Usa só contagens >= 10.

    Observação: o 1º dígito (1BL) NÃO é apropriado para contagens por seção, porque o tamanho
    das seções é limitado (~até 500 eleitores) e isso distorce a distribuição.
    """
    x = np.asarray(contagens)
    x = x[x >= 10]
    d2 = (x // 10 ** (np.floor(np.log10(x)).astype(int) - 1)) % 10
    esperado = np.array([sum(np.log10(1 + 1 / (10 * k + d)) for k in range(1, 10)) for d in range(10)])
    obs = np.bincount(d2.astype(int), minlength=10)
    chi2, p = stats.chisquare(obs, esperado * obs.sum())
    return {
        "n": int(obs.sum()),
        "media_2dig": float(d2.mean()),
        "media_esperada": float((np.arange(10) * esperado).sum()),  # ≈ 4,187
        "chi2": float(chi2),
        "p": float(p),
        "obs_freq": obs / obs.sum(),
        "esp_freq": esperado,
    }


def ultimo_digito(contagens: pd.Series | np.ndarray, minimo: int = 100) -> dict:
    """Uniformidade do último dígito para contagens >= `minimo` (abaixo disso o teste é viciado)."""
    x = np.asarray(contagens)
    x = x[x >= minimo]
    obs = np.bincount((x % 10).astype(int), minlength=10)
    chi2, p = stats.chisquare(obs)
    return {"n": int(obs.sum()), "chi2": float(chi2), "p": float(p), "obs_freq": obs / max(obs.sum(), 1)}


# --------------------------------------------------------------------------- homogeneidade no local


@dataclass
class ResultadoLocal:
    tabela: pd.DataFrame  # uma linha por seção com z-score e p-valor
    phi: float  # fator de sobredispersão estimado (1 = binomial puro)


def desvio_no_local(df: pd.DataFrame, cand: str, min_secoes: int = 3) -> ResultadoLocal:
    """Compara cada seção com as OUTRAS seções do mesmo local de votação (mesma escola).

    Seções no mesmo prédio têm eleitorado muito parecido, então a fração de votos de um candidato
    deveria ser próxima. Para cada seção, calcula-se a proporção esperada a partir das demais
    seções do local (leave-one-out) e um z-score quase-binomial: a variância binomial é inflada
    pelo fator de sobredispersão `phi`, estimado nos próprios dados (eleitores não são sorteados
    ao acaso entre as seções, então phi > 1 é o normal).
    """
    d = df[CHAVE_LOCAL + ["sec_id", "votos_validos", cand]].copy()
    d = d[d["votos_validos"] > 0]
    g = d.groupby(CHAVE_LOCAL, observed=True)
    d["n_secoes_local"] = g["sec_id"].transform("size")
    d = d[d["n_secoes_local"] >= min_secoes]
    g = d.groupby(CHAVE_LOCAL, observed=True)
    tot_v = g["votos_validos"].transform("sum")
    tot_c = g[cand].transform("sum")
    n = d["votos_validos"]
    k = d[cand]
    p0 = ((tot_c - k) / (tot_v - n)).clip(1e-4, 1 - 1e-4)
    resid = (k - n * p0) / np.sqrt(n * p0 * (1 - p0))
    phi = float(np.mean(resid**2))
    z = resid / np.sqrt(phi)
    out = d.assign(
        prop=k / n,
        prop_esperada=p0,
        z=z,
        p_valor=2 * stats.norm.sf(np.abs(z)),
        votos_excesso=k - n * p0,
    )
    return ResultadoLocal(out, phi)


def simular_extremos(res: ResultadoLocal, limiar_z: float = 5.0, n_sim: int = 200, seed: int = 0) -> dict:
    """Quantas seções com |z| > limiar esperaríamos se só houvesse variação aleatória?

    Simula votos beta-binomiais com a mesma sobredispersão estimada e conta extremos. Se o
    observado ficar dentro da faixa simulada, os 'outliers' são compatíveis com o acaso.
    """
    rng = np.random.default_rng(seed)
    t = res.tabela
    n = t["votos_validos"].to_numpy()
    p = t["prop_esperada"].to_numpy()
    # beta-binomial com variância n p (1-p) phi  =>  rho = (phi-1)/(n-1)
    rho = np.clip((res.phi - 1) / np.maximum(n - 1, 1), 1e-9, 0.99)
    a = p * (1 - rho) / rho
    b = (1 - p) * (1 - rho) / rho
    contagens = []
    for _ in range(n_sim):
        k = rng.binomial(n, rng.beta(a, b))
        z = (k - n * p) / np.sqrt(n * p * (1 - p) * res.phi)
        contagens.append(int((np.abs(z) > limiar_z).sum()))
    contagens = np.array(contagens)
    return {
        "observado": int((t["z"].abs() > limiar_z).sum()),
        "esperado_medio": float(contagens.mean()),
        "esperado_p95": float(np.percentile(contagens, 95)),
        "esperado_p99": float(np.percentile(contagens, 99)),
    }


def fdr_bh(p: pd.Series | np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Máscara de rejeição por Benjamini–Hochberg (controle de falsas descobertas)."""
    p = np.asarray(p)
    m = len(p)
    ordem = np.argsort(p)
    lim = alpha * np.arange(1, m + 1) / m
    passou = p[ordem] <= lim
    rej = np.zeros(m, bool)
    if passou.any():
        rej[ordem[: np.max(np.nonzero(passou)) + 1]] = True
    return rej


# --------------------------------------------------------------------------- materialidade


def impacto(df: pd.DataFrame, mascara: pd.Series, nome: str) -> dict:
    """Se TODAS as seções marcadas fossem anuladas, o que acontece com a margem?"""
    venc, seg, marg = margem(df)
    sub = df[mascara]
    liquido = int(sub[venc].sum() - sub[seg].sum())
    return {
        "criterio": nome,
        "secoes": int(mascara.sum()),
        "pct_secoes": float(mascara.mean() * 100),
        "votos_validos": int(sub["votos_validos"].sum()),
        f"votos_{venc}": int(sub[venc].sum()),
        f"votos_{seg}": int(sub[seg].sum()),
        "liquido_para_vencedor": liquido,
        "margem_total": marg,
        "margem_apos_anular": marg - liquido,
        "muda_resultado": (marg - liquido) <= 0,
        "pct_da_margem": liquido / marg * 100 if marg else np.nan,
    }


# --------------------------------------------------------------------------- 1º -> 2º turno


def juntar_turnos(t1: pd.DataFrame, t2: pd.DataFrame) -> pd.DataFrame:
    """Une as seções dos dois turnos pela chave (UF, município, zona, seção)."""
    c1 = candidatos(t1)
    c2 = candidatos(t2)
    a = t1[CHAVE_SECAO + ["qt_aptos", "qt_comparecimento", "votos_validos", "BRANCO", "NULO", "nr_urna_efetivada"] + c1]
    b = t2[CHAVE_SECAO + ["sec_id", "regiao", "nr_local_votacao", "qt_aptos", "qt_comparecimento", "votos_validos",
                         "BRANCO", "NULO", "nr_urna_efetivada"] + c2]
    m = b.merge(a, on=CHAVE_SECAO, suffixes=("_2t", "_1t"), how="inner")
    return m


def modelo_transicao(m: pd.DataFrame, cands_1t: list[str], alvo_2t: str) -> pd.DataFrame:
    """Prevê a % do candidato `alvo_2t` no 2º turno a partir das % do 1º turno (modelo ecológico).

    Regressão linear ponderada com efeito fixo de município: capta como cada eleitorado do 1º
    turno se redistribuiu. Seções com resíduo muito alto são as que se comportaram de forma
    diferente das vizinhas com perfil de 1º turno parecido.
    """
    import statsmodels.api as sm

    d = m[m["votos_validos_1t"] > 0].copy()
    cols = [c for c in cands_1t if c in d]
    # colunas do 1º turno que coincidem com nomes do 2º vêm com sufixo _1t
    X = pd.DataFrame({c: d[c + "_1t" if c + "_1t" in d else c] / d["votos_validos_1t"] for c in cols})
    X["BRANCO_NULO"] = (d["BRANCO_1t"] + d["NULO_1t"]) / d["qt_comparecimento_1t"].clip(lower=1)
    X["comparecimento_1t"] = d["qt_comparecimento_1t"] / d["qt_aptos_1t"].clip(lower=1)
    X = X.drop(columns=cols[-1])  # evita colinearidade (as %s somam 1)
    alvo = d[alvo_2t + "_2t" if alvo_2t + "_2t" in d else alvo_2t]
    y = alvo / d["votos_validos_2t"].clip(lower=1)
    # efeito fixo de município por "demeaning" ponderado
    w = d["votos_validos_2t"].astype(float)
    grp = d["uf"].astype(str) + "-" + d["cd_municipio"].astype(str)
    def demean(s):
        mw = (s * w).groupby(grp).transform("sum") / w.groupby(grp).transform("sum")
        return s - mw
    Xd = X.apply(demean)
    yd = demean(y)
    fit = sm.WLS(yd, Xd, weights=w).fit()
    pred = y - fit.resid
    n = d["votos_validos_2t"]
    se = np.sqrt((pred.clip(1e-3, 1 - 1e-3) * (1 - pred.clip(1e-3, 1 - 1e-3))) / n.clip(lower=1))
    phi = float(np.average((fit.resid / se) ** 2, weights=None))
    out = d[CHAVE_SECAO + ["sec_id", "regiao", "votos_validos_2t"]].assign(
        prop_2t=y, prop_prevista=pred, residuo=fit.resid, z=fit.resid / (se * np.sqrt(phi)),
    )
    out.attrs["r2"] = float(fit.rsquared)
    out.attrs["phi"] = phi
    return out


def efeito_dentro_do_grupo(y: pd.Series, x: pd.Series, grupo: pd.Series, peso: pd.Series) -> dict:
    """Coeficiente de `x` em `y` com efeito fixo de `grupo` (WLS sobre variáveis centradas no grupo).

    Erros-padrão agrupados por `grupo` (cluster), já que seções do mesmo município não são independentes.
    """
    import statsmodels.api as sm

    w = peso.astype(float)
    def centrar(s):
        s = s.astype(float)
        return s - (s * w).groupby(grupo).transform("sum") / w.groupby(grupo).transform("sum")
    yd, xd = centrar(y), centrar(x)
    fit = sm.WLS(yd, xd.to_frame("x"), weights=w).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(grupo)[0]})
    lo, hi = fit.conf_int().loc["x"]
    return {"coef": float(fit.params["x"]), "ic95": (float(lo), float(hi)), "p": float(fit.pvalues["x"])}
