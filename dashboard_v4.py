# ============================================================
# DASHBOARD DE INDICADORES ECONÔMICOS — versão 4 (reforçada)
# ============================================================
# Novidades desta versão:
#   • Bitcoin (BTC-USD) incluído na análise
#   • Cada indicador carrega de forma INDEPENDENTE: se uma
#     fonte falhar, o resto do dashboard continua funcionando
#   • Correção de fuso horário dos dados do Yahoo Finance
#   • Proteção contra séries vazias ou com poucos dados
#   • Números formatados no padrão brasileiro (1.234,56)
#
# Para rodar:  py -3.13 -m streamlit run dashboard_v4.py
# ============================================================

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import yfinance as yf
from datetime import date, timedelta

# ---- PALETA DO PROJETO -------------------------------------
COR_FUNDO       = "#0E1522"  # azul-marinho profundo
COR_CARTAO      = "#182338"  # fundo dos cartões
COR_DOURADO     = "#E3B04B"  # destaque principal (SELIC)
COR_PETROLEO    = "#4FA8A0"  # verde-petróleo (dólar, quedas)
COR_TERRACOTA   = "#C96A5B"  # altas "ruins" (inflação)
COR_ACO         = "#6E93C9"  # azul-aço (Ibovespa)
COR_LILAS       = "#9A7BC8"  # lilás (Bitcoin)
COR_TEXTO       = "#E8E6E1"
COR_TEXTO_SUAVE = "#8A93A6"
COR_GRADE       = "#243149"

st.set_page_config(
    page_title="Indicadores Econômicos BR",
    page_icon="📊",
    layout="wide",
)

# ---- CSS CUSTOMIZADO ---------------------------------------
st.markdown(
    f"""
    <style>
    div[data-testid="stMetric"] {{
        background-color: {COR_CARTAO};
        border: 1px solid {COR_GRADE};
        border-top: 3px solid {COR_DOURADO};
        border-radius: 10px;
        padding: 16px 18px;
    }}
    div[data-testid="stMetric"] label p {{
        color: {COR_TEXTO_SUAVE};
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
    }}
    h1 {{
        border-bottom: 2px solid {COR_DOURADO};
        padding-bottom: 0.4rem;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {COR_DOURADO} !important;
        border-bottom-color: {COR_DOURADO} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- FUNÇÕES AUXILIARES ------------------------------------

def fmt(valor: float, casas: int = 2) -> str:
    """Formata número no padrão brasileiro: 1.234.567,89"""
    texto = f"{valor:,.{casas}f}"
    # O Python usa vírgula pra milhar e ponto pra decimal (padrão
    # americano). Trocamos os dois usando um caractere temporário:
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def ultimo_e_anterior(df: pd.DataFrame):
    """Retorna o último valor da série e o anterior a ele.
    Se a série tiver um dado só, retorna o mesmo valor duas vezes
    (assim a variação dá zero em vez de quebrar o app)."""
    atual = float(df["valor"].iloc[-1])
    anterior = float(df["valor"].iloc[-2]) if len(df) > 1 else atual
    return atual, anterior


def estilizar(fig):
    """Aplica o tema escuro-elegante a um gráfico Plotly."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COR_TEXTO, size=13),
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        hoverlabel=dict(bgcolor=COR_CARTAO, font_color=COR_TEXTO),
    )
    fig.update_xaxes(showgrid=False, linecolor=COR_GRADE)
    fig.update_yaxes(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE)
    return fig

