from amplpy import AMPL
from pypfopt import expected_returns, risk_models
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt


RISK_METHODS = [
    "sample_cov",
    "semicovariance",
    "exp_cov",
    "ledoit_wolf",
    "ledoit_wolf_constant_variance",
    "ledoit_wolf_single_factor",
    "ledoit_wolf_constant_correlation",
    "oracle_approximating",
]

RETURN_METHODS = [
    "mean_historical_return",
    "ema_historical_return",
    "capm_return",
]


def select_solver():
    solvers = ["gurobi", "mosek", "xpress", "cplex", "copt"]
    return st.selectbox("Pick the solver 👇", solvers, key="solver")


def prepare_data(prices, real_mu):
    risk_method = st.selectbox(
        "Pick the risk method 👇",
        RISK_METHODS,
        index=RISK_METHODS.index("exp_cov"),
        key="models_risk_method",
    )
    S = risk_models.risk_matrix(prices, method=risk_method)

    return_method = st.selectbox(
        "Pick the return method 👇",
        RETURN_METHODS + ["real returns"],
        index=RETURN_METHODS.index("capm_return"),
        key="models_return_method",
    )
    if return_method == "real returns":
        mu = real_mu
    else:
        mu = expected_returns.return_model(prices, method=return_method)
    tickers = list(mu.index)
    return risk_method, return_method, tickers, mu, S


def solve(ampl, risk_free_rate=0.2, skip_mu=False, real_mu=None):
    output = ampl.get_output("solve;")
    weights_df = None
    if ampl.get_value("solve_result") == "solved":
        sigma2 = ampl.get_value("sqrt(sum {i in A, j in A} w[i] * S[i, j] * w[j])")
        weights_df = ampl.var["w"].get_values().to_pandas()
        real_return = sum(weights_df["w.val"] * real_mu)
        kpis = "**KPIs:**\n"
        kpis += f"- **Annual volatility: {sigma2*100:.1f}%**\n"
        if not skip_mu:
            mu2 = ampl.get_value("sum {i in A} mu[i] * w[i]")
            sharpe2 = (mu2 - risk_free_rate) / sigma2
            kpis += f"- **Expected annual return: {mu2*100:.1f}%**\n"
            kpis += f"- **Sharpe Ratio: {sharpe2:.2f}**\n"
        kpis += f"\n**Real return: {real_return*100:.1f}%**\n"
        st.markdown(kpis)
        fig, _ = plt.subplots()
        plt.barh(weights_df.index, weights_df.iloc[:, 0])
        st.pyplot(fig)
        st.write(weights_df.transpose())
    else:
        st.write("Failed to solve. Solver output:")
    st.write(f"```\n{output}\n```")
    return weights_df


