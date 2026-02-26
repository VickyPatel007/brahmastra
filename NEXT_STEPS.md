# Instance Created - Next Steps

## ✅ **Instance Status: Running**

- **Instance ID**: `i-0a3af150703469ec1`
- **Public IP**: `15.206.82.159`
- **Status**: ✅ Running and healthy

---

## ⏳ **Backend Status: Installing (3-5 minutes)**

The user_data script is automatically:
1. Installing Python and dependencies
2. Creating the backend API
3. Setting up systemd service

**This takes 3-5 minutes after instance creation.**

---

## 🔍 **How to Check Progress**

### Option 1: Wait and Test (Easiest)

Wait 2-3 more minutes, then run:

```bash
curl http://15.206.82.159:8000/health
```

When you see this, it's ready:
```json
{"status":"healthy","timestamp":"..."}
```

---

### Option 2: Check Installation Progress (Advanced)

Connect to EC2 Instance Connect and check logs:

1. Go to: https://ap-south-1.console.aws.amazon.com/ec2/home?region=ap-south-1#ConnectToInstance:instanceId=i-0a3af150703469ec1
2. Click "Connect"
3. Run:

```bash
# Check if user_data script is still running
ps aux | grep cloud-init

# Check installation logs
sudo tail -f /var/log/cloud-init-output.log

# Check if backend service is running
sudo systemctl status brahmastra
```

---

## 🎯 **What Happens Automatically**

The instance is installing:
1. ✅ System updates
2. ✅ Python 3 + pip + venv
3. ✅ Docker (for future use)
4. ✅ FastAPI, Uvicorn, psutil, etc.
5. ✅ Creating main.py
6. ✅ Setting up systemd service
7. ✅ Starting backend API

---

## ✅ **Once It's Ready (5-10 min from now)**

Test all endpoints:

```bash
# Health check
curl http://15.206.82.159:8000/health

# System metrics
curl http://15.206.82.159:8000/api/metrics/current

# Threat score
curl http://15.206.82.159:8000/api/threat/score

# Root endpoint
curl http://15.206.82.159:8000/

# Swagger docs (open in browser)
open http://15.206.82.159:8000/docs
```

---

## 🚀 **After Backend is Running**

We'll move to the next steps:

### **Today's Remaining Goals:**
1. ✅ ~~Create instance with auto-start~~ **DONE!**
2. ⏳ Verify backend is running
3. ⏳ Test stop/start cycle (to verify auto-start works)
4. ⏭️ Set up PostgreSQL database (RDS free tier)
5. ⏭️ Add database persistence

---

## 💡 **Pro Tip**

From now on, whenever you stop/start this instance:
- ✅ Backend will auto-start
- ✅ No manual setup needed
- ⚠️ IP address will change (we'll fix this later with Elastic IP)

---

**Current Time**: The script started ~5 minutes ago, so it should be ready in about 2-3 more minutes.

**Just wait a bit and test**: `curl http://15.206.82.159:8000/health`
