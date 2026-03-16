#!/usr/bin/env python3
"""
Health Monitor - Watches all services and alerts on issues
"""

import os
import time
import requests
import redis
from datetime import datetime
from dotenv import load_dotify

load_dotenv()

class HealthMonitor:
    def __init__(self):
        self.redis_client = redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )
        self.alert_webhook = os.getenv('ALERT_WEBHOOK_URL')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', 60))
        self.services = os.getenv('SERVICES', 'redis,content-creator,approval-bot').split(',')

    def check_redis(self) -> bool:
        """Check Redis connectivity"""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            print(f"Redis check failed: {e}")
            return False

    def check_service(self, service_name: str) -> dict:
        """Check a service's health"""
        if service_name == 'redis':
            return {
                'name': 'redis',
                'healthy': self.check_redis(),
                'queue_depth': self.redis_client.llen('pending_hooks')
            }

        if service_name == 'approval-bot':
            try:
                response = requests.get('http://approval-bot:8080/health', timeout=5)
                return {
                    'name': 'approval-bot',
                    'healthy': response.status_code == 200,
                    'data': response.json() if response.status_code == 200 else None
                }
            except Exception as e:
                return {
                    'name': 'approval-bot',
                    'healthy': False,
                    'error': str(e)
                }

        if service_name == 'content-creator':
            # Check if creator is producing content
            last_log = self.redis_client.get('creator:last_activity')
            if last_log:
                last_time = datetime.fromisoformat(last_log)
                healthy = (datetime.now() - last_time).seconds < 3600  # Within last hour
                return {
                    'name': 'content-creator',
                    'healthy': healthy,
                    'last_activity': last_log
                }
            return {
                'name': 'content-creator',
                'healthy': True,  # May be starting up
                'status': 'starting'
            }

        return {'name': service_name, 'healthy': False, 'error': 'Unknown service'}

    def run_health_checks(self):
        """Run health checks on all services"""
        results = []
        all_healthy = True

        for service in self.services:
            result = self.check_service(service.strip())
            results.append(result)

            if not result.get('healthy'):
                all_healthy = False
                self.send_alert(f"Service {service} is unhealthy: {result}", level='error')

        # Log summary
        status = "All healthy" if all_healthy else "Issues detected"
        print(f"[{datetime.now().isoformat()}] Health check: {status}")

        return results

    def send_alert(self, message: str, level: str = 'info'):
        """Send alert via webhook"""
        if not self.alert_webhook:
            return

        try:
            payload = {
                'level': level,
                'message': message,
                'service': 'health-monitor',
                'timestamp': datetime.now().isoformat()
            }
            requests.post(self.alert_webhook, json=payload, timeout=10)
        except Exception as e:
            print(f"Failed to send alert: {e}")

    def run(self):
        """Main monitoring loop"""
        print(f"Health Monitor started")
        print(f"Monitoring services: {self.services}")
        print(f"Check interval: {self.check_interval} seconds")

        while True:
            self.run_health_checks()
            time.sleep(self.check_interval)

if __name__ == '__main__':
    monitor = HealthMonitor()
    monitor.run()