def efficient_frontier(tickers, mu, S, solver, weights, market_neutral=False):
    inf = float("inf")
    ampl = AMPL()
    ampl.eval(
        r"""
        param target_return;
        param target_variance;
        param market_neutral default 0;

        set A ordered;
        param S{A, A};
        param mu{A} default 0;

        param lb default 0;
        param ub default 1;
        var w{A} >= lb <= ub;

        minimize min_portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j];
        maximize max_portfolio_return:
            sum {i in A} mu[i] * w[i];
        maximize max_portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j];
        minimize min_portfolio_return:
            sum {i in A} mu[i] * w[i];
        s.t. target_portfolio_return:
            sum {i in A} mu[i] * w[i] >= target_return;
        s.t. target_portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j] <= target_variance;
        s.t. portfolio_weights:
            sum {i in A} w[i] = if market_neutral then 0 else 1;
        """
    )
    ampl.set["A"] = tickers
    ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
    ampl.param["mu"] = mu
    ampl.param["target_return"] = 0
    ampl.param["target_variance"] = inf
    ampl.param["market_neutral"] = market_neutral
    ampl.param["lb"] = -1 if market_neutral else 0
    ampl.option["solver"] = solver

    ampl.eval("solve min_portfolio_return;")
    min_return = ampl.get_value("min_portfolio_return")

    ampl.eval("solve max_portfolio_return;")
    max_return = ampl.get_value("max_portfolio_return")

    ampl.eval("solve min_portfolio_variance;")
    min_variance = ampl.get_value("min_portfolio_variance")

    # ampl.eval("solve max_portfolio_variance;")
    # max_variance = ampl.get_value("max_portfolio_variance")

    ampl.param["target_variance"] = min_variance
    ampl.eval("solve max_portfolio_return;")
    max_return_with_min_variance = ampl.get_value("max_portfolio_return")
    ampl.param["target_variance"] = inf

    ampl.param["target_return"] = max_return
    ampl.eval("solve min_portfolio_variance;")
    min_variance_with_max_return = ampl.get_value("min_portfolio_variance")
    ampl.param["target_return"] = 0

    ampl.var["w"] = weights
    sol_return = ampl.get_value("max_portfolio_return")
    sol_variance = ampl.get_value("min_portfolio_variance")

    st.markdown(
        f"""
    ## Efficient frontier
    - Solution variance (red): {sol_variance*100:.2f}% (solution return: {sol_return*100:.2f}%)
    - Min variance (blue): {min_variance*100:.2f}% (max return for min variance: {max_return_with_min_variance*100:.2f}%)
    - Max return (green): {max_return*100:.2f}% (min variance for max return: {min_variance_with_max_return*100:.2f}%)
    """
    )

    ampl.param["target_variance"] = inf
    max_returns, variances = [], []
    for r in np.linspace(max_return_with_min_variance, max_return, 25):
        target_return = r
        ampl.param["target_return"] = target_return
        ampl.eval("solve min_portfolio_variance;")
        max_returns.append(target_return)
        variances.append(ampl.get_value("min_portfolio_variance"))

    df = pd.DataFrame({"Return": max_returns, "Variance": variances})
    combined_chart = alt.Chart(df).mark_line().encode(x="Variance", y="Return")

    ampl.param["target_return"] = 0
    min_returns = []
    for v in variances:
        ampl.param["target_variance"] = v
        ampl.eval("solve min_portfolio_return;")
        min_returns.append(round(ampl.get_value("min_portfolio_return"), 5))

    index = min_returns.index(min(min_returns))
    if index < len(min_returns) - 1:
        variances = variances[: index + 1]
        min_returns = min_returns[: index + 1]

    df = pd.DataFrame({"Return": min_returns, "Variance": variances})
    combined_chart += alt.Chart(df).mark_line().encode(x="Variance", y="Return")

    def create_point_chart(var, ret, color, label="", dx=7, dy=0):
        point = (
            alt.Chart(pd.DataFrame({"Variance": [var], "Return": [ret]}))
            .mark_point(size=100, color=color)
            .encode(x="Variance", y="Return")
        )
        if label == "":
            return point
        text = point.mark_text(align="left", baseline="middle", dx=dx, dy=dy).encode(
            text=alt.value(label)
        )
        return point + text

    for ticker in tickers:
        ampl.var["w"] = {t: 1 if t == ticker else 0 for t in tickers}
        stock_return = ampl.get_value("max_portfolio_return")
        stock_variance = ampl.get_value("min_portfolio_variance")
        combined_chart += create_point_chart(
            stock_variance, stock_return, "black", label=ticker, dy=7
        )

    combined_chart += create_point_chart(
        min_variance, max_return_with_min_variance, "blue", label="min variance", dy=-7
    )
    combined_chart += create_point_chart(
        min_variance_with_max_return, max_return, "green", label="max return", dy=-7
    )
    combined_chart += create_point_chart(
        sol_variance, sol_return, "red", label="solution", dy=7
    )
    st.altair_chart(combined_chart, use_container_width=True)


