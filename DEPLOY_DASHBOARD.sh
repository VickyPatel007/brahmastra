#!/bin/bash
# Complete Dashboard Deployment Script for EC2
# Copy and paste this ENTIRE script into your EC2 terminal

cd /home/ubuntu/brahmastra/dashboard

cat > index.html << 'EOFHTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brahmastra - Infrastructure Monitoring</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 0;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        h1 {
            font-size: 3rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
            font-weight: 800;
        }
        .subtitle { color: rgba(255, 255, 255, 0.7); font-size: 1.1rem; }
        .status-badge {
            display: inline-block;
            padding: 8px 20px;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid rgba(16, 185, 129, 0.5);
            border-radius: 20px;
            color: #10b981;
            font-weight: 600;
            margin-top: 15px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 20px;
            padding: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: transform 0.3s ease;
        }
        .card:hover { transform: translateY(-5px); }
        .card-title {
            font-size: 0.9rem;
            color: rgba(255, 255, 255, 0.6);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
            font-weight: 600;
        }
        .metric-value {
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .chart-container { position: relative; height: 300px; margin-top: 20px; }
        .large-chart { grid-column: 1 / -1; }
        .threat-gauge { position: relative; width: 200px; height: 200px; margin: 20px auto; }
        .gauge-circle {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            background: conic-gradient(from 0deg, #10b981 0deg 120deg, #f59e0b 120deg 240deg, #ef4444 240deg 360deg);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .gauge-inner {
            width: 85%;
            height: 85%;
            border-radius: 50%;
            background: rgba(15, 12, 41, 0.95);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .gauge-value { font-size: 3rem; font-weight: 800; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-top: 20px; }
        .stat-item { background: rgba(255, 255, 255, 0.03); padding: 15px; border-radius: 12px; }
        .stat-value { font-size: 1.8rem; font-weight: 700; color: #667eea; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ BRAHMASTRA</h1>
            <p class="subtitle">Self-Healing Infrastructure Monitoring System</p>
            <div class="status-badge">● LIVE</div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-title">CPU Usage</div>
                <div class="metric-value" id="cpuValue">--</div>
                <div class="chart-container"><canvas id="cpuChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-title">Memory Usage</div>
                <div class="metric-value" id="memoryValue">--</div>
                <div class="chart-container"><canvas id="memoryChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-title">Disk Usage</div>
                <div class="metric-value" id="diskValue">--</div>
                <div class="chart-container"><canvas id="diskChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-title">Threat Score</div>
                <div class="threat-gauge">
                    <div class="gauge-circle">
                        <div class="gauge-inner">
                            <div class="gauge-value" id="threatValue">--</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card large-chart">
            <div class="card-title">Historical Metrics (Last 50 Records)</div>
            <div class="chart-container" style="height: 350px;">
                <canvas id="historicalChart"></canvas>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Database Statistics</div>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value" id="metricsCount">--</div>
                    <div style="font-size: 0.85rem; color: rgba(255,255,255,0.5);">Total Metrics</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="threatsCount">--</div>
                    <div style="font-size: 0.85rem; color: rgba(255,255,255,0.5);">Threat Scores</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_URL = 'http://localhost:8000';
        const chartConfig = {
            type: 'line',
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: 'rgba(255,255,255,0.6)' } },
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: 'rgba(255,255,255,0.6)', maxTicksLimit: 10 } }
                }
            }
        };

        const cpuChart = new Chart(document.getElementById('cpuChart'), {
            ...chartConfig,
            data: { labels: [], datasets: [{ data: [], borderColor: '#667eea', backgroundColor: 'rgba(102,126,234,0.1)', fill: true, tension: 0.4 }] }
        });
        const memoryChart = new Chart(document.getElementById('memoryChart'), {
            ...chartConfig,
            data: { labels: [], datasets: [{ data: [], borderColor: '#764ba2', backgroundColor: 'rgba(118,75,162,0.1)', fill: true, tension: 0.4 }] }
        });
        const diskChart = new Chart(document.getElementById('diskChart'), {
            ...chartConfig,
            data: { labels: [], datasets: [{ data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.4 }] }
        });
        const historicalChart = new Chart(document.getElementById('historicalChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'CPU', data: [], borderColor: '#667eea', tension: 0.4 },
                    { label: 'Memory', data: [], borderColor: '#764ba2', tension: 0.4 },
                    { label: 'Disk', data: [], borderColor: '#f59e0b', tension: 0.4 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, labels: { color: 'rgba(255,255,255,0.8)' } } },
                scales: {
                    y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: 'rgba(255,255,255,0.6)' } },
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: 'rgba(255,255,255,0.6)', maxTicksLimit: 15 } }
                }
            }
        });

        async function fetchCurrentMetrics() {
            try {
                const response = await fetch(`${API_URL}/api/metrics/current`);
                const data = await response.json();
                document.getElementById('cpuValue').textContent = data.cpu_percent.toFixed(1) + '%';
                document.getElementById('memoryValue').textContent = data.memory_percent.toFixed(1) + '%';
                document.getElementById('diskValue').textContent = data.disk_percent.toFixed(1) + '%';
                const time = new Date().toLocaleTimeString();
                updateChart(cpuChart, time, data.cpu_percent);
                updateChart(memoryChart, time, data.memory_percent);
                updateChart(diskChart, time, data.disk_percent);
            } catch (e) { console.error(e); }
        }

        async function fetchThreatScore() {
            try {
                const response = await fetch(`${API_URL}/api/threat/score`);
                const data = await response.json();
                document.getElementById('threatValue').textContent = data.threat_score;
            } catch (e) { console.error(e); }
        }

        async function fetchHistoricalData() {
            try {
                const response = await fetch(`${API_URL}/api/metrics/history?limit=50`);
                const data = await response.json();
                if (data.length > 0) {
                    historicalChart.data.labels = data.map(m => new Date(m.timestamp).toLocaleTimeString());
                    historicalChart.data.datasets[0].data = data.map(m => m.cpu_percent);
                    historicalChart.data.datasets[1].data = data.map(m => m.memory_percent);
                    historicalChart.data.datasets[2].data = data.map(m => m.disk_percent);
                    historicalChart.update();
                }
            } catch (e) { console.error(e); }
        }

        async function fetchStats() {
            try {
                const response = await fetch(`${API_URL}/api/stats`);
                const data = await response.json();
                if (data.database === 'enabled') {
                    document.getElementById('metricsCount').textContent = data.metrics_count || 0;
                    document.getElementById('threatsCount').textContent = data.threats_count || 0;
                }
            } catch (e) { console.error(e); }
        }

        function updateChart(chart, label, value) {
            chart.data.labels.push(label);
            chart.data.datasets[0].data.push(value);
            if (chart.data.labels.length > 20) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }
            chart.update('none');
        }

        fetchCurrentMetrics();
        fetchThreatScore();
        fetchHistoricalData();
        fetchStats();
        setInterval(fetchCurrentMetrics, 5000);
        setInterval(fetchThreatScore, 5000);
        setInterval(fetchHistoricalData, 30000);
        setInterval(fetchStats, 10000);
    </script>
</body>
</html>
EOFHTML

echo "✅ Dashboard file created!"
ls -lh index.html

echo ""
echo "🚀 Starting dashboard server..."
nohup python3 -m http.server 8080 > /dev/null 2>&1 &

echo "✅ Dashboard is now live at: http://13.234.113.97:8080"
echo ""
echo "🎉 Refresh your browser to see the dashboard!"
