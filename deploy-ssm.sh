#!/bin/bash
# Quick deployment using AWS Systems Manager

INSTANCE_ID="i-055daf8bf7570a540"

echo "🚀 Deploying Brahmastra to EC2 via AWS SSM..."

# Send commands via AWS SSM
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /home/ubuntu",
    "mkdir -p brahmastra && cd brahmastra",
    "sudo apt-get update -y",
    "sudo apt-get install -y python3-pip python3-venv",
    "python3 -m venv venv",
    "source venv/bin/activate",
    "pip install fastapi uvicorn psutil websockets pydantic",
    "cat > main.py << '\''EOF'\''
from fastapi import FastAPI
import psutil
from datetime import datetime

app = FastAPI(title=\"Brahmastra API\", version=\"0.1.0\")

@app.get(\"/\")
async def root():
    return {\"app\": \"Brahmastra\", \"status\": \"running\", \"location\": \"AWS Mumbai\"}

@app.get(\"/health\")
async def health():
    return {\"status\": \"healthy\", \"timestamp\": datetime.now().isoformat()}

@app.get(\"/api/metrics/current\")
async def metrics():
    return {
        \"cpu_percent\": psutil.cpu_percent(interval=1),
        \"memory_percent\": psutil.virtual_memory().percent,
        \"disk_percent\": psutil.disk_usage(\"'/\"').percent
    }

if __name__ == \"'__main__\"':
    import uvicorn
    uvicorn.run(app, host=\"'0.0.0.0\"', port=8000)
EOF
'\''",
    "nohup python3 main.py > app.log 2>&1 &",
    "echo \"'Brahmastra deployed!\"'"
  ]' \
  --region ap-south-1

echo "✅ Deployment command sent!"
echo "⏳ Wait 2-3 minutes for installation to complete"
echo "🌐 Then test: curl http://15.206.173.102:8000/health"
