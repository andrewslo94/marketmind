/*
 * dashboard_chart.js — ranked allocation bars on the portfolio dashboard.
 *
 * The route puts the chart data in the page as JSON inside
 * <script type="application/json" id="allocationData">. We read it here and
 * hand it to plotly.js (loaded from Plotly's CDN in dashboard.html).
 * One series, one hue, largest holding at the top, percentage printed at
 * the end of each bar, hover shows the dollar value.
 */
(function () {
    const el = document.getElementById("allocationChart");
    const dataEl = document.getElementById("allocationData");
    if (!el || !dataEl || typeof Plotly === "undefined") return;

    const data = JSON.parse(dataEl.textContent);
    const n = data.tickers.length;

    const trace = {
        type: "bar",
        orientation: "h",
        x: data.pcts,
        y: data.tickers,
        customdata: data.names.map((name, i) => [name, data.values[i]]),
        text: data.pcts.map(p => p.toFixed(1) + "%"),
        textposition: "outside",
        textfont: { color: "#e5e7eb", size: 12 },
        cliponaxis: false,
        marker: { color: "#3987e5", line: { width: 0 } },
        hovertemplate: "<b>%{y}</b> · %{customdata[0]}<br>%{x:.2f}% of portfolio<br>$%{customdata[1]:,.2f}<extra></extra>",
    };

    const layout = {
        height: Math.max(160, 36 * n + 60),
        margin: { l: 56, r: 48, t: 8, b: 32 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, sans-serif", color: "#9ca3af", size: 12 },
        bargap: 0.35,
        xaxis: {
            range: [0, Math.max(...data.pcts) * 1.18],
            ticksuffix: "%",
            gridcolor: "#1f2937",
            zeroline: false,
            fixedrange: true,
        },
        yaxis: {
            autorange: "reversed",   // first (largest) item at the top
            tickfont: { color: "#e5e7eb", size: 12 },
            fixedrange: true,
        },
        hoverlabel: { bgcolor: "#121826", bordercolor: "#1f2937", font: { color: "#e5e7eb" } },
    };

    Plotly.newPlot(el, [trace], layout, { displayModeBar: false, responsive: true });
})();
