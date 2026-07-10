// ── MQTT CONNECTION SETTINGS ─────────────────────────────
// window.location.hostname automatically resolves to the correct host:
// → "localhost" when running on Mac
// → Pi's IP address when loaded from the Pi's dashboard
const MQTT_HOST = window.location.hostname;
const MQTT_PORT = 9001;         // WebSocket port configured in Mosquitto
const MQTT_TOPIC = "factory/#"; // Subscribe to all sensor topics
const MAX_HISTORY = 60;         // Number of data points to keep in memory per sensor

// Flask API base URL — same host as dashboard, port 5001
// Used to fetch historical averages from InfluxDB
const API_BASE = `http://${window.location.hostname}:5001`;

// ── VISUAL MAP ───────────────────────────────────────────
// Maps sensor category to chart type.
// Add a new category here and every sensor with that category
// automatically gets the right visualization — no other code changes needed.
const VISUAL_MAP = {
    "distance":    "gauge",   // distance sensors → circular gauge (shows % of range)
    "temperature": "line",    // temperature sensors → line chart (trend matters)
    "pressure":    "line",    // pressure sensors → line chart (trend matters)
    "default":     "line",    // anything else → line chart
};

// ── STATE ────────────────────────────────────────────────
const sensorData = {};  // stores history arrays per sensor id
const charts = {};      // stores Chart.js instances per sensor id
let knownSensorCount = 0;

// ── MQTT CLIENT ──────────────────────────────────────────
const client = mqtt.connect(`ws://${MQTT_HOST}:${MQTT_PORT}`);

// Update connection status badge when MQTT connects
client.on("connect", () => {
    document.getElementById("connection-status").className = "status connected";
    document.getElementById("connection-status").textContent = "Verbunden";
    client.subscribe(MQTT_TOPIC);
});

// Update connection status badge when MQTT disconnects
client.on("disconnect", () => {
    document.getElementById("connection-status").className = "status disconnected";
    document.getElementById("connection-status").textContent = "Getrennt";
});

// Handle incoming MQTT messages — parse JSON and process
client.on("message", (topic, message) => {
    const data = JSON.parse(message.toString());
    handleMessage(data);
});

// ── MESSAGE HANDLER ──────────────────────────────────────
function handleMessage(data) {
    // First time we see this sensor — create its card and fetch averages
    if (!sensorData[data.id]) {
        sensorData[data.id] = { history: [] };
        createCard(data);
        rebalanceGrid();
        // Fetch historical averages from Flask API immediately on first data
        fetchAverages(data.id);
    }

    // Add this reading to the in-memory history buffer
    sensorData[data.id].history.push({
        value: data.value,
        time: new Date(data.timestamp * 1000)
    });

    // Keep only the last MAX_HISTORY readings — drop oldest if over limit
    if (sensorData[data.id].history.length > MAX_HISTORY) {
        sensorData[data.id].history.shift();
    }

    updateCard(data);
}

// ── FLASK API — HISTORICAL AVERAGES ─────────────────────
// Fetches pre-computed averages from Flask → InfluxDB for a given sensor
async function fetchAverages(sensorId) {
    try {
        const response = await fetch(`${API_BASE}/api/sensors/${sensorId}/average`);
        const data = await response.json();
        updateAverages(sensorId, data.averages);
    } catch (err) {
        // Flask might not be running — fail silently, live MQTT data still works
        console.warn(`Could not fetch averages for sensor ${sensorId}:`, err);
    }
}

