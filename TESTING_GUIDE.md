# Testing Backend - Final Steps

## ✅ **Service is Running!**

Great! The backend service is **active (running)** on your EC2 instance.

---

## 🧪 **Test Locally First**

In your EC2 terminal, run:

```bash
curl http://localhost:8000/health
```

**Expected**: `{"status":"healthy","timestamp":"..."}`

---

## 🌐 **Test from Internet**

If localhost works, test from your Mac terminal:

```bash
# Health check
curl http://15.206.82.159:8000/health

# System metrics
curl http://15.206.82.159:8000/api/metrics/current

# Threat score
curl http://15.206.82.159:8000/api/threat/score

# Root endpoint
curl http://15.206.82.159:8000/
```

---

## ⚠️ **If Internet Test Fails**

The security group might not have port 8000 open. I'll check and fix it.

---

## 🎯 **Next: Open in Browser**

Once it works, open in your browser:

- **API Docs**: http://15.206.82.159:8000/docs
- **Health**: http://15.206.82.159:8000/health
- **Metrics**: http://15.206.82.159:8000/api/metrics/current

---

**First, confirm localhost works in EC2, then we'll fix internet access!** 🚀
