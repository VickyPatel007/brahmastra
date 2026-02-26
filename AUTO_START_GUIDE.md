# Setting Up Auto-Start for Brahmastra Backend

## 🎯 What This Does

Makes your Brahmastra backend API automatically start whenever your EC2 instance boots up. No more manual restarts!

---

## 📋 **Step-by-Step Instructions**

### **Step 1: Connect to Your EC2 Instance**

1. Go to: https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#ConnectToInstance:instanceId=i-055daf8bf7570a540
2. Click **"Connect"** button
3. You'll get a browser-based terminal

---

### **Step 2: Run the Auto-Start Setup**

Copy and paste this entire block into the terminal:

```bash
cd ~/brahmastra

# Create the systemd service file
sudo tee /etc/systemd/system/brahmastra.service > /dev/null <<'EOF'
[Unit]
Description=Brahmastra Self-Healing Infrastructure API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/brahmastra
Environment="PATH=/home/ubuntu/brahmastra/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/brahmastra/venv/bin/python3 /home/ubuntu/brahmastra/main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/brahmastra/app.log
StandardError=append:/home/ubuntu/brahmastra/app.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable brahmastra.service
sudo systemctl start brahmastra.service

# Check if it's running
sudo systemctl status brahmastra.service
```

---

### **Step 3: Verify It's Working**

Test the API from the EC2 terminal:

```bash
curl http://localhost:8000/health
```

You should see:
```json
{"status":"healthy","timestamp":"..."}
```

---

### **Step 4: Test from Your Computer**

Open a new terminal on your Mac and run:

```bash
curl http://13.127.243.89:8000/health
```

---

## ✅ **What You've Accomplished**

After running these commands:

1. ✅ Backend API is running NOW
2. ✅ Will auto-start on every EC2 boot
3. ✅ Will auto-restart if it crashes
4. ✅ Logs saved to `app.log`

---

## 🛠️ **Useful Commands**

Once the service is set up, you can manage it with these commands:

```bash
# Check if service is running
sudo systemctl status brahmastra

# View live logs
sudo journalctl -u brahmastra -f

# Restart the service
sudo systemctl restart brahmastra

# Stop the service
sudo systemctl stop brahmastra

# Start the service
sudo systemctl start brahmastra

# Disable auto-start (if needed)
sudo systemctl disable brahmastra
```

---

## 🧪 **Test Auto-Start**

To verify it works after reboot:

1. Stop your EC2 instance from AWS Console
2. Start it again
3. Wait 2-3 minutes
4. Test: `curl http://<new-ip>:8000/health`

It should work automatically! 🎉

---

## 🔍 **Troubleshooting**

### Service won't start?

```bash
# Check logs
sudo journalctl -u brahmastra -n 50

# Check if Python is in the right path
which python3

# Check if main.py exists
ls -la ~/brahmastra/main.py
```

### App crashes on start?

```bash
# Check app logs
tail -f ~/brahmastra/app.log

# Try running manually first
cd ~/brahmastra
source venv/bin/activate
python3 main.py
```

---

## 📊 **What's Next**

After this is working:
1. ✅ Set up PostgreSQL database (RDS)
2. ✅ Add database persistence
3. ✅ Implement authentication
4. ✅ Build dashboard UI

---

**Your new server IP**: http://13.127.243.89:8000

(Remember: IP changes every time you stop/start EC2!)
