# Getting Started with Brahmastra - Step by Step

## 🎯 Your First Day Checklist

### Hour 1: Install Tools

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Terraform
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# Install AWS CLI
brew install awscli

# Install Python 3.10+
brew install python@3.10

# Verify installations
terraform --version
aws --version
python3 --version
```

### Hour 2: Configure AWS

```bash
# Configure AWS credentials
aws configure

# You'll be prompted for:
# AWS Access Key ID: [paste your key]
# AWS Secret Access Key: [paste your secret]
# Default region name: ap-south-1
# Default output format: json

# Test AWS connection
aws ec2 describe-regions --region ap-south-1
```

### Hour 3: Deploy Your First Server

```bash
# Navigate to infrastructure folder
cd ~/brahmastra/infrastructure

# Initialize Terraform
terraform init

# Preview what will be created
terraform plan

# Create the infrastructure (type 'yes' when prompted)
terraform apply

# SAVE THE OUTPUT! It will show your server's public IP
# Example: instance_public_ip = "13.232.45.67"
```

### Hour 4: Set Up Backend

```bash
# SSH into your new server (replace with your IP)
ssh ubuntu@13.232.45.67

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3-pip python3-venv -y

# Clone your code (or create files manually)
mkdir ~/brahmastra
cd ~/brahmastra

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn psutil websockets

# Create main.py (copy from backend/main.py)
nano main.py
# Paste the code, save with Ctrl+X, Y, Enter

# Run the API
python3 main.py
```

### Hour 5: Test Your API

```bash
# From your LOCAL machine (not SSH), test the API
# Replace with your server IP
curl http://13.232.45.67:8000/

# You should see:
# {"app":"Brahmastra","version":"0.1.0","status":"running",...}

# Test health endpoint
curl http://13.232.45.67:8000/health

# Test metrics
curl http://13.232.45.67:8000/api/metrics/current

# Test threat score
curl http://13.232.45.67:8000/api/threat/score
```

### Hour 6: Keep It Running

```bash
# SSH back into your server
ssh ubuntu@13.232.45.67

# Install screen to keep app running
sudo apt install screen -y

# Start a screen session
screen -S brahmastra

# Run your app
cd ~/brahmastra
source venv/bin/activate
python3 main.py

# Detach from screen: Press Ctrl+A, then D
# Your app keeps running even if you disconnect!

# To reconnect later:
screen -r brahmastra
```

## ✅ Success Checklist

After your first day, you should have:
- [x] AWS account configured
- [x] EC2 instance running in Mumbai (ap-south-1)
- [x] FastAPI backend running on port 8000
- [x] API responding to health checks
- [x] Metrics endpoint returning CPU/memory data

## 🔜 Tomorrow: Week 1 Tasks

1. **Set up PostgreSQL database** (RDS free tier)
2. **Add database models** (SQLAlchemy)
3. **Store metrics in database** (not just memory)
4. **Add authentication** (API keys)
5. **Set up GitHub repo** (version control)

## 🆘 Troubleshooting

### Can't SSH into server?
```bash
# Check security group allows SSH from your IP
aws ec2 describe-security-groups --group-ids <your-sg-id>

# Add your IP if needed
aws ec2 authorize-security-group-ingress \
  --group-id <your-sg-id> \
  --protocol tcp \
  --port 22 \
  --cidr <your-ip>/32
```

### API not accessible?
```bash
# Check if app is running
ps aux | grep python

# Check if port 8000 is open
sudo netstat -tulpn | grep 8000

# Check security group allows port 8000
# Go to AWS Console → EC2 → Security Groups → Edit inbound rules
```

### Out of memory?
```bash
# Check memory usage
free -h

# If low, create swap file
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## 💡 Pro Tips

1. **Set billing alerts** in AWS (Console → Billing → Budgets)
   - Alert at $5, $10, $25

2. **Save your SSH key** somewhere safe
   - You'll need it every time you connect

3. **Use screen or tmux** to keep processes running
   - Your app won't stop when you disconnect

4. **Monitor AWS Free Tier usage**
   - Console → Billing → Free Tier
   - Make sure you're not exceeding limits

5. **Backup your work**
   - Push code to GitHub daily
   - Take EC2 snapshots weekly

## 📞 Need Help?

If you get stuck:
1. Check the error message carefully
2. Google the exact error
3. Check AWS CloudWatch logs
4. Ask in r/aws or r/devops subreddit

---

**You've got this! One step at a time.** 🚀
