# Project Brahmastra 🛡️

**Self-Healing Infrastructure Monitoring System for Indian Startups**

Brahmastra automatically protects, detects, and recovers your infrastructure from cyber attacks—without you lifting a finger.

## 🚀 Quick Start Guide

### Prerequisites
- AWS Account (Free Tier)
- Terraform installed
- Python 3.10+
- Git

### Step 1: Deploy Infrastructure (5 minutes)

```bash
# Clone the repo
git clone <your-repo-url>
cd brahmastra

# Deploy to AWS
cd infrastructure
terraform init
terraform plan
terraform apply

# Note the public IP from output
```

### Step 2: Set Up Backend (10 minutes)

```bash
# SSH into your EC2 instance
ssh ubuntu@<your-instance-ip>

# Clone your repo on the server
git clone <your-repo-url>
cd brahmastra/backend

# Install Python dependencies
pip3 install -r requirements.txt

# Run the API
python3 main.py
```

### Step 3: Test the API

```bash
# From your local machine
curl http://<your-instance-ip>:8000/health

# You should see: {"status":"healthy","timestamp":"..."}
```

## 📁 Project Structure

```
brahmastra/
├── backend/              # FastAPI backend
│   ├── main.py          # Main API application
│   └── requirements.txt # Python dependencies
├── frontend/            # React dashboard (coming soon)
├── infrastructure/      # Terraform IaC
│   └── main.tf         # AWS infrastructure
└── docs/               # Documentation
```

## 🎯 Current Features (Week 1)

- ✅ Basic FastAPI backend
- ✅ Health monitoring endpoints
- ✅ System metrics collection (CPU, memory, disk)
- ✅ Threat score calculation
- ✅ Incident logging
- ✅ Manual kill-switch endpoint

## 🔜 Coming Next (Week 2-4)

- [ ] Self-healing mechanism
- [ ] Database integration (PostgreSQL)
- [ ] Anomaly detection (ML)
- [ ] Honeypots
- [ ] Dashboard UI

## 💰 AWS Free Tier Usage

This setup uses:
- 1x EC2 t3.micro (750 hrs/month free)
- 30GB EBS storage (30GB free)
- Minimal data transfer

**Estimated cost**: $0-5/month (within free tier)

## 📚 Documentation

- [Solo Founder MVP Roadmap](../brain/solo_founder_mvp.md)
- [Technical Architecture](../brain/brahmastra_technical_architecture.md)
- [Executive Summary](../brain/executive_summary.md)

## 🤝 Contributing

This is a solo founder project. If you want to contribute or become a co-founder, reach out!

## 📝 License

Proprietary - All rights reserved

---

**Built with ❤️ in India 🇮🇳**