# ---- FUNÇÕES DE BUSCA DE DADOS -----------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_serie_bcb(codigo: int, data_inicial: date, data_final: date) -> pd.DataFrame:
    """Busca uma série na API SGS do Banco Central do Brasil."""
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        f"?formato=json"
        f"&dataInicial={data_inicial.strftime('%d/%m/%Y')}"
        f"&dataFinal={data_final.strftime('%d/%m/%Y')}"
    )
    resposta = requests.get(url, timeout=30)
    resposta.raise_for_status()
    dados_json = resposta.json()
    if not dados_json:  # lista vazia = período sem dados
        raise RuntimeError("A API do Banco Central não retornou dados.")
    df = pd.DataFrame(dados_json)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        raise RuntimeError("A série veio sem valores válidos.")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_yahoo(ticker: str, data_inicial: date, data_final: date) -> pd.DataFrame:
    """Busca o fechamento diário de um ativo no Yahoo Finance,
    devolvendo no MESMO formato das séries do BCB (data, valor)."""
    dados = yf.download(
        ticker,
        start=data_inicial,
        # +1 dia porque o yfinance NÃO inclui a data final no resultado:
        end=data_final + timedelta(days=1),
        progress=False,
        auto_adjust=True,
    )
    if dados.empty:
        raise RuntimeError(f"O Yahoo Finance não retornou dados de {ticker}.")

    # O yfinance às vezes devolve colunas "aninhadas" (MultiIndex).
    # Pegamos a coluna de fechamento de forma segura nos dois casos:
    fechamento = dados["Close"]
    if isinstance(fechamento, pd.DataFrame):
        fechamento = fechamento.iloc[:, 0]

    # As datas do Yahoo podem vir com fuso horário; as do BCB, não.
    # Misturar os dois tipos quebra o pandas — então removemos o fuso:
    indice = pd.to_datetime(dados.index)
    if indice.tz is not None:
        indice = indice.tz_localize(None)

    df = pd.DataFrame({
        "data": indice,
        "valor": pd.to_numeric(fechamento.values, errors="coerce"),
    })
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        raise RuntimeError(f"A série de {ticker} veio sem valores válidos.")
    return df

# ---- BARRA LATERAL -----------------------------------------
st.sidebar.title("⚙️ Filtros")
anos_historico = st.sidebar.slider("Período de análise (anos)", 1, 10, 3)
data_final = date.today()
data_inicial = data_final - timedelta(days=365 * anos_historico)
st.sidebar.markdown("---")
st.sidebar.caption(
    "Fontes: API SGS do Banco Central (IPCA, SELIC, dólar) "
    "e Yahoo Finance (Ibovespa, Bitcoin)."
)

# ---- TÍTULO ------------------------------------------------
st.title("📊 Indicadores Econômicos do Brasil")
st.markdown(
    f"<span style='color:{COR_TEXTO_SUAVE}'>"
    f"{data_inicial.strftime('%d/%m/%Y')} — {data_final.strftime('%d/%m/%Y')}</span>",
    unsafe_allow_html=True,
)

# ---- CARREGAMENTO TOLERANTE A FALHAS -----------------------
# Cada indicador tem sua própria "receita" de busca. Carregamos
# um por um dentro de try/except: se uma fonte estiver fora do
# ar, guardamos o nome dela em "falhas" e seguimos com as outras.
FONTES = {
    "IPCA":     lambda: buscar_serie_bcb(433,  data_inicial, data_final),
    "SELIC":    lambda: buscar_serie_bcb(4189, data_inicial, data_final),
    "Dólar":    lambda: buscar_serie_bcb(1,    data_inicial, data_final),
    "Ibovespa": lambda: buscar_yahoo("^BVSP",   data_inicial, data_final),
    "Bitcoin":  lambda: buscar_yahoo("BTC-USD", data_inicial, data_final),
}

series = {}   # indicadores carregados com sucesso
falhas = []   # nomes dos que falharam

with st.spinner("Buscando dados nas fontes públicas..."):
    for nome, receita in FONTES.items():
        try:
            series[nome] = receita()
        except Exception:
            falhas.append(nome)

if falhas:
    st.warning(
        "⚠️ Não consegui carregar agora: **" + ", ".join(falhas) + "**. "
        "O restante do dashboard segue funcionando. "
        "Verifique sua internet e recarregue a página (tecla R)."
    )

if not series:
    st.error("😕 Nenhuma fonte de dados respondeu. Verifique sua conexão.")
    st.stop()

# ---- CARTÕES DE RESUMO -------------------------------------
# Criamos um cartão para CADA indicador que carregou, lado a lado.
colunas = st.columns(len(series))

for coluna, (nome, df) in zip(colunas, series.items()):
    atual, anterior = ultimo_e_anterior(df)
    if nome == "IPCA":
        coluna.metric(
            "IPCA (mês)", f"{fmt(atual)}%",
            f"{fmt(atual - anterior)} p.p.", delta_color="inverse",
        )
    elif nome == "SELIC":
        coluna.metric("SELIC (meta)", f"{fmt(atual)}% a.a.")
    elif nome == "Dólar":
        coluna.metric(
            "Dólar", f"R$ {fmt(atual)}",
            fmt(atual - anterior), delta_color="inverse",
        )
    elif nome == "Ibovespa":
        variacao = (atual / anterior - 1) * 100 if anterior else 0.0
        coluna.metric("Ibovespa", f"{fmt(atual, 0)} pts", f"{fmt(variacao)}%")
    elif nome == "Bitcoin":
        variacao = (atual / anterior - 1) * 100 if anterior else 0.0
        coluna.metric("Bitcoin", f"US$ {fmt(atual, 0)}", f"{fmt(variacao)}%")

