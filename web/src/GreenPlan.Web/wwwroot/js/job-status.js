(() => {
    const panel = document.querySelector("[data-status-url]");
    if (!panel) {
        return;
    }

    const firstDelayMs = 2000;
    const maxDelayMs = 15000;
    const growth = 1.5;
    const url = panel.dataset.statusUrl;
    const statusText = panel.querySelector("[data-status-text]");
    const progressText = panel.querySelector("[data-progress-text]");
    const connectionText = panel.querySelector("[data-connection-text]");
    let delayMs = firstDelayMs;
    let timer = 0;

    const schedule = () => {
        window.clearTimeout(timer);
        if (!document.hidden) {
            timer = window.setTimeout(poll, delayMs);
        }
    };

    const show = (job) => {
        const moved = progressText && progressText.textContent !== job.progressText;
        statusText.textContent = job.statusText;
        statusText.className = `status status-${job.status}`;
        if (progressText) {
            progressText.textContent = job.progressText;
        }
        delayMs = moved ? firstDelayMs : Math.min(maxDelayMs, delayMs * growth);
    };

    const poll = async () => {
        try {
            const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
            if (!response.ok) {
                throw new Error(`status ${response.status}`);
            }
            const job = await response.json();
            if (job.finished) {
                window.location.reload();
                return;
            }
            show(job);
            if (connectionText) {
                connectionText.hidden = true;
            }
        } catch {
            if (connectionText) {
                connectionText.hidden = false;
            }
            delayMs = maxDelayMs;
        }
        schedule();
    };

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            window.clearTimeout(timer);
            return;
        }
        delayMs = firstDelayMs;
        poll();
    });

    schedule();
})();
