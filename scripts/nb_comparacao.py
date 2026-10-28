"""Células do notebook 03 — 2026 comparada com 2022 e explicação das seções extremas."""

TITULO = "03_comparacao_2022.ipynb"

CELULAS = [
("md", r"""
# Eleição 2026 comparada com 2022: o que é normal numa eleição brasileira?

Os notebooks 01 e 02 comparam cada indicador com um **modelo de acaso**. Este notebook usa uma régua mais concreta:
a **eleição presidencial de 2022**, com os mesmos testes, o mesmo código e os BUs oficiais do TSE. Um indicador de 2026
só merece atenção se fugir do que 2022 mostrou.

Também fecha três pontos que ficaram abertos nos notebooks 01 e 02:
1. **Por que o 2º dígito de Benford "reprova" quase todas as UFs?** (seção 2)
2. **Por que as seções que destoam do próprio local de votação pendem para um lado?** (seções 3 e 4)
3. **O padrão de comparecimento alto e de biometria é novo?** (seção 1)

A seção 5 confere três argumentos que circularam depois do 2º turno.

Para ter os dados de 2022: `ELEICOES_ANO=2022 uv run baixar && ELEICOES_ANO=2022 uv run processar` (ficam em `data/2022`).
O perfil do eleitorado por seção vem de `uv run perfil`.

Todos os indicadores são medidos para **Lula**, o único candidato presente nos quatro turnos. No 2º turno, o que vale
para Lula vale com sinal trocado para o adversário; no 1º turno, "contra Lula" inclui todos os outros candidatos.
"""),
("code", r"""
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from eleicoes_2026 import analise as A
from eleicoes_2026.config import PROCESSED

warnings.filterwarnings("ignore", category=FutureWarning)
sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.figsize": (11, 5), "figure.dpi": 110, "axes.titleweight": "bold"})
pd.options.display.float_format = "{:,.2f}".format

REF = "LULA"
FONTES = {"2022 1º turno": (1, 2022), "2022 2º turno": (2, 2022), "2026 1º turno": (1, 2026), "2026 2º turno": (2, 2026)}
E = {}
for nome, (t, ano) in FONTES.items():
    df = A.carregar_secoes(t, ano)
    if df is None:
        print(f"{nome}: não disponível")
    else:
        E[nome] = df
        print(f"{nome}: {len(df):,} seções")
"""),
("md", r"""
## 1. Painel de indicadores lado a lado
Cada linha é um teste dos notebooks 01 e 02. A coluna "2026 fora da faixa de 2022?" marca os indicadores em que
2026 fica fora do intervalo entre o menor e o maior valor dos dois turnos de 2022.
"""),
("code", r"""
P = pd.DataFrame({nome: A.painel_anomalias(df, REF) for nome, df in E.items()})
c22 = [c for c in P.columns if c.startswith("2022")]
c26 = [c for c in P.columns if c.startswith("2026")]
lo, hi = P[c22].min(axis=1), P[c22].max(axis=1)
P["2026 fora da faixa de 2022?"] = [
    ", ".join(c.split()[1] + "ºT" for c in c26 if not lo[i] <= P.loc[i, c] <= hi[i]) or "não" for i in P.index
]
P
"""),
("md", r"""
**Como ler.** Contagens de seções (|z|>5) dependem do tamanho e do equilíbrio da eleição, então diferenças moderadas
entre anos são esperadas. O que importa é a **forma**: direção dos extremos, concentração na última seção do local,
Benford observado vs. simulado, e o sinal dos efeitos dentro do município.
"""),
("md", r"""
## 2. Benford: o teste reprova uma eleição sem fraude nenhuma
`A.simular_digitos` gera uma eleição artificial **sem nenhuma manipulação**: em cada seção, os votos de Lula são sorteados
com a proporção do município e a variação observada entre seções. Se a eleição simulada "reprova" tantas UFs quanto a
real, a reprovação mede só o tamanho da amostra e a forma da distribuição de votos, não fraude.
"""),
("code", r"""
linhas = []
for nome, df in E.items():
    obs = sum(A.segundo_digito(g[REF])["p"] < .05 for _, g in df.groupby("uf", observed=True))
    sim = A.simular_digitos(df, REF, n_sim=20, seed=1)
    linhas += [{"eleição": nome, "fonte": "real", "UFs reprovadas": obs}]
    linhas += [{"eleição": nome, "fonte": "simulada sem fraude", "UFs reprovadas": v} for v in sim["reprova_2BL"]]
B = pd.DataFrame(linhas)
ax = sns.stripplot(data=B[B.fonte != "real"], x="eleição", y="UFs reprovadas", color="0.6", alpha=.6, jitter=.15, label="simulação sem fraude")
sns.scatterplot(data=B[B.fonte == "real"], x="eleição", y="UFs reprovadas", color="C3", s=140, marker="D", ax=ax, label="real", zorder=5)
h, l = ax.get_legend_handles_labels(); ax.legend(h[-2:], l[-2:], loc="lower right")
ax.set_ylim(0, 28.5); ax.set_title("2º dígito de Benford: UFs reprovadas a 5% (de 28)")
plt.show()
"""),
("md", r"""
## 3. Seções que destoam do próprio local: a assimetria se repete
No notebook 02 (A10), as seções com |z|>5 em relação às outras seções do mesmo prédio pendiam contra o 1º colocado.
Abaixo, a mesma medida para Lula em todas as eleições: quantas seções extremas a favor e contra, e quantas delas são a
**última seção do local** (a de número mais alto, normalmente a mais nova).
"""),
("code", r"""
linhas = []
for nome, df in E.items():
    t = A.desvio_no_local(df, REF).tabela.merge(df[["sec_id", "nr_secao", "comparecimento_pct"]], on="sec_id")
    g = t.groupby(A.CHAVE_LOCAL, observed=True)
    t["ultima"] = t["nr_secao"] == g["nr_secao"].transform("max")
    t["comp_rel"] = t["comparecimento_pct"] - g["comparecimento_pct"].transform("median")
    ext = t[t["z"].abs() > 5]
    for ult in (True, False):
        e = ext[ext["ultima"] == ult]
        linhas.append({"eleição": nome, "seção": "última do local" if ult else "demais",
                       "a favor": int((e["z"] > 0).sum()), "contra": int((e["z"] < 0).sum()),
                       "z médio de TODAS as seções": t.loc[t["ultima"] == ult, "z"].mean(),
                       "comparecimento vs. resto do local (p.p.)": t.loc[t["ultima"] == ult, "comp_rel"].median() * 100})
S = pd.DataFrame(linhas).set_index(["eleição", "seção"])
S
"""),
("code", r"""
fig, ax = plt.subplots()
S[["a favor", "contra"]].plot.barh(stacked=True, ax=ax, color=["C0", "C1"])
ax.set_xlabel(f"seções com |z|>5 (a favor / contra {REF})"); ax.set_ylabel("")
ax.set_title("Seções extremas em relação ao próprio local, por tipo de seção")
ax.invert_yaxis(); plt.show()
"""),
("md", r"""
**Leitura.** A assimetria aparece em 2022 e em 2026, na mesma direção, e se concentra na **última seção de cada local**.
Uma fraude não precisaria escolher justamente a seção mais nova do prédio. O padrão é compatível com a forma como o TSE
cria seções: quando um local enche, a seção nova recebe quem acabou de tirar ou transferir o título, um eleitorado mais
jovem e com mais estudantes que o resto do prédio. A seção 4 testa isso diretamente.
"""),
("md", r"""
## 4. O perfil do eleitorado explica as seções extremas?
O TSE publica o **perfil do eleitorado de cada seção** (faixa etária, escolaridade). Se as seções extremas forem
explicadas por eleitorado diferente do resto do prédio, elas devem ter, em relação às vizinhas, mais (ou menos) jovens
e pessoas com ensino superior.
"""),
("code", r"""
arq = PROCESSED / "perfil_secao.parquet"
if not arq.exists() or "2026 1º turno" not in E:
    print("Perfil por seção não disponível (rode `uv run perfil`).")
else:
    df = E["2026 1º turno"]
    perfil = pd.read_parquet(arq)
    t = A.desvio_no_local(df, REF).tabela.merge(df[["sec_id"] + A.CHAVE_SECAO], on=["sec_id"] + A.CHAVE_LOCAL[:3])
    t = t.merge(perfil, on=A.CHAVE_SECAO, how="left")
    for c in ("16_24", "60_mais", "superior"):
        t[f"pct_{c}"] = t[f"qt_{c}"] / t["qt_cadastro"] * 100
    g = t.groupby(A.CHAVE_LOCAL, observed=True)
    for c in ("pct_16_24", "pct_60_mais", "pct_superior"):  # diferença para as OUTRAS seções do local
        t[f"d_{c}"] = t[c] - (g[c].transform("sum") - t[c]) / (g[c].transform("size") - 1)
    t = t.dropna(subset=["d_pct_16_24", "d_pct_60_mais", "d_pct_superior"])
    t["grupo"] = np.select([t["z"] > 5, t["z"] < -5], [f"|z|>5 a favor de {REF}", f"|z|>5 contra {REF}"], "demais seções")
    display(t.groupby("grupo")[["d_pct_16_24", "d_pct_60_mais", "d_pct_superior"]].median()
            .rename(columns=lambda c: c.replace("d_pct_", "diferença p/ o resto do local, p.p.: ")))

    from scipy.stats import binomtest
    jovem = t["d_pct_16_24"] > 10
    extremo = t["z"].abs() > 5
    print(f"Seções com >10 p.p. mais eleitores de 16–24 anos que o resto do prédio: {jovem.mean():.1%} das seções, "
          f"mas {jovem[extremo].mean():.0%} das seções |z|>5")
    print(f"   taxa de |z|>5: {extremo[jovem].mean() * 1e4:.1f} por 10 mil entre elas vs {extremo[~jovem].mean() * 1e4:.1f} nas demais")
    resto = t[extremo & ~jovem]
    a_favor, contra = int((resto["z"] > 0).sum()), int((resto["z"] < 0).sum())
    print(f"   extremos que sobram fora desse grupo: {a_favor} a favor de {REF}, {contra} contra "
          f"(simetria: p = {binomtest(a_favor, a_favor + contra).pvalue:.2g})")

    fig, ax = plt.subplots()
    amostra = t.sample(min(len(t), 40000), random_state=0)
    ax.scatter(amostra["d_pct_16_24"], amostra["z"], s=3, alpha=.15, color="0.5", label="seções (amostra)")
    e = t[t["z"].abs() > 5]
    ax.scatter(e["d_pct_16_24"], e["z"], s=25, color="C3", label="|z|>5")
    ax.set_xlim(-30, 60); ax.axhline(0, color="k", lw=.5); ax.axvline(0, color="k", lw=.5)
    ax.set_xlabel("% de eleitores de 16 a 24 anos: diferença para as outras seções do local (p.p.)")
    ax.set_ylabel(f"z do voto em {REF} vs. o local"); ax.legend(); ax.set_title("Seções com eleitorado mais jovem que o prédio")
    plt.show()
"""),
("md", r"""
**Leitura.** As seções extremas, **nos dois sentidos**, têm muito mais eleitores jovens e muito menos idosos que as outras
seções do mesmo prédio: são seções com outro eleitorado, não seções com votos alterados. O perfil explica por que elas
destoam, mas não o sentido: jovens de bairros diferentes votam diferente. A direção (mais extremos a favor de Lula) se repete
em 2022 e em 2026, inclusive no 1º turno de 2026, que Lula perdeu, o que é coerente com o voto jovem e não com um
favorecimento a quem venceu. Os extremos que sobram fora do grupo jovem ainda são mais do que o acaso explicaria; esses são
os candidatos a checagem manual (ata da mesa, BU impresso).
"""),
("md", r"""
## 5. Perguntas que circularam depois do 2º turno
Três argumentos comuns em grupos de mensagem, conferidos com os BUs. Em todos, o número citado está certo; a pergunta é o
que ele mostra quando comparado com o 1º turno e com 2022.

### 5a. Seções em que o adversário de Lula fez no máximo 10 votos
"""),
("code", r"""
def adversario(df):
    return next(c for c in A.principais(df, 2) if c != REF)

chave = ["uf", "cd_municipio", "nr_zona", "nr_secao"]
linhas = []
for nome, df in E.items():
    adv = adversario(df)
    poucos = df[adv] <= 10
    linhas.append({"eleição": nome, "adversário": adv, f"seções com adversário ≤ 10": int(poucos.sum()),
                   f"votos de {REF} nelas": int(df.loc[poucos, REF].sum()),
                   f"seções com {REF} ≤ 10": int((df[REF] <= 10).sum()),
                   "eleitores aptos (mediana)": df.loc[poucos, "qt_aptos"].median()})
display(pd.DataFrame(linhas).set_index("eleição"))

if "2026 2º turno" in E:
    t1, t2 = E["2026 1º turno"], E["2026 2º turno"]
    adv = adversario(t2)
    poucos = t2[t2[adv] <= 10]
    print(poucos.groupby(adv).agg(secoes=(REF, "size"), **{REF: (REF, "sum")}).T.to_string())
    m = poucos[chave + [REF, adv, "votos_validos"]].merge(t1[chave + [REF, adv, "votos_validos"]], on=chave, suffixes=("_2t", "_1t"))
    print(f"\nAs mesmas {len(m):,} seções no 1º turno: {REF} com {m[REF + '_1t'].sum() / m['votos_validos_1t'].sum():.1%} dos válidos "
          f"(2º turno: {m[REF + '_2t'].sum() / m['votos_validos_2t'].sum():.1%}); {adv} já tinha ≤ 10 votos em {int((m[adv + '_1t'] <= 10).sum()):,}.")
    print("UFs com mais dessas seções:", poucos["uf"].value_counts().head(8).to_dict())
"""),
("md", r"""
São seções pequenas (metade do tamanho típico), rurais, na maioria no Nordeste e na Amazônia, que já votavam assim no
1º turno. Em 2022 havia mais seções assim do que em 2026 (4.118 no 2º turno), e o mesmo acontece, em escala menor, com
seções em que Lula faz no máximo 10 votos.

### 5b. Lula cresceu em todos os estados entre o 1º e o 2º turno
A medida dos painéis de apuração é a fatia de Lula **entre os dois finalistas**. Como as duas fatias somam 100%, se uma sobe
num estado a outra cai nele: "o adversário não cresceu em nenhum estado" é o mesmo dado lido do outro lado.
"""),
("code", r"""
def fatia_finalistas(t1, t2):
    adv = adversario(t2)
    g1 = t1.groupby("uf")[[REF, adv]].sum()
    g2 = t2.groupby("uf")[[REF, adv]].sum()
    return (g2[REF] / g2.sum(axis=1) - g1[REF] / g1.sum(axis=1)) * 100

V = pd.DataFrame({ano: fatia_finalistas(E[f"{ano} 1º turno"], E[f"{ano} 2º turno"])
                  for ano in ("2022", "2026") if f"{ano} 2º turno" in E})
for ano in V:
    print(f"{ano}: fatia de {REF} entre os finalistas subiu em {int((V[ano] > 0).sum())} de {len(V)} UFs "
          f"(de {V[ano].min():+.1f} a {V[ano].max():+.1f} p.p.)")
if "2026" in V:
    t1 = E["2026 1º turno"]
    g = t1.groupby("uf")[A.candidatos(t1) + ["votos_validos"]].sum()
    outros = (1 - g[A.principais(t1, 2)].sum(axis=1) / g["votos_validos"]) * 100
    print(f"Correlação, em 2026, entre o crescimento de {REF} e a fatia dos outros candidatos no 1º turno: "
          f"{V['2026'].corr(outros):.2f}")
    fig, ax = plt.subplots(figsize=(11, 6))
    o = V.sort_values("2026")
    y = np.arange(len(o))
    for ano, cor in (("2022", "C1"), ("2026", "C0")):
        if ano in o:
            ax.scatter(o[ano], y, color=cor, label=ano, zorder=3)
    ax.set_yticks(y, o.index); ax.axvline(0, color="k", lw=.8)
    ax.set_xlabel(f"variação da fatia de {REF} entre os dois finalistas, 1º → 2º turno (p.p.)")
    ax.set_title("Entre os turnos, todos os estados andam na mesma direção, em 2022 e em 2026"); ax.legend()
    plt.show()
"""),
("md", r"""
Em 2022 o movimento foi o espelho: o adversário de Lula ganhou terreno nos 28 estados. Quando o país inteiro se move na
mesma direção entre os turnos, isso é uma mudança de voto nacional, não um padrão de urna. Em 2026 Lula cresceu, em geral, mais onde
os outros candidatos tinham mais votos no 1º turno (correlação moderada), e menos onde já tinha 70% ou mais.

### 5c. Rio de Janeiro: de onde vieram os votos a mais de Lula?
A conta de saldo (Lula somou 81% de tudo que o adversário não manteve) supõe que todo eleitor do adversário no 1º turno
votou nele de novo. Uma **estimativa ecológica** (regressão por seção, com coeficientes não negativos) separa as
transferências. É aproximada: estima o comportamento de grupos a partir de seções, não de pessoas.
"""),
("code", r"""
from scipy.optimize import nnls

def transferencias(t1, t2, uf):
    adv = adversario(t2)
    a, b = t1[t1["uf"] == uf], t2[t2["uf"] == uf]
    top = A.candidatos(a)[:5]
    a = a.assign(outros=a[[c for c in A.candidatos(a) if c not in top]].sum(axis=1), bn=a["BRANCO"] + a["NULO"],
                 abst=a["qt_abstencoes"])[chave + top + ["outros", "bn", "abst", "qt_aptos"]]
    a = a.rename(columns={c: f"{c} (1º)" for c in top})
    b = b.assign(bn=b["BRANCO"] + b["NULO"], abst=b["qt_abstencoes"])[chave + [REF, adv, "bn", "abst", "qt_aptos"]]
    m = a.merge(b, on=chave, suffixes=("_1", "_2"))
    m = m[(m["qt_aptos_1"] - m["qt_aptos_2"]).abs() <= 5]  # mesmo eleitorado nos dois turnos
    origem = [f"{c} (1º)" for c in top] + ["outros", "bn_1", "abst_1"]
    X = m[origem].to_numpy(float)
    destino = {f"→ {REF}": REF, f"→ {adv}": adv, "→ branco/nulo": "bn_2", "→ abstenção": "abst_2"}
    T = pd.DataFrame({d: nnls(X, m[c].to_numpy(float))[0] for d, c in destino.items()},
                     index=[*top, "outros", "branco/nulo", "abstenção"])
    T = T.div(T.sum(axis=1), axis=0) * 100
    T["votos no 1º turno"] = X.sum(axis=0).astype(int)
    return T, m

def por_faixa(t1, t2, uf):
    adv = adversario(t2)
    cols = [REF, adv, "votos_validos", "qt_aptos", "qt_comparecimento"]
    m = t1.loc[t1["uf"] == uf, chave + cols].merge(t2.loc[t2["uf"] == uf, chave + cols], on=chave, suffixes=("_1", "_2"))
    m["faixa"] = pd.qcut(m[adv + "_1"] / m["votos_validos_1"], 5, labels=[f"1 (mais {REF})", "2", "3", "4", "5 (mais adversário)"])
    g = m.groupby("faixa", observed=True).sum(numeric_only=True)
    return pd.DataFrame({
        "% do adversário no 1º": g[adv + "_1"] / g["votos_validos_1"] * 100,
        "Δ comparecimento (p.p.)": (g["qt_comparecimento_2"] / g["qt_aptos_2"] - g["qt_comparecimento_1"] / g["qt_aptos_1"]) * 100,
        "votos do adversário (Δ%)": (g[adv + "_2"] / g[adv + "_1"] - 1) * 100,
        f"votos de {REF} (Δ%)": (g[REF + "_2"] / g[REF + "_1"] - 1) * 100,
    })

for ano in ("2026", "2022"):
    if f"{ano} 2º turno" not in E:
        continue
    t1, t2 = E[f"{ano} 1º turno"], E[f"{ano} 2º turno"]
    T, m = transferencias(t1, t2, "RJ")
    display(T.round(0).style.format(precision=0).set_caption(f"{ano}, RJ: para onde foi cada grupo do 1º turno (% da linha; {len(m):,} seções)"))
    display(por_faixa(t1, t2, "RJ").round(1).style.format(precision=1).set_caption(f"{ano}, RJ: seções em cinco faixas pelo voto no adversário no 1º turno"))
"""),
("md", r"""
**Leitura.** No Rio, a estimativa dá a Lula entre um terço e metade dos eleitores dos candidatos de direita, não 70%. O
adversário manteve o próprio saldo porque cerca de 5% dos eleitores dele no 1º turno não voltaram a votar: o
comparecimento subiu bem mais nas seções lulistas do que nas dele. Lula cresceu em todas as faixas, até nas mais favoráveis
ao adversário. Em 2022, no mesmo estado, foi o adversário quem mais cresceu no 2º turno.

## 6. Resumo automático
"""),
("code", r"""
fora = P[P["2026 fora da faixa de 2022?"] != "não"]
print("Indicadores em que 2026 sai da faixa dos dois turnos de 2022:")
print(fora[c22 + c26].round(2).to_string() if len(fora) else "   nenhum")
print("\nLembretes:")
print(" • 'Fora da faixa' com só dois pontos de referência é um critério frouxo: diferenças de tamanho e equilíbrio da disputa")
print("   mudam as contagens. Vale olhar a direção e o tamanho da diferença, não só o rótulo.")
print(" • Benford: compare o ponto real com a nuvem simulada (seção 2), não com 'reprovou / não reprovou'.")
print(" • Seções extremas: ver seções 3 e 4 sobre a última seção do local e o perfil do eleitorado.")
"""),
]
