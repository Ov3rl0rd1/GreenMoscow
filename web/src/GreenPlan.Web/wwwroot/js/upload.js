(() => {
    const zone = document.querySelector("[data-dropzone]");
    if (zone) {
        const input = zone.querySelector("input[type=file]");
        const list = zone.querySelector("[data-file-list]");
        const megabytes = (bytes) => (bytes / 1048576).toFixed(1).replace(".", ",");

        const showFiles = () => {
            const files = [...input.files];
            list.textContent = files.length
                ? files.map((file) => `${file.name} · ${megabytes(file.size)} МБ`).join("\n")
                : "";
            zone.classList.toggle("has-files", files.length > 0);
        };

        input.addEventListener("change", showFiles);
        for (const type of ["dragenter", "dragover"]) {
            zone.addEventListener(type, (event) => {
                event.preventDefault();
                zone.classList.add("is-dragging");
            });
        }
        for (const type of ["dragleave", "drop"]) {
            zone.addEventListener(type, () => zone.classList.remove("is-dragging"));
        }
        zone.addEventListener("drop", (event) => {
            event.preventDefault();
            if (event.dataTransfer?.files?.length) {
                input.files = event.dataTransfer.files;
                showFiles();
            }
        });
        showFiles();
    }

    const format = new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
    for (const element of document.querySelectorAll("[data-local-time]")) {
        const moment = new Date(element.getAttribute("datetime"));
        if (!Number.isNaN(moment.getTime())) {
            element.textContent = format.format(moment).replace(",", "");
        }
    }
})();
