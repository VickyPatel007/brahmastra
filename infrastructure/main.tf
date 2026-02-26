# Project Brahmastra - Infrastructure as Code
# This creates a basic EC2 instance in AWS Free Tier

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region = "ap-south-1"  # Mumbai region (DPDP compliance)
}

# VPC and Networking
resource "aws_vpc" "brahmastra_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "brahmastra-vpc"
  }
}

resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.brahmastra_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "ap-south-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "brahmastra-public-subnet"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.brahmastra_vpc.id

  tags = {
    Name = "brahmastra-igw"
  }
}

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.brahmastra_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "brahmastra-public-rt"
  }
}

resource "aws_route_table_association" "public_rta" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}

# Security Group
resource "aws_security_group" "brahmastra_sg" {
  name        = "brahmastra-sg"
  description = "Security group for Brahmastra app"
  vpc_id      = aws_vpc.brahmastra_vpc.id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # TODO: Restrict to your IP
    description = "SSH access"
  }

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # FastAPI (8000)
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Dashboard (8080)
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Dashboard HTTP"
  }

  # Outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "brahmastra-sg"
  }
}

# EC2 Instance (Free Tier: t3.micro)
resource "aws_instance" "brahmastra_server" {
  ami           = "ami-0c2af51e265bd5e0e"  # Ubuntu 22.04 LTS in ap-south-1
  instance_type = "t3.micro"  # Free tier eligible

  subnet_id                   = aws_subnet.public_subnet.id
  vpc_security_group_ids      = [aws_security_group.brahmastra_sg.id]
  associate_public_ip_address = true

  # Storage (30GB is free tier limit)
  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  # User data script to install Docker and set up backend
  user_data = <<-EOF
              #!/bin/bash
              set -e
              
              # Update system
              apt-get update
              apt-get upgrade -y
              
              # Install dependencies
              apt-get install -y docker.io docker-compose git python3-pip python3.10-venv
              
              # Start Docker
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ubuntu
              
              # Set up Brahmastra backend
              cd /home/ubuntu
              mkdir -p brahmastra
              cd brahmastra
              
              # Create Python virtual environment
              python3 -m venv venv
              source venv/bin/activate
              
              # Install Python packages
              pip install --upgrade pip
              pip install fastapi uvicorn psutil websockets pydantic
              
              # Create main.py
              cat > main.py << 'EOFPY'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psutil
from datetime import datetime

app = FastAPI(
    title="Brahmastra API",
    description="Self-Healing Infrastructure Monitoring System",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "app": "Brahmastra",
        "version": "0.1.0",
        "status": "running",
        "message": "Self-Healing Infrastructure Monitoring System",
        "location": "AWS Mumbai (ap-south-1)"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/metrics/current")
async def get_current_metrics():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    return {
        "status": "healthy" if cpu < 80 and memory < 80 else "warning",
        "cpu_percent": cpu,
        "memory_percent": memory,
        "disk_percent": disk,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/threat/score")
async def get_threat_score():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    threat_score = int((cpu + memory) / 2)
    
    return {
        "threat_score": min(threat_score, 100),
        "level": "low" if threat_score < 50 else "medium" if threat_score < 80 else "high",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOFPY
              
              # Create systemd service
              cat > /etc/systemd/system/brahmastra.service << 'EOFSVC'
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
EOFSVC
              
              # Fix ownership
              chown -R ubuntu:ubuntu /home/ubuntu/brahmastra
              
              # Enable and start service
              systemctl daemon-reload
              systemctl enable brahmastra.service
              systemctl start brahmastra.service
              EOF

  tags = {
    Name = "brahmastra-server"
  }
}

# Outputs
output "instance_public_ip" {
  value       = aws_instance.brahmastra_server.public_ip
  description = "Public IP of Brahmastra server"
}

output "instance_id" {
  value       = aws_instance.brahmastra_server.id
  description = "Instance ID"
}
