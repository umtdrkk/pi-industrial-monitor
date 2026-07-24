// ── MQTT CONNECTION SETTINGS ─────────────────────────────
// window.location.hostname automatically resolves to the correct host:
// → "localhost" when running on Mac
// → Pi's IP address when loaded from the Pi's dashboard
const MQTT_HOST = window.location.hostname;
const MQTT_PORT = 9001;         // WebSocket port configured in Mosquitto
const MQTT_TOPIC = "factory/#"; // Subscribe to all sensor topics
const MAX_HISTORY = 60;         // Number of data points to keep in memory per sensor

// Flask API base URL — same host as dashboard, port 5001
// Used to fetch historical averages and history from InfluxDB
const API_BASE = `http://${window.location.hostname}:5001`;

// ── VISUAL MAP ───────────────────────────────────────────
const VISUAL_MAP = {
    "distance":    "line",
    "temperature": "line",
    "pressure":    "gauge",
    "default":     "line",
};

// ── STATE ────────────────────────────────────────────────
const sensorData = {};
const charts = {};
const historyCharts = {};
const activeRange = {};
let knownSensorCount = 0;

// ── RENDER THROTTLE ──────────────────────────────────────
// At 100Hz MQTT rate, Chart.js would try to redraw 100x/second → crash.
// This limits chart redraws to max 10Hz (every 100ms) while still
// storing all 100Hz data in memory and InfluxDB.
const RENDER_INTERVAL = 100; // ms between chart redraws = 10Hz max
const lastRender = {};       // tracks last render time per sensor id

// ── MQTT CLIENT ──────────────────────────────────────────
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

// ── MESSAGE HANDLER ──────────────────────────────────────
function handleMessage(data) {
    if (!sensorData[data.id]) {
        sensorData[data.id] = { history: [] };
        activeRange[data.id] = null;
        lastRender[data.id] = 0; // initialize render timer for this sensor
        createCard(data);
        rebalanceGrid();
        fetchAverages(data.id);
    }

    sensorData[data.id].history.push({
        value: data.value,
        time: new Date(data.timestamp * 1000)
    });

    // At 100Hz with MAX_HISTORY=60 the buffer fills in 0.6s
    // Increase to 6000 to keep 60 seconds of history at 100Hz
    if (sensorData[data.id].history.length > MAX_HISTORY) {
        sensorData[data.id].history.shift();
    }

    updateCard(data);
}

// ── FLASK API — HISTORICAL AVERAGES ─────────────────────
async function fetchAverages(sensorId) {
    try {
        const response = await fetch(`${API_BASE}/api/sensors/${sensorId}/average`);
        const data = await response.json();
        updateAverages(sensorId, data.averages);
    } catch (err) {
        console.warn(`Could not fetch averages for sensor ${sensorId}:`, err);
    }
}

function updateAverages(sensorId, averages) {
    const avgEl = document.getElementById(`avg-${sensorId}`);
    if (!avgEl) return;

    const fmt = (val) => val !== null ? val.toFixed(2) : "--";

    avgEl.innerHTML = `
        <span class="avg-item" onclick="toggleHistory(${sensorId}, '1min')">
            <span class="avg-label">1min</span>
            <span id="avg-val-${sensorId}-1min">${fmt(averages["1min"])}</span>
        </span>
        <span class="avg-item" onclick="toggleHistory(${sensorId}, '10min')">
            <span class="avg-label">10min</span>
            <span id="avg-val-${sensorId}-10min">${fmt(averages["10min"])}</span>
        </span>
        <span class="avg-item" onclick="toggleHistory(${sensorId}, '1h')">
            <span class="avg-label">1h</span>
            <span id="avg-val-${sensorId}-1h">${fmt(averages["1h"])}</span>
        </span>
        <span class="avg-item" onclick="toggleHistory(${sensorId}, '24h')">
            <span class="avg-label">24h</span>
            <span id="avg-val-${sensorId}-24h">${fmt(averages["24h"])}</span>
        </span>
        <span class="avg-item" onclick="toggleHistory(${sensorId}, '7d')">
            <span class="avg-label">7d</span>
            <span id="avg-val-${sensorId}-7d">${fmt(averages["7d"])}</span>
        </span>
    `;
}

