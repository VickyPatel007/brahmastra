#!/bin/bash
# ============================================================
# BRAHMASTRA - Nginx + Dashboard Setup Script
# Run this ENTIRE script in your EC2 terminal (paste & enter)
# ============================================================

set -e
echo "🚀 Starting Brahmastra Dashboard + Nginx Setup..."

# ─── Step 1: Install Nginx ──────────────────────────────────
echo ""
echo "📦 Step 1: Installing Nginx..."
sudo apt-get update -qq
sudo apt-get install -y nginx

# ─── Step 2: Create dashboard directory ────────────────────
echo ""
echo "📁 Step 2: Setting up dashboard directory..."
sudo mkdir -p /var/www/brahmastra
sudo chown ubuntu:ubuntu /var/www/brahmastra

# ─── Step 3: Write the main dashboard HTML ─────────────────
echo ""
echo "🎨 Step 3: Creating dashboard..."
cat > /var/www/brahmastra/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Brahmastra - War Room</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #7c3aed;
            --secondary: #06b6d4;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg: #030712;
            --surface: rgba(255,255,255,0.04);
            --border: rgba(255,255,255,0.08);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: #f1f5f9;
            min-height: 100vh;
            overflow-x: hidden;
        }
        /* Animated background */
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background: 
                radial-gradient(ellipse 80% 50% at 20% 10%, rgba(124,58,237,0.15) 0%, transparent 60%),
                radial-gradient(ellipse 60% 40% at 80% 80%, rgba(6,182,212,0.1) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }
        .container { max-width: 1600px; margin: 0 auto; padding: 20px; position: relative; z-index: 1; }

        /* ── Header ── */
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 30px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            margin-bottom: 24px;
            backdrop-filter: blur(20px);
        }
        .logo { display: flex; align-items: center; gap: 14px; }
        .logo-icon {
            width: 48px; height: 48px; border-radius: 12px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            display: flex; align-items: center; justify-content: center;
            font-size: 24px;
            box-shadow: 0 0 20px rgba(124,58,237,0.4);
        }
        .logo-text h1 { font-size: 1.6rem; font-weight: 900; background: linear-gradient(135deg, #a78bfa, #67e8f9); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .logo-text p { font-size: 0.78rem; color: rgba(255,255,255,0.4); letter-spacing: 2px; text-transform: uppercase; }
        
        .header-right { display: flex; align-items: center; gap: 16px; }
        .live-badge {
            display: flex; align-items: center; gap: 8px;
            padding: 8px 16px;
            background: rgba(16,185,129,0.1);
            border: 1px solid rgba(16,185,129,0.3);
            border-radius: 50px;
            font-size: 0.82rem; font-weight: 600; color: var(--success);
        }
        .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.6;transform:scale(0.8)} }

        .time-display { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: rgba(255,255,255,0.4); }
        .threat-level-badge {
            padding: 8px 16px;
            border-radius: 50px;
            font-size: 0.82rem; font-weight: 700;
            border: 1px solid;
        }

        /* ── Metric Cards Row ── */
        .metrics-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }
        @media (max-width: 1024px) { .metrics-row { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 600px)  { .metrics-row { grid-template-columns: 1fr; } }

        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(20px);
            transition: transform 0.2s, border-color 0.2s;
        }
        .card:hover { transform: translateY(-3px); border-color: rgba(255,255,255,0.15); }

        .metric-card { display: flex; flex-direction: column; gap: 8px; }
        .metric-label {
            font-size: 0.72rem; font-weight: 600; letter-spacing: 2px;
            text-transform: uppercase; color: rgba(255,255,255,0.4);
        }
        .metric-value {
            font-size: 2.8rem; font-weight: 800; line-height: 1;
            font-variant-numeric: tabular-nums;
        }
        .metric-sub { font-size: 0.8rem; color: rgba(255,255,255,0.35); }
        .mini-bar {
            height: 4px; border-radius: 2px;
            background: rgba(255,255,255,0.08);
            margin-top: 8px; overflow: hidden;
        }
        .mini-bar-fill { height: 100%; border-radius: 2px; transition: width 0.6s ease; }

        /* ── Charts Grid ── */
        .charts-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 16px;
            margin-bottom: 24px;
        }
        @media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }

        .chart-container { position: relative; height: 280px; }

        /* ── Bottom Grid ── */
        .bottom-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        @media (max-width: 900px) { .bottom-grid { grid-template-columns: 1fr; } }

        .card-title {
            font-size: 0.78rem; font-weight: 700; letter-spacing: 1.5px;
            text-transform: uppercase; color: rgba(255,255,255,0.5);
            margin-bottom: 20px; display: flex; align-items: center; gap: 8px;
        }
        .card-title-dot { width: 6px; height: 6px; border-radius: 50%; }

        /* ── Threat Gauge ── */
        .gauge-wrap { display: flex; flex-direction: column; align-items: center; gap: 16px; }
        .gauge-svg-wrap { position: relative; width: 180px; height: 100px; }
        .gauge-svg-wrap svg { width: 100%; height: 100%; }
        .gauge-center-text {
            position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
            text-align: center;
        }
        .gauge-score { font-size: 2.4rem; font-weight: 800; display: block; }
        .gauge-label { font-size: 0.7rem; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 1px; }

        /* ── Log Terminal ── */
        .log-terminal {
            background: #0a0a0f;
            border: 1px solid rgba(124,58,237,0.3);
            border-radius: 12px;
            padding: 16px;
            height: 220px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            line-height: 1.7;
        }
        .log-terminal::-webkit-scrollbar { width: 4px; }
        .log-terminal::-webkit-scrollbar-track { background: transparent; }
        .log-terminal::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.5); border-radius: 2px; }
        .log-entry { display: flex; gap: 10px; margin-bottom: 2px; }
        .log-time { color: rgba(255,255,255,0.25); flex-shrink: 0; }
        .log-ok    { color: #10b981; }
        .log-warn  { color: #f59e0b; }
        .log-err   { color: #ef4444; }
        .log-info  { color: #67e8f9; }

        /* ── Stats items ── */
        .stats-list { display: flex; flex-direction: column; gap: 12px; }
        .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(255,255,255,0.03); border-radius: 8px; }
        .stat-name { font-size: 0.82rem; color: rgba(255,255,255,0.5); }
        .stat-val { font-size: 0.9rem; font-weight: 700; font-variant-numeric: tabular-nums; }

        /* ── Action Buttons ── */
        .action-bar { display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
        .btn {
            padding: 10px 20px; border: none; border-radius: 10px;
            font-size: 0.82rem; font-weight: 700; cursor: pointer;
            display: flex; align-items: center; gap: 8px;
            transition: all 0.2s; letter-spacing: 0.5px;
        }
        .btn-primary { background: linear-gradient(135deg, var(--primary), #5b21b6); color: white; box-shadow: 0 4px 15px rgba(124,58,237,0.3); }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(124,58,237,0.4); }
        .btn-danger { background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; box-shadow: 0 4px 15px rgba(239,68,68,0.3); }
        .btn-danger:hover { transform: translateY(-2px); }
        .btn-safe { background: linear-gradient(135deg, #0284c7, #0e7490); color: white; }
        .btn-safe:hover { transform: translateY(-2px); }

        /* ── Color utils ── */
        .c-green { color: var(--success); } .c-yellow { color: var(--warning); } .c-red { color: var(--danger); } .c-blue { color: var(--secondary); } .c-purple { color: var(--primary); }
    </style>
</head>
<body>
<div class="container">

    <!-- Header -->
    <header>
        <div class="logo">
            <div class="logo-icon">⚡</div>
            <div class="logo-text">
                <h1>BRAHMASTRA</h1>
                <p>War Room Command Center</p>
            </div>
        </div>
        <div class="header-right">
            <div class="live-badge"><div class="live-dot"></div>LIVE</div>
            <div class="threat-level-badge" id="threatBadge" style="color:#10b981;border-color:rgba(16,185,129,0.4);background:rgba(16,185,129,0.1)">
                🛡️ <span id="threatLevelText">SECURE</span>
            </div>
            <div class="time-display" id="clockDisplay">--:--:--</div>
        </div>
    </header>

    <!-- Metric Cards -->
    <div class="metrics-row">
        <div class="card metric-card">
            <div class="metric-label">🖥️ CPU Usage</div>
            <div class="metric-value c-purple" id="cpuVal">--</div>
            <div class="metric-sub">Processing load</div>
            <div class="mini-bar"><div class="mini-bar-fill" id="cpuBar" style="background:#7c3aed;width:0%"></div></div>
        </div>
        <div class="card metric-card">
            <div class="metric-label">🧠 Memory</div>
            <div class="metric-value c-blue" id="memVal">--</div>
            <div class="metric-sub">RAM utilization</div>
            <div class="mini-bar"><div class="mini-bar-fill" id="memBar" style="background:#06b6d4;width:0%"></div></div>
        </div>
        <div class="card metric-card">
            <div class="metric-label">💾 Disk</div>
            <div class="metric-value c-green" id="diskVal">--</div>
            <div class="metric-sub">Storage used</div>
            <div class="mini-bar"><div class="mini-bar-fill" id="diskBar" style="background:#10b981;width:0%"></div></div>
        </div>
        <div class="card metric-card">
            <div class="metric-label">⚠️ Threat Score</div>
            <div class="metric-value" id="threatNumVal" style="color:#10b981">--</div>
            <div class="metric-sub" id="threatDesc">Calculating...</div>
            <div class="mini-bar"><div class="mini-bar-fill" id="threatBar" style="background:#10b981;width:0%"></div></div>
        </div>
    </div>

    <!-- Charts Row -->
    <div class="charts-grid" style="margin-bottom:24px;">
        <div class="card">
            <div class="card-title"><div class="card-title-dot" style="background:#7c3aed"></div>System Metrics History</div>
            <div class="chart-container">
                <canvas id="histChart"></canvas>
            </div>
        </div>
        <div class="card">
            <div class="card-title"><div class="card-title-dot" style="background:#ef4444"></div>Threat Gauge</div>
            <div class="gauge-wrap" style="margin-top:10px;">
                <div class="gauge-svg-wrap">
                    <svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
                        <!-- Track -->
                        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="16" stroke-linecap="round"/>
                        <!-- Colored sections -->
                        <path d="M 20 100 A 80 80 0 0 1 100 20" fill="none" stroke="#10b981" stroke-width="16" stroke-linecap="round" opacity="0.7"/>
                        <path d="M 100 20 A 80 80 0 0 1 180 100" fill="none" stroke="#ef4444" stroke-width="16" stroke-linecap="round" opacity="0.4"/>
                        <!-- Needle -->
                        <line id="gaugeNeedle" x1="100" y1="100" x2="100" y2="28" stroke="white" stroke-width="3" stroke-linecap="round"/>
                        <circle cx="100" cy="100" r="6" fill="white"/>
                    </svg>
                    <div class="gauge-center-text">
                        <span class="gauge-score" id="gaugeScore">0</span>
                        <span class="gauge-label">/100</span>
                    </div>
                </div>
                <div class="stats-list" style="width:100%">
                    <div class="stat-row"><span class="stat-name">Processes</span><span class="stat-val c-blue" id="procCount">--</span></div>
                    <div class="stat-row"><span class="stat-name">Uptime</span><span class="stat-val c-green" id="sysUptime">--</span></div>
                    <div class="stat-row"><span class="stat-name">Backend</span><span class="stat-val c-green">🟢 Healthy</span></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Bottom Grid -->
    <div class="bottom-grid">
        <!-- Live Log Terminal -->
        <div class="card">
            <div class="card-title"><div class="card-title-dot" style="background:#06b6d4"></div>Live Activity Log</div>
            <div class="log-terminal" id="logTerminal">
                <div class="log-entry"><span class="log-time">[INIT]</span><span class="log-info">Brahmastra War Room initializing...</span></div>
                <div class="log-entry"><span class="log-time">[INIT]</span><span class="log-ok">Connecting to backend API...</span></div>
            </div>
        </div>

        <!-- Controls -->
        <div class="card">
            <div class="card-title"><div class="card-title-dot" style="background:#f59e0b"></div>Command Center</div>
            <div class="stats-list">
                <div class="stat-row"><span class="stat-name">API Status</span><span class="stat-val c-green" id="apiStatus">-</span></div>
                <div class="stat-row"><span class="stat-name">Last Updated</span><span class="stat-val c-blue" id="lastUpdate">-</span></div>
                <div class="stat-row"><span class="stat-name">Data Points</span><span class="stat-val" id="dataPoints">-</span></div>
                <div class="stat-row"><span class="stat-name">Auto-Refresh</span><span class="stat-val c-green">Every 5s</span></div>
            </div>
            <div class="action-bar">
                <button class="btn btn-primary" onclick="refreshAll()">🔄 Refresh Now</button>
                <button class="btn btn-safe" onclick="testApi()">🧪 Test API</button>
                <button class="btn btn-danger" onclick="triggerKillSwitch()">☠️ Kill Switch</button>
            </div>
        </div>
    </div>
</div>

<script>
    const API = '';  // same origin via Nginx proxy

    // ── Clock ──
    setInterval(() => {
        document.getElementById('clockDisplay').textContent = new Date().toLocaleTimeString('en-IN');
    }, 1000);

    // ── Log helper ──
    function addLog(msg, type='info') {
        const el = document.getElementById('logTerminal');
        const t = new Date().toLocaleTimeString('en-IN');
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.innerHTML = `<span class="log-time">[${t}]</span><span class="log-${type}">${msg}</span>`;
        el.appendChild(div);
        if (el.children.length > 100) el.removeChild(el.firstChild);
        el.scrollTop = el.scrollHeight;
    }

    // ── Gauge needle ──
    function setGaugeNeedle(score) {
        const angle = (score / 100) * 180 - 90; // -90 to +90 degrees
        const rad = (angle * Math.PI) / 180;
        const cx = 100, cy = 100, len = 72;
        const x2 = cx + len * Math.sin(rad);
        const y2 = cy - len * Math.cos(rad);
        document.getElementById('gaugeNeedle').setAttribute('x2', x2.toFixed(1));
        document.getElementById('gaugeNeedle').setAttribute('y2', y2.toFixed(1));
    }

    // ── Threat level badge ──
    function updateThreatBadge(score) {
        const badge = document.getElementById('threatBadge');
        const text = document.getElementById('threatLevelText');
        const numEl = document.getElementById('threatNumVal');
        const desc = document.getElementById('threatDesc');
        const bar = document.getElementById('threatBar');
        bar.style.width = score + '%';
        numEl.textContent = score;
        if (score < 30) {
            badge.style.cssText = 'color:#10b981;border-color:rgba(16,185,129,0.4);background:rgba(16,185,129,0.1);';
            text.textContent = 'SECURE'; numEl.style.color='#10b981'; bar.style.background='#10b981';
            desc.textContent = 'All systems normal';
        } else if (score < 60) {
            badge.style.cssText = 'color:#f59e0b;border-color:rgba(245,158,11,0.4);background:rgba(245,158,11,0.1);';
            text.textContent = 'CAUTION'; numEl.style.color='#f59e0b'; bar.style.background='#f59e0b';
            desc.textContent = 'Elevated activity';
        } else {
            badge.style.cssText = 'color:#ef4444;border-color:rgba(239,68,68,0.4);background:rgba(239,68,68,0.1);';
            text.textContent = '⚠️ THREAT'; numEl.style.color='#ef4444'; bar.style.background='#ef4444';
            desc.textContent = 'Immediate attention needed!';
        }
    }

    // ── Historical Chart ──
    const histChart = new Chart(document.getElementById('histChart'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'CPU %', data: [], borderColor: '#7c3aed', backgroundColor: 'rgba(124,58,237,0.1)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0 },
                { label: 'Memory %', data: [], borderColor: '#06b6d4', backgroundColor: 'rgba(6,182,212,0.1)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0 },
                { label: 'Disk %', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.05)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
            plugins: { legend: { labels: { color: 'rgba(255,255,255,0.6)', font: { size: 11 } } } },
            scales: {
                y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(255,255,255,0.4)', callback: v => v + '%' } },
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(255,255,255,0.4)', maxTicksLimit: 8 } }
            }
        }
    });

    function pushChart(time, cpu, mem, disk) {
        const ds = histChart.data;
        ds.labels.push(time);
        ds.datasets[0].data.push(cpu);
        ds.datasets[1].data.push(mem);
        ds.datasets[2].data.push(disk);
        if (ds.labels.length > 30) {
            ds.labels.shift();
            ds.datasets.forEach(d => d.data.shift());
        }
        histChart.update('none');
    }

    // ── Fetch current metrics ──
    let dataPointCount = 0;
    async function fetchMetrics() {
        try {
            const res = await fetch('/api/metrics/current');
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const d = await res.json();
            const cpu = d.cpu_percent.toFixed(1);
            const mem = d.memory_percent.toFixed(1);
            const disk = d.disk_percent.toFixed(1);
            document.getElementById('cpuVal').textContent = cpu + '%';
            document.getElementById('memVal').textContent = mem + '%';
            document.getElementById('diskVal').textContent = disk + '%';
            document.getElementById('cpuBar').style.width = cpu + '%';
            document.getElementById('memBar').style.width = mem + '%';
            document.getElementById('diskBar').style.width = disk + '%';
            if (d.process_count) document.getElementById('procCount').textContent = d.process_count;
            const t = new Date().toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'});
            pushChart(t, parseFloat(cpu), parseFloat(mem), parseFloat(disk));
            document.getElementById('apiStatus').textContent = '🟢 Online';
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('en-IN');
            document.getElementById('dataPoints').textContent = ++dataPointCount;
            addLog(`CPU:${cpu}% | MEM:${mem}% | DISK:${disk}%`, 'ok');
        } catch(e) {
            document.getElementById('apiStatus').textContent = '🔴 Error';
            addLog('Metrics fetch failed: ' + e.message, 'err');
        }
    }

    // ── Fetch threat score ──
    async function fetchThreat() {
        try {
            const res = await fetch('/api/threat/score');
            const d = await res.json();
            const score = d.threat_score || 0;
            document.getElementById('gaugeScore').textContent = score;
            setGaugeNeedle(score);
            updateThreatBadge(score);
            if (score > 60) addLog(`⚠️ High threat score detected: ${score}`, 'warn');
        } catch(e) {
            addLog('Threat score fetch failed', 'warn');
        }
    }

    // ── Button actions ──
    async function refreshAll() { addLog('Manual refresh triggered', 'info'); await fetchMetrics(); await fetchThreat(); }

    async function testApi() {
        try {
            const res = await fetch('/health');
            const d = await res.json();
            addLog('API Health: ' + JSON.stringify(d), 'ok');
        } catch(e) { addLog('API test failed: ' + e.message, 'err'); }
    }

    async function triggerKillSwitch() {
        if (!confirm('⚠️ Are you sure you want to trigger the Kill Switch? This will attempt to isolate the system.')) return;
        try {
            const res = await fetch('/api/kill-switch', { method: 'POST' });
            addLog('🚨 Kill switch triggered! Response: ' + res.status, 'warn');
        } catch(e) { addLog('Kill switch: ' + e.message, 'warn'); }
    }

    // ── Auto-refresh ──
    fetchMetrics();
    fetchThreat();
    setInterval(fetchMetrics, 5000);
    setInterval(fetchThreat, 10000);
    addLog('War Room initialized. Monitoring active. 🛡️', 'ok');
</script>
</body>
</html>
HTMLEOF

echo "✅ Dashboard HTML created!"

# ─── Step 4: Configure Nginx ────────────────────────────────
echo ""
echo "⚙️  Step 4: Configuring Nginx..."
sudo tee /etc/nginx/sites-available/brahmastra > /dev/null << 'NGINXEOF'
server {
    listen 80;
    server_name _;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/javascript application/json;

    # Dashboard - serve static files
    root /var/www/brahmastra;
    index index.html;

    # Proxy API requests to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'Authorization,Content-Type';
    }

    # Proxy health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Proxy WebSocket connections
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Serve dashboard for all other routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINXEOF

# Enable site and disable default
sudo ln -sf /etc/nginx/sites-available/brahmastra /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and reload Nginx
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "✅ Nginx configured and started!"

# ─── Step 5: Open firewall port 80 ─────────────────────────
echo ""
echo "🔒 Step 5: Ensuring port 80 is accessible..."
# Note: Also open port 80 in your AWS Security Group if not done already!

PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🎉 SETUP COMPLETE! Your Brahmastra War Room is LIVE!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "🌐 Dashboard URL : http://${PUBLIC_IP}"
echo "🔌 API Docs URL  : http://${PUBLIC_IP}/api/docs (via main API)"
echo "❤️  Health Check  : http://${PUBLIC_IP}/health"
echo ""
echo "📋 IMPORTANT: Make sure port 80 is open in AWS Security Group!"
echo "   Go to: EC2 → Security Groups → Inbound Rules → Add HTTP (port 80)"
echo ""
