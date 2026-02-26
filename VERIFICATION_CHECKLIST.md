# Backend Verification Checklist

## 🔍 **What to Check in EC2 Terminal**

### **Step 1: Check Service Status**

```bash
sudo systemctl status brahmastra
```

**Expected**: `active (running)` in green

---

### **Step 2: Test Locally**

```bash
curl http://localhost:8000/health
```

**Expected**: `{"status":"healthy","timestamp":"..."}`

---

### **Step 3: If Service Failed**

```bash
sudo journalctl -u brahmastra -n 20
```

Look for error messages.

---

## 📊 **Possible Outcomes**

| What You See | What It Means | Next Step |
|--------------|---------------|-----------|
| ✅ Service running + localhost works | Port/firewall issue | Check security group |
| ❌ Service failed | App crashed | Check logs |
| ❌ Service not found | Setup incomplete | Re-run setup commands |
| ✅ Service running but localhost fails | App not listening | Check app.log |

---

**Please run the commands above and share the output!**
