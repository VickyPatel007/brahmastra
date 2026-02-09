# Project Brahmastra - Infrastructure as Code
# This creates a basic EC2 instance in AWS Free Tier

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

  # User data script to install Docker
  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y docker.io docker-compose git
              systemctl start docker
              systemctl enable docker
              usermod -aG docker ubuntu
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
