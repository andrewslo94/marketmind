/*
 * market_chart.js — "U.S. index performance" on the Market Overview page.
 *
 * Plots each index's percent change since the first close of the chosen
 * period, so indexes at very different levels share one axis. Data comes
 * from /market/performance.json (see routes/market.py).
 *
 * Chart rules followed:
 *  - one fixed color per index (color follows the index, never its rank),
 *    checked for color-blind safety against the card background;
 *  - 2px lines, an end-dot on each line with a ring in the card color;
 *  - a legend always; end labels only when they have room not to collide;
 *  - a table under the chart with every number the chart shows;
 *  - while a new period loads, the old chart stays, dimmed.
 */
(function () {
    const el = document.getElementById("perfChart");
    const tbody = document.querySelector("#perfTable tbody");
    const note = document.getElementById("perfNote");
    const buttons = document.querySelectorAll("#perfRanges button");
    if (!el || !tbody || !note || typeof Plotly === "undefined") return;

    const COLORS = { "^GSPC": "#3987e5", "^IXIC": "#d95926", "^RUT": "#199e70" };
    const SURFACE = "#121826", TEXT = "#e5e7eb", MUTED = "#9ca3af", GRID = "#1f2937", BASELINE = "#4b5563";
    const HEIGHT = 380;
    const MIN_LABEL_GAP_PX = 18;   // end labels closer than this would overlap
    const MIN_WIDTH_FOR_LABELS = 640;

    let current = null;

    const last = arr => arr[arr.length - 1];
    const pct = v => (v > 0 ? "+" : "") + v.toFixed(2) + "%";
    const level = v => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const niceDate = iso => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

    function setActive(range) {
        buttons.forEach(b => {
            const on = b.dataset.range === range;
            b.classList.toggle("active", on);
            b.setAttribute("aria-pressed", on ? "true" : "false");
        });
    }

    // End labels fit only if every pair of line ends is at least
    // MIN_LABEL_GAP_PX apart on screen. Otherwise the legend and table carry
    // the names (nudging labels away from their lines would mislead).
    function labelsFit(series, lo, hi, plotHeight) {
        if (el.clientWidth < MIN_WIDTH_FOR_LABELS) return false;
        const ends = series.map(s => last(s.y)).sort((a, b) => a - b);
        const pxPerUnit = plotHeight / (hi - lo);
        for (let i = 1; i < ends.length; i++) {
            if ((ends[i] - ends[i - 1]) * pxPerUnit < MIN_LABEL_GAP_PX) return false;
        }
        return true;
    }

    function draw(data) {
        const series = data.series;
        const all = series.flatMap(s => s.y);
        let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
        const pad = (hi - lo) * 0.08 || 1;
        lo -= pad; hi += pad;

        // Fixed x range from the first to the last date. (Autorange pads the
        // axis 5% wherever there are dot markers, leaving an empty strip.)
        const xStart = series.map(s => s.x[0]).sort()[0];
        const xEnd = series.map(s => last(s.x)).sort().pop();

        const margin = { l: 56, r: 20, t: 36, b: 40 };
        const fit = labelsFit(series, lo, hi, HEIGHT - margin.t - margin.b);
        if (fit) margin.r = 200;

        const lines = series.map(s => ({
            type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y, customdata: s.close,
            line: { color: COLORS[s.symbol] || MUTED, width: 2 },
            // Value first, then the name and the index level.
            hovertemplate: "<b>%{y:+.2f}%</b>  " + s.name + " · %{customdata:,.2f}<extra></extra>",
        }));
        const dots = series.map(s => ({
            type: "scatter", mode: "markers", x: [last(s.x)], y: [last(s.y)],
            marker: { color: COLORS[s.symbol] || MUTED, size: 9, line: { color: SURFACE, width: 2 } },
            cliponaxis: false,   // the dot sits on the plot's right edge; don't cut it in half
            hoverinfo: "skip", showlegend: false,
        }));
        // xref "paper", x 1 = the right edge of the plot, where every line
        // ends. (Data coordinates would make Plotly stretch the time axis to
        // fit the label text inside the plot.)
        const annotations = fit ? series.map(s => ({
            x: 1, y: last(s.y), xref: "paper", yref: "y", showarrow: false,
            xanchor: "left", xshift: 10, align: "left",
            text: s.name + "  <b>" + pct(s.change_pct) + "</b>",
            font: { color: TEXT, size: 12 },
        })) : [];

        const layout = {
            height: HEIGHT, margin,
            paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Inter, sans-serif", color: MUTED, size: 12 },
            showlegend: true,
            // itemclick off: hiding a line would leave its dot and label behind.
            legend: { orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom",
                      font: { color: TEXT }, itemclick: false, itemdoubleclick: false },
            hovermode: "x unified",
            hoverlabel: { bgcolor: SURFACE, bordercolor: GRID, font: { color: TEXT } },
            xaxis: {
                type: "date", gridcolor: GRID, range: [xStart, xEnd], autorange: false,
                showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: BASELINE, spikedash: "solid",
                rangebreaks: data.range === "5Y" ? [] : [{ bounds: ["sat", "mon"] }],
                hoverformat: "%b %d, %Y",
            },
            yaxis: {
                range: [lo, hi], ticksuffix: "%", gridcolor: GRID, fixedrange: true,
                zeroline: true, zerolinecolor: BASELINE, zerolinewidth: 1,
            },
            annotations,
        };

        Plotly.react(el, lines.concat(dots), layout, { displayModeBar: false, responsive: true });
        fillTable(series);
        fillNote(data, series);
    }

    // Table view: built with textContent (never innerHTML) for every value.
    function fillTable(series) {
        tbody.replaceChildren();
        series.forEach(s => {
            const tr = document.createElement("tr");

            const name = document.createElement("td");
            name.className = "text-nowrap";
            const key = document.createElement("span");
            key.className = "mm-line-key";
            key.style.background = COLORS[s.symbol] || MUTED;
            name.append(key, document.createTextNode(s.name));

            const change = document.createElement("td");
            const dir = s.change_pct > 0 ? "up" : s.change_pct < 0 ? "down" : "flat";
            change.className = "text-end text-nowrap fw-semibold " + (dir === "up" ? "mm-gain" : dir === "down" ? "mm-loss" : "mm-muted");
            change.textContent = (dir === "up" ? "▲ " : dir === "down" ? "▼ " : "● ") + pct(s.change_pct);

            tr.append(name, change, valueCell(level(s.start), niceDate(s.start_date)), valueCell(level(s.end), niceDate(s.end_date)));
            tbody.append(tr);
        });
    }

    function valueCell(main, sub) {
        const td = document.createElement("td");
        td.className = "text-end";
        const a = document.createElement("div");
        a.className = "mm-num";
        a.textContent = main;
        const b = document.createElement("div");
        b.className = "mm-row-sub";
        b.textContent = sub;
        td.append(a, b);
        return td;
    }

    function fillNote(data, series) {
        const parts = [
            (data.interval === "1wk" ? "Weekly" : "Daily") + " closes; the latest point is the most recent delayed value",
            "Delayed data · " + data.source,
        ];
        if (data.fetched_at) parts.push("fetched " + new Date(data.fetched_at).toLocaleString());
        if (data.stale) parts.push("provider unreachable, showing cached history");
        const failed = Object.keys(data.failed || {});
        if (failed.length) parts.push("Data unavailable: " + failed.join(", "));
        note.textContent = parts.join(" · ") + ".";
    }

    async function load(range) {
        if (range === current) return;
        current = range;
        setActive(range);
        el.classList.add("mm-chart-loading");
        note.textContent = "Loading " + range + "…";

        let data;
        try {
            const resp = await fetch(el.dataset.url + "?range=" + encodeURIComponent(range),
                                     { headers: { Accept: "application/json" } });
            data = await resp.json();
        } catch (err) {
            data = { ok: false, reason: "network" };
        }
        if (range !== current) return;   // a newer click is already loading
        el.classList.remove("mm-chart-loading");

        if (!data.ok || !data.series || !data.series.length) {
            Plotly.purge(el);
            tbody.replaceChildren();
            note.textContent = "Data unavailable for " + range +
                (data.reason === "unavailable" ? ": the price provider can't be reached right now." : ".");
            return;
        }
        draw(data);
    }

    buttons.forEach(b => b.addEventListener("click", () => load(b.dataset.range)));
    load(el.dataset.default || "1Y");
})();