st.markdown("")

# ---- ABAS --------------------------------------------------
aba_ipca, aba_selic, aba_dolar, aba_ibov, aba_btc, aba_comp, aba_dados = st.tabs(
    ["📈 IPCA", "🏦 SELIC", "💵 Dólar", "🏛️ Ibovespa", "₿ Bitcoin",
     "🔍 Comparação", "🗂️ Dados brutos"]
)

def aviso_indisponivel(nome: str):
    """Mensagem padrão quando um indicador não carregou."""
    st.info(f"Os dados de {nome} não estão disponíveis no momento. "
            "Recarregue a página para tentar de novo.")

# --- IPCA ---
with aba_ipca:
    if "IPCA" not in series:
        aviso_indisponivel("IPCA")
    else:
        ipca = series["IPCA"]
        st.subheader("IPCA — variação mensal (%)")
        st.caption("Inflação oficial do Brasil, medida pelo IBGE.")
        fig = px.bar(
            ipca, x="data", y="valor",
            labels={"data": "Mês", "valor": "Variação (%)"},
            color=ipca["valor"] > 0,
            color_discrete_map={True: COR_TERRACOTA, False: COR_PETROLEO},
        )
        st.plotly_chart(estilizar(fig), width="stretch")
        acumulado = ((1 + ipca["valor"] / 100).prod() - 1) * 100
        st.info(f"📌 Inflação acumulada no período: **{fmt(acumulado)}%**")

# --- SELIC ---
with aba_selic:
    if "SELIC" not in series:
        aviso_indisponivel("SELIC")
    else:
        selic = series["SELIC"]
        st.subheader("Taxa SELIC — meta do Copom (% ao ano)")
        st.caption("A taxa básica de juros da economia brasileira.")
        fig = px.line(selic, x="data", y="valor",
                      labels={"data": "Data", "valor": "Taxa (% a.a.)"})
        fig.update_traces(line_color=COR_DOURADO, line_width=3)
        st.plotly_chart(estilizar(fig), width="stretch")

# --- DÓLAR ---
with aba_dolar:
    if "Dólar" not in series:
        aviso_indisponivel("Dólar")
    else:
        dolar = series["Dólar"]
        st.subheader("Dólar comercial — cotação de venda (R$)")
        fig = px.area(dolar, x="data", y="valor",
                      labels={"data": "Data", "valor": "Cotação (R$)"})
        fig.update_traces(line_color=COR_PETROLEO,
                          fillcolor="rgba(79, 168, 160, 0.15)")
        st.plotly_chart(estilizar(fig), width="stretch")
        c1, c2 = st.columns(2)
        c1.metric("Máxima no período", f"R$ {fmt(dolar['valor'].max())}")
        c2.metric("Mínima no período", f"R$ {fmt(dolar['valor'].min())}")

# --- IBOVESPA ---
with aba_ibov:
    if "Ibovespa" not in series:
        aviso_indisponivel("Ibovespa")
    else:
        ibov = series["Ibovespa"]
        st.subheader("Ibovespa — fechamento diário (pontos)")
        st.caption("Principal índice da bolsa brasileira (B3). Fonte: Yahoo Finance.")
        fig = px.line(ibov, x="data", y="valor",
                      labels={"data": "Data", "valor": "Pontos"})
        fig.update_traces(line_color=COR_ACO, line_width=2.5)
        st.plotly_chart(estilizar(fig), width="stretch")
        retorno = (ibov["valor"].iloc[-1] / ibov["valor"].iloc[0] - 1) * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("Retorno no período", f"{fmt(retorno, 1)}%")
        c2.metric("Máxima", f"{fmt(ibov['valor'].max(), 0)} pts")
        c3.metric("Mínima", f"{fmt(ibov['valor'].min(), 0)} pts")

