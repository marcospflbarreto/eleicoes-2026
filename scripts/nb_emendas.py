"""Células do notebook 04 — emendas parlamentares dos deputados federais e reeleição em 2026."""

TITULO = "04_emendas_reeleicao.ipynb"

CELULAS = [
("md", r"""
# Emendas parlamentares e reeleição dos deputados federais (2023–2026)

Duas perguntas:
1. **Descritiva:** quanto os deputados federais destinaram em emendas na 57ª legislatura, de que tipo, quando foi pago
   e para onde foi.
2. **Pergunta A:** entre os 513 deputados eleitos em 2022, quem destinou mais emendas, ou as concentrou na própria base
   eleitoral, se reelegeu mais em 2026?

Os dados vêm de `uv run coletar-legislativo` (Portal da Transparência, TSE e Câmara). A tabela por deputado é montada por
`eleicoes_2026.emendas.painel_deputados()`.

**O que este notebook não consegue dizer.** É uma análise de associação, não de causa: deputados que já eram fortes podem
tanto conseguir executar mais emendas quanto se reeleger mais. Faltam os gastos de campanha de 2026 (a prestação de
contas final ainda não foi publicada), que são o principal fator conhecido de reeleição.
"""),
("code", r"""
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.formula.api as smf

from eleicoes_2026 import emendas as E

warnings.filterwarnings("ignore", category=FutureWarning)
sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.figsize": (11, 5), "figure.dpi": 110, "axes.titleweight": "bold"})
pd.options.display.float_format = "{:,.2f}".format

emendas = pd.read_parquet(E.LEG / "emendas.parquet")
pagos = pd.read_parquet(E.LEG / "emendas_pagamentos.parquet")
dep = E.painel_deputados()
print(f"{len(emendas):,} linhas de emendas, {len(pagos):,} pagamentos, {len(dep)} deputados eleitos em 2022")
"""),
("md", r"""
## 1. Quanto e de que tipo
Valores em R$ bilhões, por ano do orçamento. **Empenhado** é o valor reservado; **pago** é o que saiu no próprio ano
(o restante vira "restos a pagar" e é pago nos anos seguintes).

Os tipos:
- **Individual – Transferência especial** (a "emenda Pix"): o dinheiro vai direto para o caixa da prefeitura ou do
  estado, sem projeto definido.
- **Individual – Finalidade definida:** o dinheiro vai para uma ação específica (obra, custeio de saúde etc.).
- **Bancada:** emenda coletiva dos deputados e senadores de um estado.
- **Comissão:** emenda de comissão do Congresso.
- **Relator:** o "orçamento secreto", declarado inconstitucional pelo STF no fim de 2022.

As emendas individuais têm execução obrigatória e uma cota igual por parlamentar; só elas têm um autor individual.
"""),
("code", r"""
e = emendas[emendas["ano"].between(2020, 2026)]
CURTO = {"Emenda Individual - Transferências Especiais": "Individual – especial (Pix)",
         "Emenda Individual - Transferências com Finalidade Definida": "Individual – finalidade definida",
         "Emenda de Bancada": "Bancada", "Emenda de Comissão": "Comissão", "Emenda de Relator": "Relator"}
t = (e.assign(tipo=e["tipo"].map(CURTO)).groupby(["tipo", "ano"])[["valor_empenhado", "valor_pago"]].sum() / 1e9).unstack("ano")
t.columns = [f"{c[0].replace('valor_', '')} {c[1]}" for c in t.columns]
t = t[[f"{v} {a}" for v in ("empenhado", "pago") for a in range(2020, 2027)]]
t
"""),
("code", r"""
emp = (e.assign(tipo=e["tipo"].map(CURTO)).groupby(["ano", "tipo"])["valor_empenhado"].sum() / 1e9).unstack("tipo")
ax = emp.plot.bar(stacked=True, width=.8)
ax.set_ylabel("R$ bilhões empenhados"); ax.set_xlabel("ano do orçamento")
ax.set_title("Emendas parlamentares por tipo"); ax.legend(fontsize=9, loc="upper left"); plt.show()
"""),
("md", r"""
**Leitura.** Depois do fim das emendas de relator (2022), o dinheiro migrou para as emendas de comissão e de bancada. As
individuais cresceram e, dentro delas, as transferências especiais ficaram com cerca de um terço.
"""),
("md", r"""
## 2. Quando foi pago: o calendário eleitoral
Pagamentos por mês, de 2022 a 2026, somando o pagamento do próprio ano e os restos a pagar. A lei eleitoral proíbe
transferências voluntárias para estados e municípios nos três meses anteriores à eleição; as emendas individuais seguem
essa regra.
"""),
("code", r"""
p = pagos[pagos["ano_pagamento"] >= 2022].copy()
p["mes"] = pd.PeriodIndex.from_fields(year=p["ano_pagamento"], month=p["mes_pagamento"], freq="M")
p["grupo"] = np.where(p["tipo"].str.startswith("Emenda Individual"), "individuais", "bancada, comissão e relator")
m = (p.groupby(["mes", "grupo"])["valor"].sum() / 1e9).unstack("grupo").fillna(0)
m.index = m.index.astype(str)  # barras em posições 0..n-1, uma por mês
ax = m.plot.bar(stacked=True, width=.9, color=["0.7", "C0"])
ax.set_xticks(range(0, len(m), 3), m.index[::3], rotation=90)
ax.set_ylabel("R$ bilhões pagos"); ax.set_xlabel(""); ax.set_title("Pagamentos de emendas por mês")
for ano in (2022, 2026):
    ax.axvline(list(m.index).index(f"{ano}-10"), color="C3", ls="--", lw=1)  # mês da eleição
plt.show()

anos = p
antes = anos[anos["mes_pagamento"] <= 6].groupby("ano_pagamento")["valor"].sum() / anos.groupby("ano_pagamento")["valor"].sum()
print("Fração do ano pago de janeiro a junho:", ", ".join(f"{a}: {v:.0%}" for a, v in antes.items()),
      "(2026 vai só até outubro)")
"""),
("md", r"""
**Leitura.** Em ano de eleição o pagamento se concentra antes de julho, quando começa a proibição. Isso vale para as
eleições gerais (2022, 2026) e para as municipais (2024), quando prefeitos e vereadores aliados disputam. Em 2026 o pico
foi em maio. Em 2023 e 2025 os pagamentos se espalham pelo segundo semestre.
"""),
("md", r"""
## 3. Para onde foi
O arquivo principal de emendas não diz o município de destino da maioria das emendas individuais ("MÚLTIPLO" ou só a
UF). O arquivo de pagamentos diz o município de quem recebeu, e é ele que usamos. Uma exceção importante: nas emendas
com finalidade definida, boa parte do dinheiro passa pelo **Banco do Brasil em Brasília**, que é só o intermediário, e o
destino final se perde.
"""),
("code", r"""
ind = p[p["tipo"].str.startswith("Emenda Individual") & (p["ano_pagamento"] >= 2023)].copy()
ind["destino"] = np.select(
    [ind["favorecido"].str.contains("BANCO DO BRASIL", na=False),
     ind["natureza_juridica"].str.contains("Município|Municipal", na=False),
     ind["natureza_juridica"].str.contains("Estado|Estadual", na=False),
     ind["natureza_juridica"].str.contains("Privad|Empresária|Cooperativa", na=False)],
    ["Banco do Brasil (intermediário)", "prefeitura ou fundo municipal", "estado ou fundo estadual", "entidade privada"],
    "outros")
d = (ind.groupby(["tipo", "destino"])["valor"].sum() / 1e9).unstack("tipo").fillna(0)
d.columns = [c.replace("Emenda Individual - Transferências ", "") for c in d.columns]
d["total"] = d.sum(axis=1)
d.loc["total"] = d.sum()
display(d.round(2))
print(f"Fração das emendas individuais (pagas 2023–2026) sem destino identificável: "
      f"{d.loc['Banco do Brasil (intermediário)', 'total'] / d.loc['total', 'total']:.0%}")
"""),
("code", r"""
func = emendas[emendas["tipo"].str.startswith("Emenda Individual") & emendas["ano"].between(E.ANO_INICIO, 2026)]
f = func.groupby("funcao")["valor_empenhado"].sum().sort_values(ascending=False) / 1e9
f = pd.concat([f.head(8), pd.Series({"demais": f.iloc[8:].sum()})])
ax = f[::-1].plot.barh(color="C0")
ax.set_xlabel("R$ bilhões empenhados"); ax.set_title(f"Emendas individuais por área ({E.ANO_INICIO}–2026)"); plt.show()
"""),
("md", r"""
**Leitura.** As transferências especiais vão quase todas para prefeituras e estados. Nas de finalidade definida, o
maior destino identificado são os fundos municipais (principalmente de saúde). O Banco do Brasil aparece como intermediário em uma fatia grande, e por isso as análises por município
subestimam o dinheiro que chega a cada lugar. Saúde concentra a maior parte do valor: a Constituição obriga que metade
das emendas individuais vá para a saúde.
"""),
("md", r"""
## 4. Os deputados: quanto cada um destinou e com que estratégia
A partir daqui a unidade é o deputado eleito em 2022. As medidas, todas de emendas individuais dos orçamentos de
2024 a 2026 pagas até setembro de 2026 (o mês anterior à eleição):

| coluna | o que mede |
|---|---|
| `emendas_pagas` | valor pago, em R$ |
| `pct_especial` | fração paga como transferência especial ("Pix") |
| `pct_pago_2026` | fração paga no ano da eleição |
| `pct_na_base` | fração do valor com município identificado que foi para a **base eleitoral** do deputado: os municípios que, somados, deram metade dos votos dele em 2022 |
| `governismo` | fração dos votos Sim/Não na Câmara (2023–2026) que seguiram a orientação do Governo |

O orçamento de 2023 fica de fora porque as emendas dele foram apresentadas em 2022, pela legislatura anterior: só os
deputados reeleitos em 2022 as têm.
"""),
("code", r"""
fig, ax = plt.subplots()
ax.hist(dep["emendas_pagas"] / 1e6, bins=40, color="C0")
ax.set_xlabel("R$ milhões pagos por deputado (orçamentos 2024–2026, até set/2026)"); ax.set_ylabel("deputados")
ax.set_title("A cota é quase igual para todos"); plt.show()

poucos = dep[dep["emendas_pagas"] < dep["emendas_pagas"].median() / 2].sort_values("emendas_pagas")
inteiro = dep.loc[dep["anos_com_emendas"] == 3, "emendas_pagas"] / 1e6
print(f"Quem teve emenda própria nos três orçamentos ({len(inteiro)} deputados): metade recebeu entre "
      f"R$ {inteiro.quantile(.25):.0f} e {inteiro.quantile(.75):.0f} milhões.")
print(f"{len(poucos)} deputados receberam menos da metade da mediana (R$ {dep['emendas_pagas'].median() / 1e6:.0f} milhões). "
      "Na lista há ministros, secretários estaduais e deputados que")
print("perderam o mandato ou morreram; nesses casos quem assumiu a cadeira apresentou as emendas:")
print(", ".join(poucos["nome"]))
"""),
("code", r"""
grandes = dep["sg_partido_2022"].value_counts().loc[lambda s: s >= 10].index
partidos = (dep[dep["sg_partido_2022"].isin(grandes)].groupby("sg_partido_2022")
            .agg(deputados=("nome", "size"), emendas_milhoes=("emendas_pagas", lambda s: s.median() / 1e6),
                 pct_especial=("pct_especial", "median"), pct_na_base=("pct_na_base", "median"),
                 governismo=("governismo", "median"))
            .sort_values("governismo"))
partidos
"""),
("code", r"""
CORES = dict(zip(["PL", "UNIÃO", "PP", "REPUBLICANOS", "MDB", "PSD", "PT"], sns.color_palette("tab10")))
dep["partido_grafico"] = dep["sg_partido_2022"].where(dep["sg_partido_2022"].isin(CORES), "outros")
fig, axs = plt.subplots(1, 2, figsize=(14, 5.5), sharex=True)
for ax, col, titulo in zip(axs, ["pct_especial", "pct_na_base"], ["Fração em transferência especial", "Fração na base eleitoral"]):
    o = dep[dep["partido_grafico"] == "outros"]
    ax.scatter(o["governismo"], o[col], s=12, color="0.75", alpha=.6, label="outros partidos")
    for sg, cor in CORES.items():
        g = dep[dep["partido_grafico"] == sg]
        ax.scatter(g["governismo"], g[col], s=16, color=cor, alpha=.65, label=sg)
        # mediana do partido: marcador grande com borda preta
        ax.scatter(g["governismo"].median(), g[col].median(), s=170, color=cor, edgecolor="k", lw=1.2, marker="D", zorder=5)
    ax.set_xlabel("governismo (fração de votos com o Governo)"); ax.set_title(titulo)
axs[1].legend(title="partido em 2022\n(losango = mediana)", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
plt.tight_layout(); plt.show()
print(dep[["emendas_pagas", "pct_especial", "pct_pago_2026", "pct_na_base", "governismo"]].corr(method="spearman").round(2))
"""),
("md", r"""
**Leitura.** Como a cota é igual por lei, o valor pago quase não varia entre quem exerceu o mandato inteiro: o
alinhamento com o governo não muda o **quanto** um deputado consegue destinar. O que varia é a estratégia: quanto vai
como transferência especial e quanto fica concentrado na própria base. O PSOL não usa transferência especial.
"""),
("md", r"""
## 5. Pergunta A: emendas e reeleição
Dos 513 eleitos em 2022, uma parte não disputou a Câmara em 2026 (concorreu a outro cargo ou não concorreu). A pergunta
só faz sentido para quem tentou a reeleição.
"""),
("code", r"""
print(f"Eleitos em 2022: {len(dep)}")
print(f"   candidatos a deputado federal em 2026: {dep['concorreu_2026'].sum()}")
print(f"   reeleitos: {dep['reeleito'].sum()} ({dep.loc[dep['concorreu_2026'], 'reeleito'].mean():.0%} de quem tentou)")
print(f"   mudaram de partido entre 2022 e 2026 (entre quem tentou): {dep.loc[dep['concorreu_2026'], 'mudou_partido'].mean():.0%}")
r = dep[dep["concorreu_2026"]].copy()
r["reeleito"] = r["reeleito"].astype(int)
"""),
("code", r"""
def taxa_por_faixa(col, rotulos=("baixa", "média", "alta")):
    faixa = pd.qcut(r[col].rank(method="first"), 3, labels=rotulos)
    return r.groupby(faixa, observed=True).agg(
        deputados=("reeleito", "size"), valor_mediano=(col, "median"),
        taxa_reeleicao=("reeleito", "mean"), crescimento_mediano_votos=("crescimento_votos", "median"))

for col in ("emendas_pagas", "pct_na_base", "pct_especial", "pct_pago_2026"):
    print(f"\n{col} (terços)")
    display(taxa_por_faixa(col))

print("\ngovernismo (faixas fixas: a oposição fica quase toda abaixo de 0,4)")
display(r.groupby(pd.cut(r["governismo"], [0, .4, .6, .8, .9, 1]), observed=True)
         .agg(deputados=("reeleito", "size"), taxa_reeleicao=("reeleito", "mean"), mudou_partido=("mudou_partido", "mean")))
"""),
("md", r"""
**Regressões.** Duas medidas de resultado, para quem disputou em 2026:
- `reeleito` (0 ou 1), em modelo de probabilidade linear: o coeficiente é a mudança na chance de reeleição;
- `crescimento_votos`: log dos votos em 2026 sobre os de 2022 (0,10 ≈ 10% mais votos).

Controles: força eleitoral em 2022 (log da fatia dos votos da UF), se é veterano (já era deputado antes de 2023), se
mudou de partido, número de municípios na base (deputados de base concentrada têm menos municípios onde a emenda "conta")
e efeitos fixos de UF. Erros-padrão robustos (HC1). `emendas_pagas` entra em R$ 10 milhões.
"""),
("code", r"""
r["emendas_10mi"] = r["emendas_pagas"] / 1e7
r["log_fatia_2022"] = np.log(r["fatia_uf_2022"])
r["log_mun_base"] = np.log(r["n_municipios_base"])
CONTROLES = "log_fatia_2022 + veterano + mudou_partido + log_mun_base + C(uf)"

linhas = []
for y in ("reeleito", "crescimento_votos"):
    for x in ("emendas_10mi", "pct_na_base", "pct_especial", "pct_pago_2026", "governismo"):
        for extra, nome in (("", "UF"), (" + C(sg_partido_2022)", "UF + partido")):
            mod = smf.ols(f"{y} ~ {x} + {CONTROLES}{extra}", data=r).fit(cov_type="HC1")
            ic = mod.conf_int().loc[x]
            linhas.append({"resultado": y, "variável": x, "efeitos fixos": nome, "coef": mod.params[x],
                           "IC 95% inf": ic[0], "IC 95% sup": ic[1], "p": mod.pvalues[x], "n": int(mod.nobs)})
R = pd.DataFrame(linhas).set_index(["resultado", "variável", "efeitos fixos"])
R.style.format({"coef": "{:.3f}", "IC 95% inf": "{:.3f}", "IC 95% sup": "{:.3f}", "p": "{:.3f}", "n": "{:d}"}) \
    .map(lambda v: "font-weight: bold" if v < .05 else "", subset=["p"])
"""),
("code", r"""
fig, axs = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
for ax, y in zip(axs, ("reeleito", "crescimento_votos")):
    s = R.xs(y).reset_index()
    s["rótulo"] = s["variável"] + " (" + s["efeitos fixos"] + ")"
    ax.errorbar(s["coef"], range(len(s)), xerr=[s["coef"] - s["IC 95% inf"], s["IC 95% sup"] - s["coef"]], fmt="o", capsize=3)
    ax.axvline(0, color="k", lw=.8); ax.set_title(y)
    ax.set_yticks(range(len(s)), s["rótulo"]); ax.invert_yaxis()
axs[0].set_xlabel("mudança na chance de reeleição"); axs[1].set_xlabel("mudança no log dos votos")
fig.suptitle("Coeficientes com intervalo de 95%", weight="bold"); plt.tight_layout(); plt.show()
"""),
("code", r"""
fig, ax = plt.subplots()
sns.regplot(data=r, x="pct_na_base", y="crescimento_votos", lowess=True, scatter_kws={"s": 12, "alpha": .4}, line_kws={"color": "C3"}, ax=ax)
ax.axhline(0, color="k", lw=.8)
ax.set_xlabel("fração das emendas (com município identificado) paga na base eleitoral de 2022")
ax.set_ylabel("log(votos 2026 / votos 2022)"); ax.set_title("Concentrar emendas na base e variação de votos")
plt.show()
"""),
("md", r"""
**Leitura.**
- **Valor pago:** a associação com reeleição é pequena e não significativa a 5%. Era o esperado: com cota igual, quase não
  há variação para medir, e a que existe vem de licenças.
- **Concentração na base:** quem mandou uma fração maior das emendas para os municípios que o elegeram em 2022 teve mais
  votos em 2026, inclusive comparando deputados do mesmo partido e da mesma UF. Na chance de reeleição o sinal é o mesmo,
  mas o intervalo inclui zero.
- **Transferência especial e pagamento no ano da eleição:** nenhuma associação.
- **Governismo:** a oposição (quase toda do PL) se reelegeu mais que o centro. Com efeito fixo de partido a diferença na
  reeleição some, ou seja, é efeito do partido, não das emendas.
"""),
("md", r"""
## 6. Resumo automático
"""),
("code", r"""
def frase(y, x, fe="UF"):
    l = R.loc[(y, x, fe)]
    return f"coef {l['coef']:+.3f} (IC 95% {l['IC 95% inf']:+.3f} a {l['IC 95% sup']:+.3f}, p = {l['p']:.3f})"

print(f"• {dep['concorreu_2026'].sum()} dos 513 eleitos em 2022 disputaram a Câmara em 2026; "
      f"{r['reeleito'].mean():.0%} deles se reelegeram.")
print(f"• Valor pago: mediana de R$ {dep['emendas_pagas'].median() / 1e6:.0f} milhões por deputado; "
      f"a variação vem quase toda de licença ou perda de mandato, não de escolha.")
print(f"• Mais R$ 10 milhões em emendas pagas → chance de reeleição: {frase('reeleito', 'emendas_10mi')}")
print(f"• Concentração na base (de 0 a 100%) → chance de reeleição: {frase('reeleito', 'pct_na_base')}")
print(f"                                     → crescimento dos votos: {frase('crescimento_votos', 'pct_na_base')}")
print(f"  (com efeito fixo de partido: {frase('crescimento_votos', 'pct_na_base', 'UF + partido')})")
print(f"• Fração em transferência especial → crescimento dos votos: {frase('crescimento_votos', 'pct_especial')}")
print(f"• Governismo → chance de reeleição: {frase('reeleito', 'governismo')}")
print("\nLembretes: associação, não causa. Deputados com base sólida podem tanto mandar mais emendas para ela quanto crescer")
print("nos votos por outros motivos. Faltam os gastos de campanha de 2026. A pergunta B (emendas × votos por município,")
print("com efeitos fixos de deputado e município) controla melhor esses fatores e é o próximo passo.")
"""),
]
