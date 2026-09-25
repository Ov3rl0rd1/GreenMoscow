(() => {
    const panel = document.querySelector("[data-status-url]");
    if (!panel) {
        return;
    }

    const firstDelayMs = 2000;
    const maxDelayMs = 15000;
    const growth = 1.5;
    const tickMs = 1000;
    const url = panel.dataset.statusUrl;
    const statusText = panel.querySelector("[data-status-text]");
    const progressText = panel.querySelector("[data-progress-text]");
    const connectionText = panel.querySelector("[data-connection-text]");
    const totalRow = panel.querySelector(".stage-total");
    let delayMs = firstDelayMs;
    let timer = 0;
    let running = statusText.classList.contains("status-running");
    let syncedAt = performance.now();

    const twoDigits = (value) => String(value).padStart(2, "0");

    const formatDuration = (seconds) => {
        if (seconds < 60) {
            return `${seconds.toFixed(1).replace(".", ",").replace(/,0$/, "")} с`;
        }
        const whole = Math.round(seconds);
        const hours = Math.floor(whole / 3600);
        const minutes = Math.floor((whole % 3600) / 60);
        return hours > 0
            ? `${hours} ч ${twoDigits(minutes)} мин`
            : `${minutes} мин ${twoDigits(whole % 60)} с`;
    };

    const liveRows = () => [...panel.querySelectorAll('[data-state="current"]'), totalRow].filter(Boolean);

    const tick = () => {
        if (!running) {
            return;
        }
        const passed = (performance.now() - syncedAt) / 1000;
        for (const row of liveRows()) {
            if (row.dataset.seconds === "") {
                continue;
            }
            const cell = row.querySelector("[data-stage-time], [data-elapsed]");
            cell.textContent = formatDuration(Number(row.dataset.seconds) + passed);
        }
    };

    const showStages = (job) => {
        for (const stage of job.stages) {
            const row = panel.querySelector(`[data-stage="${stage.key}"]`);
            if (!row) {
                continue;
            }
            row.dataset.state = stage.state;
            row.dataset.seconds = stage.seconds ?? "";
            row.className = `stage stage-${stage.state}`;
            row.querySelector("[data-stage-time]").textContent = stage.timeText;
        }
        if (totalRow) {
            totalRow.dataset.seconds = job.elapsedSeconds ?? "";
            totalRow.querySelector("[data-elapsed]").textContent = job.elapsedText;
        }
        syncedAt = performance.now();
    };

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
        running = job.status === "running";
        showStages(job);
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

    window.setInterval(tick, tickMs);
    schedule();
})();
