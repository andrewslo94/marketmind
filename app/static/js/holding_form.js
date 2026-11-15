/*
 * holding_form.js — on the add/edit holding form, look up the ticker the
 * user typed and show the company name + current (delayed) price.
 *
 * How it works:
 *   1. When the ticker field loses focus (or Enter is pressed), call our own
 *      JSON endpoint /portfolio/quote/<TICKER>  (see routes/portfolio.py).
 *   2. Show the result in the box under the field.
 *   3. If the price field is still empty, fill it with the current price as a
 *      starting point. The user can overwrite it — what they actually paid is
 *      what matters for cost basis.
 *
 * fetch() is the browser's built-in way to make an HTTP request from
 * JavaScript without reloading the page.
 */
(function () {
    const tickerInput = document.getElementById("ticker");
    const priceInput = document.getElementById("avg_price");
    const box = document.getElementById("quoteBox");
    if (!tickerInput || !priceInput || !box) return;

    const urlTemplate = box.dataset.quoteUrl;   // ".../portfolio/quote/__T__"
    let lastLookedUp = "";
    let autoFilledPrice = null;                 // remember what *we* put in

    function show(html, state) {
        box.innerHTML = html;
        box.classList.remove("d-none", "is-error", "is-warn");
        if (state) box.classList.add(state);
    }

    function money(value, currency) {
        const n = Number(value);
        if (!isFinite(n)) return "Data unavailable";
        return n.toLocaleString(undefined, { style: "currency", currency: currency || "USD" });
    }

    function formatTime(iso) {
        if (!iso) return "time unavailable";
        const d = new Date(iso);
        return isNaN(d) ? "time unavailable" : d.toLocaleString();
    }

    function maybeFillPrice(price) {
        const current = priceInput.value.trim();
        // Fill if empty, or if the only thing in there is our previous auto-fill.
        if (current === "" || (autoFilledPrice !== null && current === autoFilledPrice)) {
            autoFilledPrice = Number(price).toFixed(2);
            priceInput.value = autoFilledPrice;
            return true;
        }
        return false;
    }

    async function lookup() {
        const ticker = tickerInput.value.trim().toUpperCase();
        tickerInput.value = ticker;
        if (!ticker || ticker === lastLookedUp) return;
        lastLookedUp = ticker;

        show('<span class="mm-quote-meta">Looking up ' + ticker + '…</span>');

        let data;
        try {
            const resp = await fetch(urlTemplate.replace("__T__", encodeURIComponent(ticker)),
                                     { headers: { "Accept": "application/json" } });
            data = await resp.json();
        } catch (err) {
            show("Data unavailable — couldn't reach the server.", "is-error");
            return;
        }

        if (!data.ok) {
            if (data.reason === "not_found") {
                show("<strong>" + ticker + "</strong> was not found as a stock or ETF symbol.", "is-error");
            } else if (data.reason === "unavailable") {
                show("Data unavailable — the price provider can't be reached right now. " +
                     "You can still save the holding and enter the price yourself.", "is-warn");
            } else {
                show("Enter a valid ticker symbol.", "is-error");
            }
            return;
        }

        const filled = maybeFillPrice(data.price);
        const stateNote = data.market_state === "REGULAR" ? "market open" : "market " + (data.market_state || "").toLowerCase();
        show(
            '<div><strong>' + data.name + '</strong> <span class="mm-quote-meta">(' + data.ticker + ')</span></div>' +
            '<div class="mm-quote-price">' + money(data.price, data.currency) + '</div>' +
            '<div class="mm-quote-meta">Delayed data · ' + stateNote + ' · quote time ' + formatTime(data.market_time) +
            (data.stale ? ' · <strong>stale</strong> (provider unreachable, showing last cached value)' : '') +
            ' · ' + data.source + '</div>' +
            (filled
                ? '<div class="mm-quote-meta mt-1">Filled the price box with the current price. Change it to what you actually paid.</div>'
                : '<div class="mm-quote-meta mt-1">Price box left as you entered it.</div>'),
            data.stale ? "is-warn" : null
        );
    }

    tickerInput.addEventListener("blur", lookup);
    tickerInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); lookup(); }
    });
    // On the edit page the ticker is already filled in: look it up right away.
    if (tickerInput.value.trim()) lookup();
})();