def min_volatility(prices, real_mu):
    risk_method, _, tickers, mu, S = prepare_data(prices, real_mu)
    solver = select_solver()
    st.markdown(
        f"""
    #### Minimizing Volatility
    - Risk method: {risk_method}
    - Solver: {solver}
    """
    )
    ampl = AMPL()
    ampl.eval(
        r"""
        set A ordered;
        param S{A, A};
        param lb default 0;
        param ub default 1;
        var w{A} >= lb <= ub;
        minimize portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j];
        s.t. portfolio_weights:
            sum {i in A} w[i] = 1;
    """
    )
    ampl.set["A"] = tickers
    ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
    ampl.option["solver"] = solver
    weights_df = solve(ampl, skip_mu=True, real_mu=real_mu)
    st.markdown(
        """
        ## The implementation using [amplpy](https://amplpy.readthedocs.org/)

        ```python
        ampl = AMPL()
        ampl.eval(r\"\"\"
            set A ordered;
            param S{A, A};
            param lb default 0;
            param ub default 1;
            var w{A} >= lb <= ub;
            minimize portfolio_variance:
                sum {i in A, j in A} w[i] * S[i, j] * w[j];
            s.t. portfolio_weights:
                sum {i in A} w[i] = 1;
        \"\"\")
        ampl.set["A"] = tickers
        ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
        ampl.option["solver"] = solver
        ampl.solve()
        ```
        """
    )
    efficient_frontier(tickers, mu, S, solver, weights_df)


def efficient_risk(prices, real_mu):
    risk_method, return_method, tickers, mu, S = prepare_data(prices, real_mu)
    solver = select_solver()
    st.markdown(
        f"""
    #### Efficient Risk
    - Risk method: {risk_method}
    - Return method: {return_method}
    - Solver: {solver}
    """
    )
    target_volatility = st.slider("Target volatility?", 0.05, 1.0, 0.25, step=0.01)
    market_neutral = st.checkbox("Market neutral?")
    ampl = AMPL()
    ampl.eval(
        r"""
        param target_volatility;
        param market_neutral default 0;
        set A ordered;
        param S{A, A};
        param mu{A} default 0;
        
        param lb default 0;
        param ub default 1;
        var w{A} >= lb <= ub;
        maximize portfolio_return:
            sum {i in A} mu[i] * w[i];
        s.t. portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j] <= target_volatility^2;
        s.t. portfolio_weights:
            sum {i in A} w[i] = if market_neutral then 0 else 1;
    """
    )
    ampl.set["A"] = tickers
    ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
    ampl.param["mu"] = mu
    ampl.param["target_volatility"] = target_volatility
    ampl.param["market_neutral"] = market_neutral
    ampl.param["lb"] = -1 if market_neutral else 0
    ampl.option["solver"] = solver
    weights_df = solve(ampl, real_mu=real_mu)
    st.markdown(
        """
        ## The implementation using [amplpy](https://amplpy.readthedocs.org/)

        ```python
        ampl = AMPL()
        ampl.eval(r\"\"\"
            param target_volatility;
            param market_neutral default 0;
            set A ordered;
            param S{A, A};
            param mu{A} default 0;
            
            param lb default 0;
            param ub default 1;
            var w{A} >= lb <= ub;
            maximize portfolio_return:
                sum {i in A} mu[i] * w[i];
            s.t. portfolio_variance:
                sum {i in A, j in A} w[i] * S[i, j] * w[j] <= target_volatility^2;
            s.t. portfolio_weights:
                sum {i in A} w[i] = if market_neutral then 0 else 1;
        \"\"\")
        ampl.set["A"] = tickers
        ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
        ampl.param["mu"] = mu
        ampl.param["target_volatility"] = target_volatility
        ampl.param["market_neutral"] = market_neutral
        ampl.param["lb"] = -1 if market_neutral else 0
        ampl.option["solver"] = solver
        ampl.solve()
        ```
        """
    )
    efficient_frontier(tickers, mu, S, solver, weights_df, market_neutral)


