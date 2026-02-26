# Amazon Q Prompts for Brahmastra Deployment

## 🤖 **Using Amazon Q to Deploy Brahmastra**

Here are prompts you can use with Amazon Q AI in the AWS Console:

---

## 📋 **Prompt 1: Check Existing Instances**

```
Show me all EC2 instances in ap-south-1 region with their status, IP addresses, and names
```

---

## 📋 **Prompt 2: Launch New EC2 Instance**

```
Launch a new t3.micro EC2 instance in ap-south-1 (Mumbai) region with the following:
- Name: brahmastra-server
- AMI: Ubuntu 22.04 LTS
- Instance type: t3.micro (free tier)
- Storage: 30GB gp3
- Security group: Allow SSH (22), HTTP (80), HTTPS (443), and port 8000 from anywhere
- Auto-assign public IP
- Create a new key pair named brahmastra-key
```

---

## 📋 **Prompt 3: Set Up Backend After Instance Launch**

```
Connect to my EC2 instance and run these commands:
1. Update system: sudo apt-get update
2. Install Python: sudo apt-get install -y python3-venv python3-pip
3. Create directory: mkdir -p /home/ubuntu/brahmastra && cd /home/ubuntu/brahmastra
4. Create virtual environment: python3 -m venv venv
5. Activate venv: source venv/bin/activate
6. Install packages: pip install fastapi uvicorn psutil websockets pydantic
```

---

## 📋 **Prompt 4: Create FastAPI Application**

```
Create a file /home/ubuntu/brahmastra/main.py with a FastAPI application that has:
- Health check endpoint at /health
- System metrics endpoint at /api/metrics/current (CPU, memory, disk using psutil)
- Threat score endpoint at /api/threat/score
- CORS enabled for all origins
- Run on host 0.0.0.0 port 8000
```

---

## 📋 **Prompt 5: Set Up Auto-Start Service**

```
Create a systemd service for my FastAPI app:
- Service name: brahmastra
- Working directory: /home/ubuntu/brahmastra
- Command: /home/ubuntu/brahmastra/venv/bin/python3 /home/ubuntu/brahmastra/main.py
- User: ubuntu
- Auto-restart on failure
- Enable on boot
- Start the service now
```

---

## 📋 **Prompt 6: Check Service Status**

```
Check if the brahmastra service is running and show me:
1. Service status
2. Last 20 log lines
3. Whether port 8000 is listening
4. Test the health endpoint at localhost:8000/health
```

---

## 📋 **Prompt 7: Fix Security Group**

```
Ensure my EC2 instance security group allows inbound traffic on:
- Port 22 (SSH) from anywhere
- Port 80 (HTTP) from anywhere
- Port 443 (HTTPS) from anywhere
- Port 8000 (Custom TCP) from anywhere
```

---

## 🎯 **Quick Start Prompt (All-in-One)**

```
I need to deploy a FastAPI backend application called Brahmastra:

1. Launch a t3.micro EC2 instance in ap-south-1 with Ubuntu 22.04
2. Configure security group to allow ports 22, 80, 443, and 8000
3. Install Python 3, pip, and create virtual environment at /home/ubuntu/brahmastra
4. Install FastAPI, Uvicorn, psutil, websockets, pydantic
5. Create a FastAPI app with health check, metrics, and threat score endpoints
6. Set up systemd service to auto-start the app on boot
7. Start the service and verify it's accessible on port 8000

Show me the public IP address when done.
```

---

## 💡 **Tips for Using Amazon Q**

1. **Be specific**: Include region, instance type, and exact requirements
2. **One step at a time**: If the all-in-one prompt doesn't work, use individual prompts
3. **Verify each step**: Ask Q to show you the status after each action
4. **Save outputs**: Copy the public IP and instance ID for later use

---

## 🔧 **If Instance Was Deleted**

```
My EC2 instance was terminated. Please:
1. Check if there are any running instances in ap-south-1
2. If none, create a new t3.micro instance with the Brahmastra configuration
3. Use my existing Terraform configuration if available
4. Show me the new instance ID and public IP
```

---

**Try these prompts with Amazon Q and let me know what happens!** 🚀