// Updates the averages row at the bottom of a sensor card
function updateAverages(sensorId, averages) {
    const avgEl = document.getElementById(`avg-${sensorId}`);
    if (!avgEl) return;

    // Show "--" for time ranges with no data yet (e.g. "7d" on first day)
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
// Live values update every second via MQTT — averages don't need to be that frequent
setInterval(() => {
    Object.keys(sensorData).forEach(id => fetchAverages(id));
}, 30000);

// ── GRID LAYOUT ──────────────────────────────────────────
// Adjusts the CSS grid column/row count based on how many sensors exist.
// Called every time a new sensor card is created.
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
// Called every second when new MQTT data arrives — updates live values on the card
function updateCard(data) {
    const visual = VISUAL_MAP[data.category] || VISUAL_MAP.default;

    const valueEl = document.getElementById(`value-${data.id}`);
    if (!valueEl) return;

    // Update the main live value (distance in mm, pressure in bar etc.)
    valueEl.textContent = data.value.toFixed(2);

    // For distance sensors — show the raw sensor voltage as secondary info
    // This helps cross-check the distance conversion math
    const voltageEl = document.getElementById(`voltage-${data.id}`);
    if (voltageEl && data.voltage !== undefined) {
        voltageEl.textContent = `(${data.voltage.toFixed(2)} V)`;
    }

    // For pressure sensors — show the raw current as secondary info
    const currentEl = document.getElementById(`current-${data.id}`);
    if (currentEl && data.current_ma !== undefined) {
        currentEl.textContent = `(${data.current_ma.toFixed(2)} mA)`;
    }

    // Update the timestamp showing when the last reading arrived
    const date = new Date(data.timestamp * 1000);
    const timeEl = document.getElementById(`time-${data.id}`);
    if (timeEl) timeEl.textContent = date.toLocaleTimeString("de-DE");

    const history = sensorData[data.id].history;

    if (visual === "gauge") {
        // Distance sensor gauge: closer object = higher fill percentage
        // Sensor range is 15-500mm (inverse: 10V=15mm, 0V=500mm)
        // So percent = (500 - distance) / 485 * 100
        // 15mm (closest) → 100%, 500mm (furthest) → 0%
        const percent = Math.min(Math.max((500 - data.value) / 485 * 100, 0), 100);
        updateGauge(data.id, percent);
    } else {
        // Line chart sensors — push new data point and update chart
        if (charts[data.id]) {
            charts[data.id].data.labels = history.map(h =>
                h.time.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
            );
            charts[data.id].data.datasets[0].data = history.map(h => h.value);
            charts[data.id].update("none"); // "none" skips animation for performance
        }
    }

    // Live rolling average from the last 60 in-memory readings
    const midEl = document.getElementById(`mid-${data.id}`);
    if (midEl && history.length > 0) {
        const avg = history.reduce((s, h) => s + h.value, 0) / history.length;
        midEl.textContent = `Live Mittel: ${avg.toFixed(2)} ${data.unit}`;
    }
}

// ── GAUGE UPDATE ─────────────────────────────────────────
// Updates the SVG gauge arc and center label for a given sensor
function updateGauge(id, percent) {
    const arc = document.getElementById(`gauge-arc-${id}`);
    const label = document.getElementById(`gauge-label-${id}`);
    if (!arc) return;

    // stroke-dasharray = full circumference (2π × radius = 2π × 54 ≈ 339.3)
    // stroke-dashoffset controls how much of the arc is visible:
    // offset = 0 → full circle (100%), offset = 339.3 → empty (0%)
    const circumference = 2 * Math.PI * 54;
    const offset = circumference * (1 - percent / 100);
    arc.style.strokeDashoffset = offset;
    if (label) label.textContent = `${Math.round(percent)}%`;
}

// ── CARD CREATION ────────────────────────────────────────
// Creates a new sensor card DOM element when a new sensor is first seen.
// Cards are never recreated — only updated via updateCard() after this.
function createCard(data) {
    const grid = document.getElementById("sensor-grid");
    const visual = VISUAL_MAP[data.category] || VISUAL_MAP.default;
    const isVoltage = data.type === "voltage";
    const color   = isVoltage ? "#3b82f6" : "#10b981"; // blue for voltage, green for current
    const colorBg = isVoltage ? "rgba(59,130,246,0.08)" : "rgba(16,185,129,0.08)";

    const card = document.createElement("div");
    card.className = `sensor-card ${data.type}`;
    card.id = `card-${data.id}`;

    // Gauge HTML for distance sensors — SVG circle with animated arc
    // Line chart HTML for all other sensor types — Chart.js canvas
    const bodyHtml = visual === "gauge"
        ? `
        <div class="gauge-wrap">
            <svg viewBox="0 0 120 120" class="gauge-svg">
                <!-- Background track — always full grey circle -->
                <circle cx="60" cy="60" r="54" class="gauge-track"></circle>
                <!-- Foreground arc — animates based on distance percentage -->
                <circle cx="60" cy="60" r="54" class="gauge-arc" id="gauge-arc-${data.id}"
                    style="stroke:${color}"></circle>
            </svg>
            <!-- Percentage label centered inside the gauge -->
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
                <!-- Sensor name e.g. "DISTANZSENSOR" -->
                <span class="sensor-name">${data.name}</span>
                <!-- Signal type badge e.g. "0–10V" or "4–20mA" -->
                <span class="sensor-type-badge">${isVoltage ? "0–10V" : "4–20mA"}</span>
            </div>
            <div class="sensor-right">
                <!-- Main live value + unit e.g. "485 mm" or "0.42 bar" -->
                <div class="sensor-value-row">
                    <span class="sensor-value" id="value-${data.id}">--</span>
                    <span class="sensor-unit">${data.unit}</span>
                </div>
                <!-- Secondary voltage — only populated for distance sensors -->
                <div class="sensor-voltage" id="voltage-${data.id}"></div>
                <!-- Secondary current — only populated for pressure sensors -->
                <div class="sensor-voltage" id="current-${data.id}"></div>
                <!-- Live rolling average from last 60 in-memory readings -->
                <div class="sensor-mid" id="mid-${data.id}">Live Mittel: --</div>
            </div>
        </div>
        ${bodyHtml}
        <!-- Historical averages row — fetched from Flask API every 30 seconds -->
        <div class="sensor-averages" id="avg-${data.id}">
            <span class="avg-item"><span class="avg-label">1min</span> --</span>
            <span class="avg-item"><span class="avg-label">10min</span> --</span>
            <span class="avg-item"><span class="avg-label">1h</span> --</span>
            <span class="avg-item"><span class="avg-label">24h</span> --</span>
            <span class="avg-item"><span class="avg-label">7d</span> --</span>
        </div>
        <!-- Timestamp of last received reading -->
        <div class="timestamp" id="time-${data.id}">--</div>
    `;

    grid.appendChild(card);

    // Only create Chart.js instance for line chart sensors
    // Gauge sensors use SVG directly — no Chart.js needed
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
                    pointRadius: 0,      // no dots — cleaner look for real-time data
                    tension: 0.3,        // slight curve for smoother appearance
                    fill: true,          // fill area under the line
                    backgroundColor: colorBg,
                }]
            },
            options: {
                animation: false,  // disable animation for real-time performance
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
                devicePixelRatio: 2,  // sharper rendering on high-DPI displays
            }
        });
    }
}