def efficient_return(prices, real_mu):
    risk_method, return_method, tickers, mu, S = prepare_data(prices, real_mu)
    solver = select_solver()
    st.markdown(
        f"""
    #### Efficient Return
    - Risk method: {risk_method}
    - Return method: {return_method}
    - Solver: {solver}
    """
    )
    target_return = st.slider("Target return?", 0.01, 0.20, 0.10, step=0.01)
    market_neutral = st.checkbox("Market neutral?")
    ampl = AMPL()
    ampl.eval(
        r"""
        param target_return;
        param market_neutral default 0;

        set A ordered;
        param S{A, A};
        param mu{A} default 0;

        param lb default 0;
        param ub default 1;
        var w{A} >= lb <= ub;

        minimize portfolio_variance:
            sum {i in A, j in A} w[i] * S[i, j] * w[j];
        s.t. portfolio_return:
            sum {i in A} mu[i] * w[i] >= target_return;
        s.t. portfolio_weights:
            sum {i in A} w[i] = if market_neutral then 0 else 1;
        """
    )
    ampl.set["A"] = tickers
    ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
    ampl.param["mu"] = mu
    ampl.param["target_return"] = target_return
    ampl.param["market_neutral"] = market_neutral
    ampl.param["lb"] = -1 if market_neutral else 0
    ampl.option["solver"] = solver
    weights_df = solve(ampl, real_mu=real_mu)
    st.markdown(
        """
        ## The implementation using [amplpy](https://amplpy.readthedocs.org/)

        ```python
        ampl = AMPL()
        ampl.eval(r\"\"\"
            param target_return;
            param market_neutral default 0;

            set A ordered;
            param S{A, A};
            param mu{A} default 0;

            param lb default 0;
            param ub default 1;
            var w{A} >= lb <= ub;

            minimize portfolio_variance:
                sum {i in A, j in A} w[i] * S[i, j] * w[j];
            s.t. portfolio_return:
                sum {i in A} mu[i] * w[i] >= target_return;
            s.t. portfolio_weights:
                sum {i in A} w[i] = if market_neutral then 0 else 1;
        \"\"\")
        ampl.set["A"] = tickers
        ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
        ampl.param["mu"] = mu
        ampl.param["target_return"] = target_return
        ampl.param["market_neutral"] = market_neutral
        ampl.param["lb"] = -1 if market_neutral else 0
        ampl.option["solver"] = solver
        ampl.solve()
        ```
        """
    )
    efficient_frontier(tickers, mu, S, solver, weights_df, market_neutral)


def max_sharpe(prices, real_mu):
    risk_method, return_method, tickers, mu, S = prepare_data(prices, real_mu)
    solver = select_solver()
    st.markdown(
        f"""
    #### Max Sharpe
    - Risk method: {risk_method}
    - Return method: {return_method}
    - Solver: {solver}
    """
    )
    risk_free_rate = st.slider("Risk free rate?", 0.02, 0.1, 0.02, step=0.01)
    ampl = AMPL()
    ampl.eval(
        r"""
        param risk_free_rate default 0.02;

        set A ordered;
        param S{A, A};
        param mu{A} default 0;

        var k >= 0;
        var z{i in A} >= 0;  # scaled weights
        var w{i in A} = z[i] / k;

        minimize portfolio_sharpe:
            sum {i in A, j in A} z[i] * S[i, j] * z[j];
        s.t. muz:
            sum {i in A} (mu[i] - risk_free_rate) * z[i] = 1;
        s.t. portfolio_weights:
            sum {i in A}  z[i] = k;
        """
    )
    ampl.set["A"] = tickers
    ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
    ampl.param["mu"] = mu
    ampl.param["risk_free_rate"] = risk_free_rate
    ampl.option["solver"] = solver
    weights_df = solve(ampl, risk_free_rate, real_mu=real_mu)
    st.markdown(
        """
        ## The implementation using [amplpy](https://amplpy.readthedocs.org/)

        ```python
        ampl = AMPL()
        ampl.eval(r\"\"\"
            param risk_free_rate default 0.02;

            set A ordered;
            param S{A, A};
            param mu{A} default 0;

            var k >= 0;
            var z{i in A} >= 0;  # scaled weights
            var w{i in A} = z[i] / k;

            minimize portfolio_sharpe:
                sum {i in A, j in A} z[i] * S[i, j] * z[j];
            s.t. muz:
                sum {i in A} (mu[i] - risk_free_rate) * z[i] = 1;
            s.t. portfolio_weights:
                sum {i in A}  z[i] = k;
        \"\"\")
        ampl.set["A"] = tickers
        ampl.param["S"] = pd.DataFrame(S, index=tickers, columns=tickers).unstack()
        ampl.param["mu"] = mu
        ampl.param["risk_free_rate"] = risk_free_rate
        ampl.option["solver"] = solver
        ampl.solve()
        ```
        """
    )
    efficient_frontier(tickers, mu, S, solver, weights_df)