// ── HISTORY TOGGLE ───────────────────────────────────────
async function toggleHistory(sensorId, range) {
    const historyEl = document.getElementById(`history-${sensorId}`);
    if (!historyEl) return;

    if (activeRange[sensorId] === range) {
        activeRange[sensorId] = null;
        historyEl.style.display = "none";
        if (historyCharts[sensorId]) {
            historyCharts[sensorId].destroy();
            delete historyCharts[sensorId];
        }
        document.querySelectorAll(`#avg-${sensorId} .avg-item`).forEach(el => {
            el.classList.remove("avg-active");
        });
        return;
    }

    activeRange[sensorId] = range;
    document.querySelectorAll(`#avg-${sensorId} .avg-item`).forEach(el => {
        el.classList.remove("avg-active");
    });
    event.currentTarget.classList.add("avg-active");

    try {
        const response = await fetch(`${API_BASE}/api/sensors/${sensorId}/history/${range}`);
        const data = await response.json();

        if (data.data.length === 0) {
            historyEl.style.display = "flex";
            historyEl.innerHTML = `<span class="history-empty">Keine Daten für ${range} verfügbar</span>`;
            return;
        }

        historyEl.style.display = "block";

        if (historyCharts[sensorId]) {
            historyCharts[sensorId].destroy();
        }

        const card = document.getElementById(`card-${sensorId}`);
        const isVoltage = card.classList.contains("voltage");
        const color = isVoltage ? "#3b82f6" : "#10b981";
        const colorBg = isVoltage ? "rgba(59,130,246,0.08)" : "rgba(16,185,129,0.08)";

        const labels = data.data.map(p => {
            const d = new Date(p.time);
            return d.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"});
        });
        const values = data.data.map(p => p.value);

        const canvas = document.getElementById(`history-canvas-${sensorId}`);
        historyCharts[sensorId] = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [{
                    data: values,
                    borderColor: color,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3,
                    fill: true,
                    backgroundColor: colorBg,
                }]
            },
            options: {
                animation: false,
                plugins: {
                    legend: { display: false },
                    title: {
                        display: true,
                        text: `Verlauf — letzte ${range}`,
                        font: { size: 10 },
                        color: "#94a3b8",
                        padding: { bottom: 4 }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        ticks: { font: { size: 8 }, color: "#94a3b8", maxTicksLimit: 6, maxRotation: 0 },
                        grid: { color: "#f1f5f9" }
                    },
                    y: {
                        display: true,
                        ticks: { font: { size: 8 }, color: "#94a3b8", maxTicksLimit: 4 },
                        grid: { color: "#f1f5f9" }
                    }
                },
                responsive: true,
                maintainAspectRatio: false,
            }
        });

    } catch (err) {
        console.warn(`Could not fetch history for sensor ${sensorId}:`, err);
        historyEl.style.display = "flex";
        historyEl.innerHTML = `<span class="history-empty">Fehler beim Laden der Daten</span>`;
    }
}

setInterval(() => {
    Object.keys(sensorData).forEach(id => fetchAverages(id));
}, 30000);

// ── GRID LAYOUT ──────────────────────────────────────────
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

