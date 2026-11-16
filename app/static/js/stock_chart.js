/*
 * stock_chart.js — price-history line chart on the stock detail page.
 *
 * Clicking a range button fetches /stocks/<T>/history.json?range=<R> and
 * redraws. One series, one hue, 2px line, unified hover (crosshair +
 * tooltip). Non-trading hours and weekends are removed from the x-axis
 * with Plotly "rangebreaks" so intraday charts don't show flat overnight gaps.
 */
(function () {
    const el = document.getElementById("stockChart");
    const summary = document.getElementById("chartSummary");
    const buttons = document.querySelectorAll(".mm-range-group button");
    if (!el || typeof Plotly === "undefined") return;

    const baseUrl = el.dataset.historyUrl;
    let current = null;

    function money(n) {
        return Number(n).toLocaleString(undefined, { style: "currency", currency: "USD" });
    }

    function setActive(range) {
        buttons.forEach(b => b.classList.toggle("active", b.dataset.range === range));
    }

    function draw(data) {
        const pts = data.points;
        const x = pts.map(p => p.t);
        const y = pts.map(p => p.c);
        const first = y[0], last = y[y.length - 1];
        const change = last - first, pct = change / first * 100;
        const up = change >= 0;

        const trace = {
            type: "scatter",
            mode: "lines",
            x, y,
            line: { color: "#3987e5", width: 2 },
            fill: "tozeroy",
            fillcolor: "rgba(57, 135, 229, 0.08)",
            hovertemplate: "%{y:$,.2f}<extra></extra>",
            name: data.ticker,
        };

        const rangebreaks = [{ bounds: ["sat", "mon"] }];
        if (data.intraday) rangebreaks.push({ bounds: [16, 9.5], pattern: "hour" });

        const layout = {
            height: 360,
            margin: { l: 56, r: 16, t: 8, b: 40 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Inter, sans-serif", color: "#9ca3af", size: 12 },
            hovermode: "x unified",
            hoverlabel: { bgcolor: "#121826", bordercolor: "#1f2937", font: { color: "#e5e7eb" } },
            xaxis: {
                type: "date",
                gridcolor: "#1f2937",
                showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: "#4b5563", spikedash: "dot",
                rangebreaks,
                tickformat: data.intraday ? "%-I:%M %p" : undefined,
                hoverformat: data.intraday ? "%b %d, %-I:%M %p ET" : "%b %d, %Y",
            },
            yaxis: {
                gridcolor: "#1f2937",
                tickprefix: "$",
                zeroline: false,
                fixedrange: true,
                // Don't start at zero: that would flatten the line. Pad the data range instead.
                range: [Math.min(...y) * 0.995, Math.max(...y) * 1.005],
            },
            showlegend: false,
        };

        Plotly.react(el, [trace], layout, { displayModeBar: false, responsive: true });

        const lo = Math.min(...y), hi = Math.max(...y);
        summary.innerHTML =
            '<span class="' + (up ? "mm-gain" : "mm-loss") + ' fw-semibold">' +
            (up ? "▲ " : "▼ ") + (up ? "+" : "-") + money(Math.abs(change)) + " (" + (up ? "+" : "") + pct.toFixed(2) + "%)" +
            "</span> over " + data.range + " · range " + money(lo) + " – " + money(hi) +
            " · " + pts.length + " " + data.interval + " bars · closes, " +
            (data.intraday ? "times in ET" : "daily/weekly/monthly") +
            " · Delayed data · " + data.source +
            (data.stale ? " · <strong>stale</strong> (provider unreachable, last cached data)" : "");
    }

    async function load(range) {
        if (range === current) return;
        current = range;
        setActive(range);
        summary.textContent = "Loading " + range + "…";
        let data;
        try {
            const resp = await fetch(baseUrl + "?range=" + encodeURIComponent(range));
            data = await resp.json();
        } catch (err) {
            summary.textContent = "Data unavailable — couldn't reach the server.";
            return;
        }
        if (!data.ok || !data.points.length) {
            Plotly.purge(el);
            summary.textContent = "Data unavailable for " + range + (data.reason === "unavailable" ? " (provider unreachable)." : ".");
            return;
        }
        draw(data);
    }

    buttons.forEach(b => b.addEventListener("click", () => load(b.dataset.range)));
    load("1M");
})();
