import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# Add root folder to sys.path to import app
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import app

class TestSecurityFeatures(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.app.config['TESTING'] = True
        app.app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.app.test_client()

    def test_is_current_time_near_scheduled(self):
        # Test exact match
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        self.assertTrue(app.is_current_time_near_scheduled(date_str, time_str))

        # Test within window (10 minutes before)
        ten_mins_before = now + timedelta(minutes=10)
        date_str = ten_mins_before.strftime("%Y-%m-%d")
        time_str = ten_mins_before.strftime("%H:%M")
        self.assertTrue(app.is_current_time_near_scheduled(date_str, time_str))

        # Test within window (60 minutes after)
        sixty_mins_after = now - timedelta(minutes=60)
        date_str = sixty_mins_after.strftime("%Y-%m-%d")
        time_str = sixty_mins_after.strftime("%H:%M")
        self.assertTrue(app.is_current_time_near_scheduled(date_str, time_str))

        # Test outside window (30 minutes before)
        thirty_mins_before = now + timedelta(minutes=30)
        date_str = thirty_mins_before.strftime("%Y-%m-%d")
        time_str = thirty_mins_before.strftime("%H:%M")
        self.assertFalse(app.is_current_time_near_scheduled(date_str, time_str))

        # Test outside window (3 hours after)
        three_hours_after = now - timedelta(hours=3)
        date_str = three_hours_after.strftime("%Y-%m-%d")
        time_str = three_hours_after.strftime("%H:%M")
        self.assertFalse(app.is_current_time_near_scheduled(date_str, time_str))

    def test_can_join_appointment(self):
        # Mock user
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.is_admin = False
        mock_user.role = "user"
        mock_user.email = "test@example.com"
        
        # Patch current_user
        original_current_user = app.current_user
        app.current_user = mock_user
        
        # Patch current_db_user_id to return "123"
        original_db_user_id = app.current_db_user_id
        app.current_db_user_id = lambda: "123"

        # Matching user ID
        appt = {"id": 1, "user_id": "123", "email": "other@example.com"}
        self.assertTrue(app.can_join_appointment(appt))

        # Matching email
        appt = {"id": 2, "user_id": "456", "email": "test@example.com"}
        self.assertTrue(app.can_join_appointment(appt))

        # Non-matching user
        appt = {"id": 3, "user_id": "456", "email": "other@example.com"}
        self.assertFalse(app.can_join_appointment(appt))

        # Admin user
        mock_user.is_admin = True
        self.assertTrue(app.can_join_appointment(appt))

        # Restore
        app.current_user = original_current_user
        app.current_db_user_id = original_db_user_id

if __name__ == "__main__":
    unittest.main()