// ── CARD UPDATE ──────────────────────────────────────────
function updateCard(data) {
    const visual = VISUAL_MAP[data.category] || VISUAL_MAP.default;

    const valueEl = document.getElementById(`value-${data.id}`);
    if (!valueEl) return;

    // Always update the live value display — lightweight DOM update, fine at 100Hz
    valueEl.textContent = data.value.toFixed(2);

    // Secondary voltage for distance sensors
    const voltageEl = document.getElementById(`voltage-${data.id}`);
    if (voltageEl && data.voltage !== undefined) {
        voltageEl.textContent = `(${data.voltage.toFixed(2)} V)`;
    }

    // Secondary current for pressure sensors
    const currentEl = document.getElementById(`current-${data.id}`);
    if (currentEl && data.current_ma !== undefined) {
        currentEl.textContent = `(${data.current_ma.toFixed(2)} mA)`;
    }

    // Timestamp — always update
    const date = new Date(data.timestamp * 1000);
    const timeEl = document.getElementById(`time-${data.id}`);
    if (timeEl) timeEl.textContent = date.toLocaleTimeString("de-DE");

    const history = sensorData[data.id].history;

    // ── RENDER THROTTLE ──────────────────────────────────
    // Chart.js redraws are expensive — limit to 10Hz regardless of MQTT rate.
    // The live value above still updates at full 100Hz (cheap DOM text change).
    // All data is still stored in memory and InfluxDB at full rate.
    const now = Date.now();
    const shouldRender = (now - (lastRender[data.id] || 0)) >= RENDER_INTERVAL;

    if (shouldRender) {
        lastRender[data.id] = now;

        if (visual === "gauge") {
            // Pressure gauge: 0 bar = 0%, 1 bar = 100%
            const percent = Math.min(Math.max(data.percent ?? 0, 0), 100);
            updateGauge(data.id, percent);
        } else {
            // Line chart — throttled to 10Hz to prevent browser freeze
            if (charts[data.id]) {
                charts[data.id].data.labels = history.map(h =>
                    h.time.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
                );
                charts[data.id].data.datasets[0].data = history.map(h => h.value);
                charts[data.id].update("none");
            }
        }

        // Live rolling average — also throttled (no need to recalculate 100x/sec)
        const midEl = document.getElementById(`mid-${data.id}`);
        if (midEl && history.length > 0) {
            const avg = history.reduce((s, h) => s + h.value, 0) / history.length;
            midEl.textContent = `Live Mittel: ${avg.toFixed(2)} ${data.unit}`;
        }
    }
}

// ── GAUGE UPDATE ─────────────────────────────────────────
function updateGauge(id, percent) {
    const arc = document.getElementById(`gauge-arc-${id}`);
    const label = document.getElementById(`gauge-label-${id}`);
    if (!arc) return;

    const circumference = 2 * Math.PI * 54;
    const offset = circumference * (1 - percent / 100);
    arc.style.strokeDashoffset = offset;
    if (label) label.textContent = `${Math.round(percent)}%`;
}

// ── CARD CREATION ────────────────────────────────────────
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
                <div class="sensor-voltage" id="voltage-${data.id}"></div>
                <div class="sensor-voltage" id="current-${data.id}"></div>
                <div class="sensor-mid" id="mid-${data.id}">Live Mittel: --</div>
            </div>
        </div>
        ${bodyHtml}
        <div class="sensor-averages" id="avg-${data.id}">
            <span class="avg-item" onclick="toggleHistory(${data.id}, '1min')">
                <span class="avg-label">1min</span><span>--</span>
            </span>
            <span class="avg-item" onclick="toggleHistory(${data.id}, '10min')">
                <span class="avg-label">10min</span><span>--</span>
            </span>
            <span class="avg-item" onclick="toggleHistory(${data.id}, '1h')">
                <span class="avg-label">1h</span><span>--</span>
            </span>
            <span class="avg-item" onclick="toggleHistory(${data.id}, '24h')">
                <span class="avg-label">24h</span><span>--</span>
            </span>
            <span class="avg-item" onclick="toggleHistory(${data.id}, '7d')">
                <span class="avg-label">7d</span><span>--</span>
            </span>
        </div>
        <div class="history-container" id="history-${data.id}" style="display:none;">
            <canvas id="history-canvas-${data.id}"></canvas>
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