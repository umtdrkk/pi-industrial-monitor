const MQTT_HOST = window.location.hostname;
const MQTT_PORT = 9001;
const MQTT_TOPIC = "factory/#";
const MAX_HISTORY = 40;
const SENSORS_PER_PAGE = 4;

const sensorData = {};
const charts = {};
const sensorOrder = [];
let currentPage = 0;

const client = mqtt.connect(`ws://${MQTT_HOST}:${MQTT_PORT}`);

client.on("connect", () => {
    document.getElementById("connection-status").className = "status connected";
    document.getElementById("connection-status").textContent = "Verbunden";
    client.subscribe(MQTT_TOPIC);
});

client.on("disconnect", () => {
    document.getElementById("connection-status").className = "status disconnected";
    document.getElementById("connection-status").textContent = "Getrennt";
});

client.on("message", (topic, message) => {
    const data = JSON.parse(message.toString());
    handleMessage(data);
});

function handleMessage(data) {
    if (!sensorData[data.id]) {
        sensorData[data.id] = { history: [], latest: null };
        sensorOrder.push(data.id);
        sensorOrder.sort((a, b) => a - b);
        rebuildGrid();
    }

    sensorData[data.id].latest = data;
    sensorData[data.id].history.push({
        value: data.value,
        time: new Date(data.timestamp * 1000)
    });
    if (sensorData[data.id].history.length > MAX_HISTORY) {
        sensorData[data.id].history.shift();
    }

    updateCard(data);
}

function totalPages() {
    return Math.ceil(sensorOrder.length / SENSORS_PER_PAGE);
}

function visibleSensors() {
    const start = currentPage * SENSORS_PER_PAGE;
    return sensorOrder.slice(start, start + SENSORS_PER_PAGE);
}

function rebuildGrid() {
    const grid = document.getElementById("sensor-grid");
    grid.innerHTML = "";

    // destroy existing charts cleanly
    Object.keys(charts).forEach(id => {
        charts[id].destroy();
        delete charts[id];
    });

    visibleSensors().forEach(id => {
        const entry = sensorData[id];
        if (entry && entry.latest) {
            createCard(entry.latest);
            // replay history into chart
            if (entry.history.length > 0) {
                charts[id].data.labels = entry.history.map(h =>
                    h.time.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
                );
                charts[id].data.datasets[0].data = entry.history.map(h => h.value);
                charts[id].update("none");
                // update displayed value
                document.getElementById(`value-${id}`).textContent =
                    entry.latest.value.toFixed(2);
                const percent = entry.latest.type === "voltage"
                    ? (entry.latest.value / 10) * 100
                    : entry.latest.percent ?? 0;
                document.getElementById(`fill-${id}`).style.width = `${Math.min(percent, 100)}%`;
                if (entry.latest.percent !== undefined) {
                    const pctEl = document.getElementById(`percent-${id}`);
                    if (pctEl) pctEl.textContent = `${entry.latest.percent}%`;
                }
                const date = new Date(entry.latest.timestamp * 1000);
                document.getElementById(`time-${id}`).textContent =
                    date.toLocaleTimeString("de-DE");
            }
        }
    });

    updatePageIndicator();
}

function updatePageIndicator() {
    document.getElementById("page-indicator").textContent =
        `${currentPage + 1} / ${totalPages()}`;
    document.getElementById("btn-prev").disabled = currentPage === 0;
    document.getElementById("btn-next").disabled = currentPage >= totalPages() - 1;
}

function updateCard(data) {
    if (!visibleSensors().includes(data.id)) return;

    const valueEl = document.getElementById(`value-${data.id}`);
    const fillEl  = document.getElementById(`fill-${data.id}`);
    const timeEl  = document.getElementById(`time-${data.id}`);
    const pctEl   = document.getElementById(`percent-${data.id}`);

    if (!valueEl) return;

    valueEl.textContent = data.value.toFixed(2);

    const percent = data.type === "voltage"
        ? (data.value / 10) * 100
        : data.percent ?? 0;
    fillEl.style.width = `${Math.min(percent, 100)}%`;

    if (pctEl && data.percent !== undefined) {
        pctEl.textContent = `${data.percent}%`;
    }

    const date = new Date(data.timestamp * 1000);
    timeEl.textContent = date.toLocaleTimeString("de-DE");

    if (charts[data.id]) {
        const history = sensorData[data.id].history;
        charts[data.id].data.labels = history.map(h =>
            h.time.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
        );
        charts[data.id].data.datasets[0].data = history.map(h => h.value);
        charts[data.id].update("none");
    }
}

function createCard(data) {
    const grid = document.getElementById("sensor-grid");
    const isVoltage = data.type === "voltage";
    const color   = isVoltage ? "#3b82f6" : "#10b981";
    const colorBg = isVoltage ? "rgba(59,130,246,0.08)" : "rgba(16,185,129,0.08)";

    const card = document.createElement("div");
    card.className = `sensor-card ${data.type}`;
    card.id = `card-${data.id}`;

    card.innerHTML = `
        <div class="sensor-header">
            <div class="sensor-title">
                <span class="sensor-name">${data.name}</span>
                <span class="sensor-type-badge">${isVoltage ? "0–10V" : "4–20mA"}</span>
            </div>
            <div class="sensor-right">
                <div class="sensor-value-row">
                    <span class="sensor-value" id="value-${data.id}">--</span>
                    <span class="sensor-unit">${data.unit}</span>
                </div>
                ${data.type === "current"
                    ? `<div class="sensor-percent" id="percent-${data.id}">--%</div>`
                    : ""}
            </div>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" id="fill-${data.id}" style="width:0%"></div>
        </div>
        <div class="chart-container">
            <canvas id="chart-${data.id}"></canvas>
        </div>
        <div class="timestamp" id="time-${data.id}">--</div>
    `;

    grid.appendChild(card);

    const ctx = document.getElementById(`chart-${data.id}`).getContext("2d");
    charts[data.id] = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: color,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: true,
                backgroundColor: colorBg,
            }]
        },
        options: {
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        font: { size: 9 },
                        color: "#94a3b8",
                        maxTicksLimit: 5,
                        maxRotation: 0,
                    },
                    grid: { color: "#f1f5f9" }
                },
                y: {
                    display: true,
                    ticks: {
                        font: { size: 9 },
                        color: "#94a3b8",
                        maxTicksLimit: 4,
                    },
                    grid: { color: "#f1f5f9" }
                }
            },
            responsive: true,
            maintainAspectRatio: false,
            devicePixelRatio: 2,
        }
    });
}

document.getElementById("btn-prev").addEventListener("click", () => {
    if (currentPage > 0) goToPage(currentPage - 1);
});

document.getElementById("btn-next").addEventListener("click", () => {
    if (currentPage < totalPages() - 1) goToPage(currentPage + 1);
});

function goToPage(page) {
    currentPage = page;
    rebuildGrid();
}