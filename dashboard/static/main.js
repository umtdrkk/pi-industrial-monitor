const MQTT_HOST = window.location.hostname;
const MQTT_PORT = 9001;
const MQTT_TOPIC = "factory/#";
const MAX_HISTORY = 60;

// Flask API base URL — same host as dashboard, port 5001
// On Pi this resolves to the Pi's IP, on Mac to localhost
const API_BASE = `http://${window.location.hostname}:5001`;

// category -> visual type. Add a new category here and every
// sensor with that category automatically gets the right chart.
const VISUAL_MAP = {
    "distance":    "gauge",
    "temperature": "line",
    "pressure":    "line",
    "default":     "line",
};

const sensorData = {};
const charts = {};
let knownSensorCount = 0;

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
        sensorData[data.id] = { history: [] };
        createCard(data);
        rebalanceGrid();
        // Fetch averages immediately when a new sensor card is created
        fetchAverages(data.id);
    }

    sensorData[data.id].history.push({
        value: data.value,
        time: new Date(data.timestamp * 1000)
    });
    if (sensorData[data.id].history.length > MAX_HISTORY) {
        sensorData[data.id].history.shift();
    }

    updateCard(data);
}

// Fetches historical averages from Flask API and updates the card
async function fetchAverages(sensorId) {
    try {
        const response = await fetch(`${API_BASE}/api/sensors/${sensorId}/average`);
        const data = await response.json();
        updateAverages(sensorId, data.averages);
    } catch (err) {
        // Flask might not be running — fail silently, live data still works
        console.warn(`Could not fetch averages for sensor ${sensorId}:`, err);
    }
}

// Updates the averages section on a sensor card
function updateAverages(sensorId, averages) {
    const avgEl = document.getElementById(`avg-${sensorId}`);
    if (!avgEl) return;

    // Format each average value, show "--" if null (not enough data yet)
    const fmt = (val) => val !== null ? val.toFixed(2) : "--";

    avgEl.innerHTML = `
        <span class="avg-item"><span class="avg-label">1min</span> ${fmt(averages["1min"])}</span>
        <span class="avg-item"><span class="avg-label">10min</span> ${fmt(averages["10min"])}</span>
        <span class="avg-item"><span class="avg-label">1h</span> ${fmt(averages["1h"])}</span>
        <span class="avg-item"><span class="avg-label">24h</span> ${fmt(averages["24h"])}</span>
        <span class="avg-item"><span class="avg-label">7d</span> ${fmt(averages["7d"])}</span>
    `;
}

// Refresh all sensor averages every 30 seconds
// Live values update via MQTT every second, averages don't need to be that frequent
setInterval(() => {
    Object.keys(sensorData).forEach(id => fetchAverages(id));
}, 30000);

// Adjusts the grid column count based on how many sensors exist,
// so the layout works whether there are 2 or 10 sensors.
function rebalanceGrid() {
    const grid = document.getElementById("sensor-grid");
    const count = Object.keys(sensorData).length;
    knownSensorCount = count;

    let cols, rows;
    if (count <= 2)      { cols = count; rows = 1; }
    else if (count <= 4) { cols = 2; rows = 2; }
    else if (count <= 6) { cols = 3; rows = 2; }
    else if (count <= 8) { cols = 4; rows = 2; }
    else                  { cols = 5; rows = 2; }

    grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    grid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
}

function updateCard(data) {
    const visual = VISUAL_MAP[data.category] || VISUAL_MAP.default;

    const valueEl = document.getElementById(`value-${data.id}`);
    if (!valueEl) return;

    valueEl.textContent = data.value.toFixed(2);

    const date = new Date(data.timestamp * 1000);
    const timeEl = document.getElementById(`time-${data.id}`);
    if (timeEl) timeEl.textContent = date.toLocaleTimeString("de-DE");

    const history = sensorData[data.id].history;

    if (visual === "gauge") {
        const percent = data.type === "voltage"
            ? Math.min((data.value / 10) * 100, 100)
            : Math.min(data.percent ?? 0, 100);
        updateGauge(data.id, percent);
    } else {
        if (charts[data.id]) {
            charts[data.id].data.labels = history.map(h =>
                h.time.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
            );
            charts[data.id].data.datasets[0].data = history.map(h => h.value);
            charts[data.id].update("none");
        }
    }

    // Live mid value from in-memory buffer (last 60 readings)
    const midEl = document.getElementById(`mid-${data.id}`);
    if (midEl && history.length > 0) {
        const avg = history.reduce((s, h) => s + h.value, 0) / history.length;
        midEl.textContent = `Live Mittel: ${avg.toFixed(2)} ${data.unit}`;
    }
}

function updateGauge(id, percent) {
    const arc = document.getElementById(`gauge-arc-${id}`);
    const label = document.getElementById(`gauge-label-${id}`);
    if (!arc) return;

    const circumference = 2 * Math.PI * 54;
    const offset = circumference * (1 - percent / 100);
    arc.style.strokeDashoffset = offset;
    if (label) label.textContent = `${Math.round(percent)}%`;
}

function createCard(data) {
    const grid = document.getElementById("sensor-grid");
    const visual = VISUAL_MAP[data.category] || VISUAL_MAP.default;
    const isVoltage = data.type === "voltage";
    const color   = isVoltage ? "#3b82f6" : "#10b981";
    const colorBg = isVoltage ? "rgba(59,130,246,0.08)" : "rgba(16,185,129,0.08)";

    const card = document.createElement("div");
    card.className = `sensor-card ${data.type}`;
    card.id = `card-${data.id}`;

    const bodyHtml = visual === "gauge"
        ? `
        <div class="gauge-wrap">
            <svg viewBox="0 0 120 120" class="gauge-svg">
                <circle cx="60" cy="60" r="54" class="gauge-track"></circle>
                <circle cx="60" cy="60" r="54" class="gauge-arc" id="gauge-arc-${data.id}"
                    style="stroke:${color}"></circle>
            </svg>
            <div class="gauge-center">
                <span class="gauge-percent" id="gauge-label-${data.id}">0%</span>
            </div>
        </div>
        `
        : `
        <div class="chart-container">
            <canvas id="chart-${data.id}"></canvas>
        </div>
        `;

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
                <div class="sensor-mid" id="mid-${data.id}">Live Mittel: --</div>
            </div>
        </div>
        ${bodyHtml}
        <div class="sensor-averages" id="avg-${data.id}">
            <span class="avg-item"><span class="avg-label">1min</span> --</span>
            <span class="avg-item"><span class="avg-label">10min</span> --</span>
            <span class="avg-item"><span class="avg-label">1h</span> --</span>
            <span class="avg-item"><span class="avg-label">24h</span> --</span>
            <span class="avg-item"><span class="avg-label">7d</span> --</span>
        </div>
        <div class="timestamp" id="time-${data.id}">--</div>
    `;

    grid.appendChild(card);

    if (visual !== "gauge") {
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
                        ticks: { font: { size: 9 }, color: "#94a3b8", maxTicksLimit: 5, maxRotation: 0 },
                        grid: { color: "#f1f5f9" }
                    },
                    y: {
                        display: true,
                        ticks: { font: { size: 9 }, color: "#94a3b8", maxTicksLimit: 4 },
                        grid: { color: "#f1f5f9" }
                    }
                },
                responsive: true,
                maintainAspectRatio: false,
                devicePixelRatio: 2,
            }
        });
    }
}