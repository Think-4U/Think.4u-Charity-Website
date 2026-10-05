import os
import sys
import argparse

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_maintenance_settings_live, upsert_cms_value, maintenance_window_is_active

def main():
    parser = argparse.ArgumentParser(description="Manage Think.4U Scheduled Maintenance mode.")
    parser.add_argument("--status", action="store_true", help="Display current maintenance status")
    parser.add_argument("--off", action="store_true", help="Turn off maintenance mode immediately")
    parser.add_argument("--on", action="store_true", help="Turn on maintenance mode")
    args = parser.parse_args()

    if args.off:
        print("[*] Disabling maintenance mode...")
        upsert_cms_value("maintenance_enabled", "false")
        print("[+] Maintenance mode disabled successfully! User access is restored.")
        return

    if args.on:
        print("[*] Enabling maintenance mode...")
        upsert_cms_value("maintenance_enabled", "true")
        print("[+] Maintenance mode enabled.")
        return

    # Default action: show status
    settings = get_maintenance_settings_live()
    is_active = maintenance_window_is_active(settings)
    print("=" * 50)
    print("Think.4U Maintenance Mode Status")
    print("=" * 50)
    print(f"Enabled in DB:   {settings.get('maintenance_enabled')}")
    print(f"Window Active:   {is_active}")
    print(f"Scheduled Start: {settings.get('maintenance_start') or 'Not set'}")
    print(f"Scheduled End:   {settings.get('maintenance_end') or 'Not set'}")
    print(f"Status Text:     {settings.get('maintenance_status')}")
    print(f"Message:         {settings.get('maintenance_message')[:80]}...")
    print("=" * 50)
    print("To disable maintenance:  python scripts/toggle_maintenance.py --off")
    print("To enable maintenance:   python scripts/toggle_maintenance.py --on")

if __name__ == "__main__":
    main()
