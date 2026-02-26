# Database subnet for RDS (requires 2 AZs)
resource "aws_subnet" "private_subnet_1" {
  vpc_id            = aws_vpc.brahmastra_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "ap-south-1a"

  tags = {
    Name = "brahmastra-private-subnet-1"
  }
}

resource "aws_subnet" "private_subnet_2" {
  vpc_id            = aws_vpc.brahmastra_vpc.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "ap-south-1b"

  tags = {
    Name = "brahmastra-private-subnet-2"
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "brahmastra_db_subnet" {
  name       = "brahmastra-db-subnet"
  subnet_ids = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]

  tags = {
    Name = "brahmastra-db-subnet-group"
  }
}

# Security Group for RDS
resource "aws_security_group" "rds_sg" {
  name        = "brahmastra-rds-sg"
  description = "Security group for Brahmastra RDS PostgreSQL"
  vpc_id      = aws_vpc.brahmastra_vpc.id

  # PostgreSQL access from EC2
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.brahmastra_sg.id]
    description     = "PostgreSQL from EC2"
  }

  # PostgreSQL access from anywhere (for development)
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "PostgreSQL from internet (dev only)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "brahmastra-rds-sg"
  }
}

# Random password for RDS
resource "random_password" "db_password" {
  length  = 16
  special = true
}

# RDS PostgreSQL Instance (Free Tier)
resource "aws_db_instance" "brahmastra_db" {
  identifier        = "brahmastra-db"
  engine            = "postgres"
  engine_version    = "15"  # Use major version only
  instance_class    = "db.t3.micro"  # Free tier eligible
  allocated_storage = 20              # Free tier limit

  db_name  = "brahmastra_db"
  username = "brahmastra_admin"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.brahmastra_db_subnet.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  publicly_accessible = true  # For development
  skip_final_snapshot = true  # For development

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  tags = {
    Name = "brahmastra-postgresql"
  }
}

# Outputs for database connection
output "db_endpoint" {
  value       = aws_db_instance.brahmastra_db.endpoint
  description = "PostgreSQL database endpoint"
}

output "db_name" {
  value       = aws_db_instance.brahmastra_db.db_name
  description = "Database name"
}

output "db_username" {
  value       = aws_db_instance.brahmastra_db.username
  description = "Database username"
  sensitive   = true
}

output "db_password" {
  value       = random_password.db_password.result
  description = "Database password"
  sensitive   = true
}
