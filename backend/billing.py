"""
Brahmastra Billing & Cost Tracker
===================================
Tracks AWS infrastructure costs and resource usage.
Uses AWS Cost Explorer API when credentials are available,
falls back to estimates based on instance type.

Supports:
- EC2 instance cost tracking
- EBS volume costs
- Data transfer estimates
- Monthly/daily breakdowns
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger("Brahmastra-Billing")

# ── AWS Cost Estimates (per hour, Mumbai region) ─────────────
EC2_PRICING = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3a.micro": 0.0094,
    "t3a.small": 0.0188,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "c5.large": 0.085,
    "r5.large": 0.126,
}

EBS_PRICING_PER_GB = 0.08  # per month, gp3
ELASTIC_IP_COST = 3.60  # per month when not associated (free when associated)
DATA_TRANSFER_PER_GB = 0.1093  # first 10TB outbound


class BillingTracker:
    """Tracks and estimates AWS infrastructure costs."""

    def __init__(self):
        self.instance_type = os.getenv("INSTANCE_TYPE", "t2.micro")
        self.ebs_size_gb = int(os.getenv("EBS_SIZE_GB", "30"))
        self.started_at = datetime.now()
        self.custom_costs = []  # User-added costs
        self.daily_data_transfer_gb = 0.5  # Estimate
        self.servers_count = 1

        # Try to detect instance type
        self._detect_instance_info()
        logger.info(f"💰 Billing tracker initialized ({self.instance_type}, {self.ebs_size_gb}GB EBS)")

    def _detect_instance_info(self):
        """Try to detect EC2 instance type from metadata."""
        try:
            import requests
            resp = requests.get(
                "http://169.254.169.254/latest/meta-data/instance-type",
                timeout=2
            )
            if resp.status_code == 200:
                self.instance_type = resp.text.strip()
                logger.info(f"📌 Detected instance type: {self.instance_type}")
        except Exception:
            pass

        try:
            import requests
            resp = requests.get(
                "http://169.254.169.254/latest/meta-data/instance-id",
                timeout=2
            )
            if resp.status_code == 200:
                self.instance_id = resp.text.strip()
        except Exception:
            self.instance_id = "unknown"

    def get_hourly_cost(self) -> float:
        return EC2_PRICING.get(self.instance_type, 0.0116)

    def get_daily_cost(self) -> dict:
        ec2_daily = self.get_hourly_cost() * 24
        ebs_daily = (self.ebs_size_gb * EBS_PRICING_PER_GB) / 30
        data_daily = self.daily_data_transfer_gb * DATA_TRANSFER_PER_GB
        elastic_ip_daily = 0  # Free when associated

        total = ec2_daily + ebs_daily + data_daily + elastic_ip_daily

        return {
            "ec2": round(ec2_daily, 4),
            "ebs": round(ebs_daily, 4),
            "data_transfer": round(data_daily, 4),
            "elastic_ip": round(elastic_ip_daily, 4),
            "total": round(total, 4),
            "currency": "USD",
        }

    def get_monthly_cost(self) -> dict:
        daily = self.get_daily_cost()
        return {
            "ec2": round(daily["ec2"] * 30, 2),
            "ebs": round(daily["ebs"] * 30, 2),
            "data_transfer": round(daily["data_transfer"] * 30, 2),
            "elastic_ip": round(daily["elastic_ip"] * 30, 2),
            "custom": round(sum(c.get("amount", 0) for c in self.custom_costs), 2),
            "total": round(daily["total"] * 30 + sum(c.get("amount", 0) for c in self.custom_costs), 2),
            "currency": "USD",
        }

    def get_yearly_estimate(self) -> dict:
        monthly = self.get_monthly_cost()
        return {k: round(v * 12, 2) if isinstance(v, (int, float)) else v for k, v in monthly.items()}

    def get_running_cost(self) -> dict:
        """Get cost since tracking started."""
        hours_running = (datetime.now() - self.started_at).total_seconds() / 3600
        hourly = self.get_hourly_cost()
        total_so_far = hourly * hours_running

        return {
            "hours_running": round(hours_running, 1),
            "cost_so_far": round(total_so_far, 4),
            "started_at": self.started_at.isoformat(),
            "currency": "USD",
        }

    def add_custom_cost(self, name: str, amount: float, frequency: str = "monthly"):
        """Add a custom recurring cost (domain, SSL cert, monitoring tools, etc.)."""
        self.custom_costs.append({
            "name": name,
            "amount": amount,
            "frequency": frequency,
            "added_at": datetime.now().isoformat(),
        })

    def get_cost_breakdown(self) -> dict:
        """Full cost breakdown for the dashboard."""
        daily = self.get_daily_cost()
        monthly = self.get_monthly_cost()
        running = self.get_running_cost()

        # Calculate percentage breakdown
        total = monthly["total"] or 1
        breakdown_pct = {
            "ec2": round((monthly["ec2"] / total) * 100, 1),
            "ebs": round((monthly["ebs"] / total) * 100, 1),
            "data_transfer": round((monthly["data_transfer"] / total) * 100, 1),
        }

        return {
            "instance_type": self.instance_type,
            "instance_id": getattr(self, "instance_id", "unknown"),
            "ebs_size_gb": self.ebs_size_gb,
            "daily": daily,
            "monthly": monthly,
            "yearly_estimate": self.get_yearly_estimate(),
            "running": running,
            "breakdown_percentage": breakdown_pct,
            "custom_costs": self.custom_costs,
            "pricing_note": "Estimates based on AWS Mumbai (ap-south-1) on-demand pricing",
        }

    def get_savings_tips(self) -> List[dict]:
        """Generate cost-saving recommendations."""
        tips = []
        hourly = self.get_hourly_cost()
        monthly = self.get_monthly_cost()

        if self.instance_type.startswith("t2"):
            tips.append({
                "title": "Switch to T3/T3a instances",
                "description": f"T3a.micro costs $0.0094/hr vs your T2.micro at ${hourly}/hr. Save ~19% monthly.",
                "potential_savings": round((hourly - 0.0094) * 720, 2),
                "difficulty": "easy",
            })

        if monthly["total"] > 10:
            tips.append({
                "title": "Consider Reserved Instances",
                "description": "With a 1-year commitment, save up to 40% on EC2 costs.",
                "potential_savings": round(monthly["ec2"] * 0.4, 2),
                "difficulty": "medium",
            })

        tips.append({
            "title": "Use Spot Instances for non-critical workloads",
            "description": "Spot instances can save up to 90% for fault-tolerant tasks.",
            "potential_savings": round(monthly["ec2"] * 0.7, 2),
            "difficulty": "advanced",
        })

        if self.ebs_size_gb > 20:
            tips.append({
                "title": "Optimize EBS storage",
                "description": f"You have {self.ebs_size_gb}GB. Review if all storage is needed.",
                "potential_savings": round((self.ebs_size_gb - 20) * EBS_PRICING_PER_GB, 2),
                "difficulty": "easy",
            })

        return tips


# ── Singleton ─────────────────────────────────────────────────
billing_tracker = BillingTracker()
