"""Células do notebook 01 — análise neutra."""

TITULO = "01_analise_neutra.ipynb"

CELULAS = [
("md", r"""
# Eleição Presidencial 2026 — Análise neutra dos Boletins de Urna

**Objetivo:** descrever os resultados e procurar anomalias estatísticas **sem hipótese prévia sobre quem ganha ou perde com elas**.
Cada teste é aplicado de forma simétrica a todos os candidatos e, sempre que possível, comparado com o que se esperaria
apenas por acaso (modelo nulo). Um "outlier" sozinho não é indício de fraude: em ~470 mil seções, eventos de 1 em 100 mil
acontecem algumas vezes por puro acaso.

**Fonte:** Boletins de Urna (BU) publicados pelo TSE em <https://dadosabertos.tse.jus.br> — um registro por seção eleitoral,
com votos por candidato, eleitores aptos, comparecimento, horários e identificação da urna.

Para atualizar os dados: `uv run baixar && uv run processar` e reexecute o notebook.
"""),
("code", r"""
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
from sklearn.ensemble import IsolationForest

from eleicoes_2026 import analise as A

warnings.filterwarnings("ignore", category=FutureWarning)
sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({"figure.figsize": (11, 5), "figure.dpi": 110, "axes.titleweight": "bold"})
pd.options.display.float_format = "{:,.3f}".format
pd.options.display.max_columns = 40

T = {t: A.carregar_secoes(t) for t in (1, 2)}
TURNOS = [t for t, df in T.items() if df is not None]
for t in (1, 2):
    df = T[t]
    print(f"{t}º turno:", "não disponível ainda (rode `uv run baixar --turno 2 && uv run processar --turno 2`)" if df is None
          else f"{len(df):,} seções | {df['votos_total'].sum():,} votos | {df['uf'].nunique()} UFs")
"""),
("md", "## 1. Qualidade e consistência dos dados\nTestes aritméticos que todo BU deveria satisfazer. Violações aqui indicariam erro de registro ou de publicação, não necessariamente de votação."),
("code", r"""
for t in TURNOS:
    print(f"\n{t}º turno")
    display(A.checar_consistencia(T[t]))
    display(T[t]["ds_tipo_urna"].value_counts().rename("seções por tipo de urna").to_frame())
"""),
("md", "## 2. Resultado\n### 2.1 Nacional"),
("code", r"""
fig, axes = plt.subplots(1, len(TURNOS), figsize=(7 * len(TURNOS), 5), squeeze=False)
for ax, t in zip(axes[0], TURNOS):
    r = A.resultado(T[t])
    display(r.assign(votos=r["votos"].map("{:,}".format)).rename(columns={"pct_validos": "% válidos"}).head(12).style.set_caption(f"{t}º turno"))
    top = r.head(8)
    sns.barplot(x=top["pct_validos"], y=top.index, ax=ax, color="#4C72B0")
    ax.bar_label(ax.containers[0], fmt="%.2f%%", padding=3)
    ax.set(title=f"{t}º turno — % dos votos válidos", xlabel="", ylabel="")
plt.tight_layout()
"""),
("md", "### 2.2 Por UF e região"),
("code", r"""
for t in TURNOS:
    df = T[t]
    cands = A.principais(df, 4 if t == 1 else 2)
    por_uf = A.resultado(df, "uf")[cands].sort_values(cands[0])
    ax = por_uf.plot.barh(stacked=True, figsize=(11, 9), width=0.85)
    ax.set(title=f"{t}º turno — % dos válidos por UF (principais candidatos)", xlabel="%", ylabel="")
    ax.axvline(50, color="k", lw=0.8, ls="--")
    ax.legend(loc="lower right")
    plt.show()
    display(A.resultado(df, "regiao")[cands].round(2))
"""),
("md", r"""
## 3. Distribuições por seção
Histogramas da % de comparecimento e da % de cada candidato por seção. Distribuições suaves e unimodais (ou bimodais
explicadas por geografia, como Norte/Nordeste vs Sul) são o esperado. Picos isolados em valores extremos (por exemplo
100% de comparecimento) merecem inspeção.
"""),
("code", r"""
for t in TURNOS:
    df = T[t]
    cands = A.principais(df, 2)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    sns.histplot(df["comparecimento_pct"].clip(0, 1) * 100, bins=100, ax=axes[0])
    axes[0].set(title=f"{t}º turno — comparecimento por seção", xlabel="% comparecimento")
    for ax, c in zip(axes[1:], cands):
        share = df[c] / df["votos_validos"].replace(0, np.nan) * 100
        sns.histplot(x=share, hue=df["regiao"], bins=100, ax=ax, element="step", stat="count", common_norm=False)
        ax.set(title=f"{c}", xlabel="% dos válidos na seção")
    plt.tight_layout(); plt.show()
"""),
("md", r"""
## 4. "Impressão digital" eleitoral (Klimek et al., 2012)
Histograma 2D de **comparecimento × % do candidato** por seção. Em eleições com enchimento de urnas aparece uma
"mancha" anômala no canto superior direito (≈100% de comparecimento e ≈100% de votos para um candidato), ligada ao
resto da nuvem por uma "ponte". Eleições limpas mostram uma nuvem compacta. Mostramos os dois principais candidatos
para manter a simetria.
"""),
("code", r"""
for t in TURNOS:
    df = T[t][T[t]["votos_validos"] >= 30]
    cands = A.principais(df, 2)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, c in zip(axes, cands):
        ax.hist2d(df["comparecimento_pct"].clip(0, 1) * 100, df[c] / df["votos_validos"] * 100,
                  bins=[100, 100], range=[[0, 100], [0, 100]], cmap="magma_r", norm="log")
        ax.set(title=f"{t}º turno — {c}", xlabel="% comparecimento", ylabel=f"% {c}")
    plt.tight_layout(); plt.show()
    canto = (df["comparecimento_pct"] >= 0.95) & (df[cands].max(axis=1) / df["votos_validos"] >= 0.95)
    print(f"Seções no canto (≥95% comparecimento e ≥95% para um candidato): {canto.sum()} "
          f"({canto.mean()*100:.4f}%) — {df.loc[canto, 'votos_validos'].sum():,} votos")
"""),
("md", r"""
## 5. Testes de dígitos
* **2º dígito de Benford (2BL, Mebane):** para contagens de votos por seção, a média do 2º dígito costuma ficar perto de
  4,187. Desvios aparecem também em eleições limpas (a distribuição depende do tamanho da seção e da competitividade),
  então o teste serve mais para **comparar grupos entre si** do que como prova absoluta.
* **Último dígito:** para contagens ≥ 100 o último dígito deveria ser ~uniforme. Manipulação manual de números costuma
  produzir excesso de 0 e 5.
* O teste do **1º dígito não é usado**: o tamanho limitado das seções o torna inadequado.

Com dezenas de grupos testados, alguns p-valores < 0,05 são esperados por acaso; por isso mostramos também o limiar de
Bonferroni. E com centenas de milhares de seções o qui-quadrado rejeita até desvios minúsculos: o que importa é o
**tamanho** do desvio e se ele é **igual para os dois candidatos** (nesse caso reflete a estrutura das seções).
"""),
("code", r"""
for t in TURNOS:
    df = T[t]
    cands = A.principais(df, 2)
    linhas = []
    for c in cands:
        b = A.segundo_digito(df[c]); u = A.ultimo_digito(df[c])
        linhas.append({"candidato": c, "n": b["n"], "média 2º díg": b["media_2dig"], "esperado": b["media_esperada"],
                       "p 2BL": b["p"], "p último díg": u["p"]})
        fig, axes = plt.subplots(1, 2, figsize=(12, 3.5))
        axes[0].bar(range(10), b["obs_freq"], label="observado"); axes[0].plot(range(10), b["esp_freq"], "ro-", label="Benford")
        axes[0].set(title=f"{t}º turno — {c}: 2º dígito", xticks=range(10)); axes[0].legend()
        axes[1].bar(range(10), u["obs_freq"]); axes[1].axhline(0.1, color="r")
        axes[1].set(title=f"{c}: último dígito (contagens ≥ 100)", xticks=range(10))
        plt.tight_layout(); plt.show()
    display(pd.DataFrame(linhas))

    # por UF, simétrico para os dois candidatos
    res = []
    for uf, g in df.groupby("uf", observed=True):
        for c in cands:
            res.append({"uf": uf, "candidato": c, "media_2dig": A.segundo_digito(g[c])["media_2dig"],
                        "p_2BL": A.segundo_digito(g[c])["p"], "p_ultimo": A.ultimo_digito(g[c])["p"]})
    res = pd.DataFrame(res)
    bonf = 0.05 / len(res)
    print(f"{t}º turno — {len(res)} testes por UF; limiar de Bonferroni = {bonf:.2e}")
    print(f"   p 2BL < 0,05: {(res.p_2BL<0.05).sum()} (esperado por acaso ≈ {0.05*len(res):.1f}); < Bonferroni: {(res.p_2BL<bonf).sum()}")
    print(f"   p último dígito < 0,05: {(res.p_ultimo<0.05).sum()}; < Bonferroni: {(res.p_ultimo<bonf).sum()}")
    ax = sns.scatterplot(data=res, x="uf", y="media_2dig", hue="candidato", s=60)
    ax.axhline(4.187, color="k", ls="--", lw=1); ax.set(title=f"{t}º turno — média do 2º dígito por UF"); plt.xticks(rotation=90); plt.show()
"""),
("md", r"""
## 6. Homogeneidade dentro do mesmo local de votação
Seções do mesmo prédio (escola) atendem eleitores muito parecidos. Para cada seção comparamos a % de um candidato com a
das **outras** seções do mesmo local (z-score quase-binomial, com sobredispersão `φ` estimada nos dados). Em seguida
simulamos quantas seções extremas (|z| > 5) apareceriam só por acaso com essa mesma sobredispersão.

Se o número observado for muito maior que o simulado, há mais heterogeneidade do que o acaso explica — o que pode ter
causas legítimas (seções especiais, presídios, aldeias, seções de transferência temporária) e deve ser inspecionado caso a caso.
"""),
("code", r"""
LOCAL = {}
for t in TURNOS:
    df = T[t]
    for c in A.principais(df, 2):
        r = A.desvio_no_local(df, c)
        LOCAL[(t, c)] = r
        sim = A.simular_extremos(r, limiar_z=5)
        print(f"{t}º turno | {c:20s} | φ = {r.phi:.2f} | seções |z|>5: observado {sim['observado']}, "
              f"esperado ~{sim['esperado_medio']:.1f} (p99 = {sim['esperado_p99']:.0f}) | "
              f"BH-FDR 5%: {A.fdr_bh(r.tabela['p_valor']).sum()}")
    fig, ax = plt.subplots(figsize=(10, 4))
    for c in A.principais(df, 2):
        sns.histplot(LOCAL[(t, c)].tabela["z"].clip(-10, 10), bins=200, element="step", fill=False, ax=ax, label=c)
    xs = np.linspace(-10, 10, 400)
    n = len(LOCAL[(t, c)].tabela)
    ax.plot(xs, n * 0.1 * np.exp(-xs**2 / 2) / np.sqrt(2 * np.pi), "k--", label="N(0,1)")
    ax.set(yscale="log", title=f"{t}º turno — z-score da seção vs. resto do local", xlabel="z"); ax.legend(); plt.show()
"""),
("code", r"""
# Seções mais extremas (para inspeção manual — conferir a seção no site do TSE / BU impresso)
for (t, c), r in LOCAL.items():
    top = r.tabela.reindex(r.tabela["z"].abs().sort_values(ascending=False).index).head(10)
    display(top[["sec_id", "nr_local_votacao", "n_secoes_local", "votos_validos", "prop", "prop_esperada", "z"]]
            .style.set_caption(f"{t}º turno — {c}: 10 seções mais destoantes do próprio local"))
"""),
("md", r"""
## 7. Anomalias multivariadas (Isolation Forest)
Combinação de variáveis por seção: comparecimento, % de brancos+nulos, % do 1º colocado, % de eleitores liberados
sem biometria, tempo entre encerramento e emissão do BU, e desvio em relação ao local de votação. O algoritmo aponta
seções "isoladas" — é uma ferramenta de **triagem** para inspeção, não um teste de hipótese. Exterior excluído.
"""),
("code", r"""
# O exterior (ZZ) é estruturalmente diferente (comparecimento muito baixo, seções enormes) e
# dominaria a triagem; por isso fica de fora aqui.
for t in TURNOS:
    df = T[t][T[t]["uf"] != "ZZ"]
    c = A.principais(df, 1)[0]
    z = LOCAL[(t, c)].tabela.set_index("sec_id")["z"]
    X = pd.DataFrame({
        "comparecimento": df["comparecimento_pct"],
        "branco_nulo": (df["BRANCO"] + df["NULO"]) / df["votos_total"].replace(0, np.nan),
        "pct_1o": df[c] / df["votos_validos"].replace(0, np.nan),
        "sem_biometria": df["qt_biom_sem_hab"] / df["qt_comparecimento"].replace(0, np.nan),
        "min_ate_bu": (df["dt_emissao_bu"] - df["dt_encerramento"]).dt.total_seconds() / 60,
        "z_local": df["sec_id"].map(z),
    }, index=df.index).fillna(0).clip(-50, 500)
    iso = IsolationForest(n_estimators=200, contamination=0.001, random_state=0).fit(X)
    df_t = df.assign(score=-iso.score_samples(X), anomalia=iso.predict(X) == -1)
    print(f"{t}º turno: {df_t['anomalia'].sum()} seções sinalizadas (0,1% por construção)")
    display(df_t[df_t.anomalia].groupby("regiao", observed=True).size().rename("seções sinalizadas").to_frame()
            .join(df_t.groupby("regiao", observed=True).size().rename("total")).assign(pct=lambda d: d.iloc[:,0]/d.total*100))
    display(df_t.nlargest(15, "score")[["sec_id", "nm_municipio", "qt_aptos", "comparecimento_pct", "votos_validos", c,
                                         "BRANCO", "NULO", "qt_biom_sem_hab", "score"]])
"""),
("md", r"""
## 8. Aspectos operacionais
Horários (convertidos para Brasília), tempo até a emissão do BU, liberação de eleitores sem biometria e data de carga das
urnas. Servem para verificar se a operação foi homogênea no país.
"""),
("code", r"""
for t in TURNOS:
    df = T[t]
    fig, axes = plt.subplots(2, 2, figsize=(15, 8))
    (df["dt_encerramento_bsb"].dt.hour + df["dt_encerramento_bsb"].dt.minute / 60).plot.hist(bins=120, ax=axes[0, 0], log=True)
    axes[0, 0].set(title="Encerramento da votação (hora de Brasília)", xlabel="hora")
    mins = ((df["dt_emissao_bu"] - df["dt_encerramento"]).dt.total_seconds() / 60).clip(-5, 120)
    mins.plot.hist(bins=125, ax=axes[0, 1], log=True); axes[0, 1].set(title="Minutos entre encerramento e emissão do BU")
    sb = (df["qt_biom_sem_hab"] / df["qt_comparecimento"].replace(0, np.nan) * 100).clip(0, 100)
    sns.histplot(sb, bins=100, ax=axes[1, 0]); axes[1, 0].set(title="% de eleitores liberados sem biometria", yscale="log")
    df["dt_carga_urna"].dt.floor("D").value_counts().sort_index().plot.bar(ax=axes[1, 1])
    axes[1, 1].set(title="Data de carga das urnas"); axes[1, 1].tick_params(axis="x", labelsize=7)
    plt.suptitle(f"{t}º turno", fontweight="bold"); plt.tight_layout(); plt.show()
"""),
("code", r"""
# Ordem de chegada dos BUs: a % acumulada muda ao longo da apuração porque regiões diferentes
# (e o exterior) totalizam em horários diferentes — não porque votos "mudam".
for t in TURNOS:
    df = T[t].dropna(subset=["dt_bu_recebido"]).sort_values("dt_bu_recebido")
    a, b = A.principais(df, 2)
    acum = df[[a, b, "votos_validos"]].cumsum()
    frac = acum["votos_validos"] / acum["votos_validos"].iloc[-1] * 100
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(frac, acum[a] / acum["votos_validos"] * 100, label=a)
    ax.plot(frac, acum[b] / acum["votos_validos"] * 100, label=b)
    ax.set(title=f"{t}º turno — % acumulada conforme os BUs chegam", xlabel="% dos votos válidos totalizados", ylabel="% acumulada", ylim=(20, 80))
    ax.legend(); plt.show()
    ordem = df.groupby("regiao", observed=True)["dt_bu_recebido"].median().sort_values()
    print("Mediana do horário de recebimento por região:"); display(ordem.to_frame())
"""),
("md", r"""
## 9. Do 1º para o 2º turno
Ligando cada seção nos dois turnos, prevemos a % de cada finalista no 2º turno a partir da composição do voto no 1º
(modelo ecológico com efeito fixo de município). Seções com resíduo grande são as que se comportaram de forma muito
diferente das demais seções do município com o mesmo perfil de 1º turno.
"""),
("code", r"""
if T[2] is None:
    print("2º turno ainda não disponível — seção pulada.")
else:
    t1, t2 = T[1], T[2]
    M = A.juntar_turnos(t1, t2)
    print(f"Seções presentes nos dois turnos: {len(M):,} (1º: {len(t1):,}, 2º: {len(t2):,})")
    alvo = A.principais(t2, 1)[0]
    TR = A.modelo_transicao(M, A.candidatos(t1)[:8], alvo)
    print(f"Alvo: % de {alvo} no 2º turno | R² (dentro do município) = {TR.attrs['r2']:.3f} | φ = {TR.attrs['phi']:.2f}")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hexbin(TR["prop_prevista"] * 100, TR["prop_2t"] * 100, gridsize=120, bins="log", cmap="viridis")
    axes[0].plot([0, 100], [0, 100], "r--"); axes[0].set(xlabel="% prevista", ylabel="% observada", title=f"{alvo}: previsto × observado")
    sns.histplot(TR["z"].clip(-10, 10), bins=200, ax=axes[1]); axes[1].set(yscale="log", title="z do resíduo")
    plt.tight_layout(); plt.show()
    display(TR.reindex(TR["z"].abs().sort_values(ascending=False).index).head(15))
    print(f"|z| > 5 → {int((TR['z'].abs()>5).sum())} seções; com z positivo (favor de {alvo}): {int((TR['z']>5).sum())}, "
          f"negativo: {int((TR['z']<-5).sum())}")
    print("   Obs.: assimetria aqui NÃO é, por si, sinal de viés — a migração dos votos de 3º colocados não é linear "
          "(num teste com 2º turno sintético e sem manipulação alguma, o modelo também deu resíduos assimétricos).")
    # comparecimento entre turnos
    dc = (M["qt_comparecimento_2t"] / M["qt_aptos_2t"] - M["qt_comparecimento_1t"] / M["qt_aptos_1t"]) * 100
    ax = sns.histplot(dc.clip(-40, 40), bins=160); ax.set(title="Variação do comparecimento 1º→2º turno (p.p.)", yscale="log"); plt.show()
"""),
("md", "## 10. Resumo automático"),
("code", r"""
for t in TURNOS:
    df = T[t]
    v, s, m = A.margem(df)
    cons = A.checar_consistencia(df)
    print(f"— {t}º turno: {v} à frente de {s} por {m:,} votos ({m/df['votos_validos'].sum()*100:.2f} p.p. dos válidos).")
    print(f"  Violações aritméticas: {int(cons['secoes_violando'].sum())} ocorrências em {len(df):,} seções.")
    for c in A.principais(df, 2):
        sim = A.simular_extremos(LOCAL[(t, c)], 5)
        print(f"  {c}: {sim['observado']} seções muito destoantes do próprio local (acaso: ~{sim['esperado_medio']:.0f}).")
print("\nInterpretação: anomalias estatísticas identificam seções para inspeção; só a verificação do BU impresso, "
      "dos logs da urna e das atas da seção pode dizer se houve erro ou irregularidade.")
"""),
]