# --- BITCOIN (NOVO) ---
with aba_btc:
    if "Bitcoin" not in series:
        aviso_indisponivel("Bitcoin")
    else:
        btc = series["Bitcoin"]
        st.subheader("Bitcoin — cotação diária (US$)")
        st.caption(
            "Preço do Bitcoin em dólares americanos (par BTC-USD). "
            "Fonte: Yahoo Finance. Cripto negocia 24h, inclusive fins de semana."
        )
        fig = px.area(btc, x="data", y="valor",
                      labels={"data": "Data", "valor": "Preço (US$)"})
        fig.update_traces(line_color=COR_LILAS,
                          fillcolor="rgba(154, 123, 200, 0.15)")
        st.plotly_chart(estilizar(fig), width="stretch")
        retorno = (btc["valor"].iloc[-1] / btc["valor"].iloc[0] - 1) * 100
        c1, c2, c3 = st.columns(3)
        c1.metric("Retorno no período", f"{fmt(retorno, 1)}%")
        c2.metric("Máxima", f"US$ {fmt(btc['valor'].max(), 0)}")
        c3.metric("Mínima", f"US$ {fmt(btc['valor'].min(), 0)}")

# --- COMPARAÇÃO ---
with aba_comp:
    st.subheader("Comparação entre indicadores")

    disponiveis = list(series.keys())
    padrao = [n for n in ["SELIC", "Ibovespa", "Bitcoin"] if n in disponiveis]
    escolhidos = st.multiselect(
        "Indicadores para comparar:", disponiveis, default=padrao
    )
    modo = st.radio(
        "Modo de exibição:",
        ["Índice base 100 (escala comparável)", "Valores originais (mesmo eixo)"],
        horizontal=True,
    )

    if not escolhidos:
        st.info("Selecione pelo menos um indicador acima. 👆")
    else:
        # Tudo na frequência mensal (o IPCA já é mensal; os
        # diários viram média do mês):
        def mensalizar(nome):
            s = series[nome].set_index("data")["valor"]
            return s if nome == "IPCA" else s.resample("MS").mean()

        df_comp = pd.DataFrame({n: mensalizar(n) for n in escolhidos}).dropna()

        if len(df_comp) < 2:
            st.info(
                "Não há meses suficientes em comum entre os indicadores "
                "escolhidos. Tente aumentar o período no filtro lateral."
            )
        else:
            if modo.startswith("Índice"):
                df_plot = df_comp.copy()
                for col in df_plot.columns:
                    if col == "IPCA":
                        # IPCA é variação: acumulamos pra virar índice
                        df_plot[col] = (1 + df_plot[col] / 100).cumprod() * 100
                    else:
                        df_plot[col] = df_plot[col] / df_plot[col].iloc[0] * 100
                rotulo_y = "Índice (início do período = 100)"
                st.caption(
                    "Todas as séries começam em 100 — uma linha em 110 "
                    "significa alta de 10% desde o início do período."
                )
            else:
                df_plot = df_comp
                rotulo_y = "Valor (unidades originais)"
                st.caption(
                    "⚠️ Unidades diferentes no mesmo eixo (%, R$, pontos, US$). "
                    "Séries grandes como Ibovespa e Bitcoin 'esmagam' as demais — "
                    "para comparar de verdade, prefira o modo base 100."
                )

            df_longo = df_plot.reset_index().melt(
                id_vars="data", var_name="Indicador", value_name="valor"
            )
            fig = px.line(
                df_longo, x="data", y="valor", color="Indicador",
                labels={"data": "Data", "valor": rotulo_y},
                color_discrete_map={
                    "IPCA": COR_TERRACOTA, "SELIC": COR_DOURADO,
                    "Dólar": COR_PETROLEO, "Ibovespa": COR_ACO,
                    "Bitcoin": COR_LILAS,
                },
            )
            fig.update_traces(line_width=2.5)
            fig = estilizar(fig)
            fig.update_layout(
                showlegend=True,
                legend=dict(orientation="h", y=1.12, title=None),
            )
            st.plotly_chart(fig, width="stretch")

# --- DADOS BRUTOS ---
with aba_dados:
    st.subheader("Tabelas de dados")
    st.caption("Os dados como vieram das fontes. Baixe em CSV pelo ícone da tabela.")
    escolha = st.selectbox("Escolha o indicador:", list(series.keys()))
    st.dataframe(series[escolha], width="stretch", hide_index=True)

# ---- RODAPÉ ------------------------------------------------
st.markdown("---")
st.caption(
    "Feito com Python + Streamlit • Dados: Banco Central do Brasil e Yahoo Finance"
)