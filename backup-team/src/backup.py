#!/usr/bin/env python3
"""
Backup Agent - Handles Redis persistence, data backups, and recovery
"""

import os
import json
import time
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import redis
import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

class BackupAgent:
    def __init__(self):
        self.redis_client = redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )
        self.backup_dir = Path('/backups')
        self.backup_dir.mkdir(exist_ok=True)
        self.retention_days = int(os.getenv('BACKUP_RETENTION_DAYS', 7))
        self.alert_webhook = os.getenv('ALERT_WEBHOOK_URL')

    def create_backup(self):
        """Create a full backup of Redis data"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = self.backup_dir / f"reel_backup_{timestamp}.json.gz"

        try:
            # Get all data from Redis
            data = {
                'pending_hooks': [],
                'approved_hooks': [],
                'rejected_hooks': [],
                'metadata': {
                    'backup_time': timestamp,
                    'backup_version': '1.0'
                }
            }

            # Export queues
            for queue in ['pending_hooks', 'approved_hooks', 'rejected_hooks']:
                items = self.redis_client.lrange(queue, 0, -1)
                data[queue] = [json.loads(item) for item in items]

            # Write compressed backup
            with gzip.open(backup_file, 'wt', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            print(f"Created backup: {backup_file}")
            self.log_activity(f"Backup created: {backup_file.name}")
            self.send_alert(f"Backup created successfully: {backup_file.name}")

            return backup_file

        except Exception as e:
            error_msg = f"Backup failed: {e}"
            print(error_msg)
            self.log_activity(error_msg)
            self.send_alert(error_msg, level='error')
            return None

    def restore_backup(self, backup_file: Path) -> bool:
        """Restore Redis data from backup"""
        try:
            with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                data = json.load(f)

            # Clear and restore queues
            for queue in ['pending_hooks', 'approved_hooks', 'rejected_hooks']:
                self.redis_client.delete(queue)
                for item in data.get(queue, []):
                    self.redis_client.lpush(queue, json.dumps(item))

            print(f"Restored from backup: {backup_file}")
            self.log_activity(f"Restored from backup: {backup_file.name}")
            return True

        except Exception as e:
            print(f"Restore failed: {e}")
            self.log_activity(f"Restore failed: {e}")
            return False

    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        for backup_file in self.backup_dir.glob('reel_backup_*.json.gz'):
            # Parse timestamp from filename
            try:
                timestamp_str = backup_file.stem.split('_', 2)[2]
                file_time = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

                if file_time < cutoff:
                    backup_file.unlink()
                    print(f"Deleted old backup: {backup_file.name}")
                    self.log_activity(f"Deleted old backup: {backup_file.name}")
            except (IndexError, ValueError):
                continue

    def get_latest_backup(self) -> Path:
        """Get the most recent backup file"""
        backups = sorted(self.backup_dir.glob('reel_backup_*.json.gz'))
        return backups[-1] if backups else None

    def send_alert(self, message: str, level: str = 'info'):
        """Send alert via webhook"""
        if not self.alert_webhook:
            return

        try:
            payload = {
                'level': level,
                'message': message,
                'service': 'backup-agent',
                'timestamp': datetime.now().isoformat()
            }
            requests.post(self.alert_webhook, json=payload, timeout=10)
        except Exception as e:
            print(f"Failed to send alert: {e}")

    def log_activity(self, message: str):
        """Log activity to file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('/app/logs/backup.log', 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

    def run(self):
        """Main backup loop"""
        interval = int(os.getenv('BACKUP_INTERVAL', 86400))  # Default daily

        print(f"Backup Agent started")
        print(f"Backup interval: {interval} seconds")
        print(f"Retention: {self.retention_days} days")

        # Schedule backups
        schedule.every(interval).seconds.do(self.create_backup)
        schedule.every(interval).seconds.do(self.cleanup_old_backups)

        while True:
            schedule.run_pending()
            time.sleep(60)

if __name__ == '__main__':
    agent = BackupAgent()
    agent.run()
