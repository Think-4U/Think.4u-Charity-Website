import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from io import BytesIO

# Add root folder to sys.path to import app
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import app

class TestMeetingFeatures(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        app.app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.app.test_client()
        self.csrf_patcher = patch('app.verify_csrf_token', return_value=True)
        self.csrf_patcher.start()
        self.db_conn_patcher = patch('app.get_db_connection')
        self.mock_db_conn = self.db_conn_patcher.start()
        self.mock_cursor = MagicMock()
        self.mock_cursor.fetchone.return_value = None
        self.mock_db_conn.return_value.cursor.return_value = self.mock_cursor
        self.get_user_patcher = None

    def tearDown(self):
        self.csrf_patcher.stop()
        self.db_conn_patcher.stop()
        if self.get_user_patcher:
            self.get_user_patcher.stop()

    def mock_login(self, user_role="user", user_id=111, user_email="test@example.com", user_name="Test User"):
        user = app.User(
            id=user_id,
            email=user_email,
            name=user_name,
            role=user_role,
            is_admin=(user_role == "admin")
        )
        self.get_user_patcher = patch('flask_login.utils._get_user', return_value=user)
        self.get_user_patcher.start()
        return user

    def setup_supabase_mock(self, mock_supabase):
        queries = {}
        def get_table_mock(table_name):
            if table_name not in queries:
                q = MagicMock()
                q.select.return_value = q
                q.eq.return_value = q
                q.neq.return_value = q
                q.order.return_value = q
                q.limit.return_value = q
                q.update.return_value = q
                q.insert.return_value = q
                queries[table_name] = q
            return queries[table_name]

        mock_supabase.table.side_effect = get_table_mock
        for name in ["users", "appointments", "appointment_slots", "volunteer_events", "event_participants"]:
            get_table_mock(name)
        return queries

    @patch('app.supabase')
    def test_book_slot_already_booked(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # psycopg2 select queries mock
        self.mock_cursor.fetchone.side_effect = [
            {"id": 1, "status": "available", "registration_limit": 2, "slot_date": "2026-06-26", "slot_time": "10:00"}, # Slot query
            {"id": 99} # Duplicate check
        ]

        response = self.client.post('/appointments/slot/1/book', data={'purpose': 'Test', 'notes': 'Notes'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/appointments'))

    @patch('app.supabase')
    def test_book_slot_reaches_limit(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # psycopg2 select queries mock
        self.mock_cursor.fetchone.side_effect = [
            {"id": 1, "status": "available", "registration_limit": 1, "slot_date": "2026-06-26", "slot_time": "10:00"}, # Slot query
            None, # Duplicate check
            {"count": 1} # Count check (reached limit)
        ]

        response = self.client.post('/appointments/slot/1/book', data={'purpose': 'Test', 'notes': 'Notes'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/appointments'))

    @patch('app.supabase')
    def test_coordinator_add_participant_success(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Target user setup when target email is searched
        queries["users"].execute.return_value = MagicMock(data=[{
            "id": 222, "email": "two@example.com", "name": "User Two", "role": "user"
        }])

        # Appointments execute returns:
        # 1. Source meeting query -> valid scheduled meeting
        # 2. Check duplicate booking (already participant) -> empty
        queries["appointments"].execute.side_effect = [
            MagicMock(data=[{"id": 10, "meet_url": "https://meet.domain.com/room", "purpose": "Testing", "appointment_date": "2026-06-26", "appointment_time": "10:00"}]),
            MagicMock(data=[])
        ]

        response = self.client.post('/coordinator/meeting/10/add_participant', data={'email': 'two@example.com'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/coordinator'))
        # Verify the target user email was inserted into appointments
        queries["appointments"].insert.assert_called_once()

    @patch('app.supabase')
    def test_coordinator_update_settings(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Source meeting search
        queries["appointments"].execute.return_value = MagicMock(data=[{"id": 10, "meet_url": "https://meet.domain.com/room"}])

        response = self.client.post('/coordinator/meeting/10/update_settings', data={
            'show_chat': 'on',
            'show_screen_share': 'on'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].update.assert_called_once_with({
            "meeting_settings": {
                "show_chat": True,
                "show_screen_share": True,
                "show_raise_hand": False,
                "show_participants": False,
                "record_meeting": False
            },
            "updated_at": unittest.mock.ANY
        })

    @patch('app.supabase')
    def test_end_meeting_cascades(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Meeting query lookup
        queries["appointments"].execute.return_value = MagicMock(data=[{"id": 10, "uuid": "uuid-10", "meet_url": "https://meet.domain.com/room"}])

        # Patch can_join_appointment to authorize coordinator access
        with patch('app.can_join_appointment', return_value=True):
            response = self.client.post('/meeting/6ba7b810-9dad-11d1-80b4-00c04fd430c8/end')
            self.assertEqual(response.status_code, 302)
            # Verify update was called on appointments with matching meet_url (cascade end)
            queries["appointments"].update.assert_called_once_with({
                "status": "completed",
                "updated_at": unittest.mock.ANY
            })
            queries["appointments"].eq.assert_any_call("meet_url", "https://meet.domain.com/room")

    @patch('app.supabase')
    def test_appointments_slicing(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Return 5 meetings
        queries["appointments"].execute.return_value = MagicMock(data=[
            {"id": i, "purpose": f"Meeting {i}", "created_at": "2026-06-25", "status": "scheduled"} for i in range(1, 6)
        ])

        # Request default dashboard list (should slice to 3)
        response = self.client.get('/appointments')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meeting 1", response.data)
        self.assertNotIn(b"Meeting 4", response.data)  # Sliced out

        # Request all meetings (show_all=true)
        response = self.client.get('/appointments?show_all=true')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meeting 1", response.data)
        self.assertIn(b"Meeting 4", response.data)  # Not sliced out

    @patch('app.supabase')
    def test_appointments_get_coordinator_settings(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock coordinator settings
        queries["users"].execute.return_value = MagicMock(data=[
            {
                "global_meeting_settings": {
                    "allow_custom_requests": False,
                    "request_start_time": "10:30",
                    "request_end_time": "15:45"
                }
            }
        ])

        response = self.client.get('/appointments')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"allowCustomRequests = false", response.data)
        self.assertIn(b'requestStartTime = "10:30"', response.data)
        self.assertIn(b'requestEndTime = "15:45"', response.data)

    @patch('app.supabase')
    def test_coordinator_settings_get_post(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # GET settings
        response = self.client.get('/coordinator/settings')
        self.assertEqual(response.status_code, 200)

        # POST settings
        response = self.client.post('/coordinator/settings', data={
            'show_chat': 'on',
            'show_raise_hand': 'on'
        })
        self.assertEqual(response.status_code, 302)
        queries["users"].update.assert_called_once_with({
            "global_meeting_settings": {
                "show_chat": True,
                "show_screen_share": False,
                "show_raise_hand": True,
                "show_participants": False,
                "record_meeting": False,
                "holidays": []
            }
        })

    @patch('app.supabase')
    def test_coordinator_history(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        queries["appointments"].execute.return_value = MagicMock(data=[
            {"id": 1, "purpose": "History Meeting", "status": "scheduled"}
        ])
        queries["appointment_slots"].execute.return_value = MagicMock(data=[
            {"id": 1, "slot_date": "2026-06-25", "slot_time": "12:00", "status": "available"}
        ])

        response = self.client.get('/coordinator/history')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"History Meeting", response.data)

    @patch('app.supabase')
    def test_coordinator_meeting_detail(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Return target appointment
        queries["appointments"].execute.return_value = MagicMock(data=[
            {"id": 10, "purpose": "Details Purpose", "coordinator_id": 111, "meet_url": "https://meet.domain.com/room"}
        ])

        # GET detail
        response = self.client.get('/coordinator/meeting/10')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Details Purpose", response.data)

        # POST toggle share
        response = self.client.post('/coordinator/meeting/10', data={
            'action': 'toggle_share',
            'share_recording': 'on'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].update.assert_called_with({"share_recording": True})

    @patch('app.supabase')
    def test_meeting_room_invalid_rendering(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Completed meeting lookup
        queries["appointments"].execute.return_value = MagicMock(data=[
            {"id": 10, "uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8", "status": "completed", "user_id": 111}
        ])

        response = self.client.get('/meeting/6ba7b810-9dad-11d1-80b4-00c04fd430c8')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meeting Closed", response.data)
        self.assertIn(b"This meeting has already ended and cannot be joined.", response.data)

    @patch('app.supabase')
    def test_appointments_validation_past_date(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        response = self.client.post('/appointments', data={
            'appointment_date': '2020-01-01',
            'appointment_time': '10:00',
            'purpose': 'Past Meeting Discussion'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_not_called()

    @patch('app.supabase')
    def test_appointments_validation_sunday(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        response = self.client.post('/appointments', data={
            'appointment_date': '2026-06-28',
            'appointment_time': '10:00',
            'purpose': 'Sunday Discussion'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_called_once()
        inserted_payload = queries["appointments"].insert.call_args[0][0]
        self.assertEqual(inserted_payload["status"], "rescheduled")

    @patch('app.supabase')
    def test_appointments_validation_holiday(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        queries["users"].execute.return_value = MagicMock(data=[
            {"global_meeting_settings": {"holidays": ["2026-07-04"]}}
        ])
        
        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-04',
            'appointment_time': '10:00',
            'purpose': 'Holiday Discussion'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_called_once()
        inserted_payload = queries["appointments"].insert.call_args[0][0]
        self.assertEqual(inserted_payload["status"], "rescheduled")

    @patch('app.supabase')
    def test_appointments_validation_valid(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        queries["users"].execute.return_value = MagicMock(data=[])
        queries["appointment_slots"].execute.return_value = MagicMock(data=[
            {"slot_date": "2026-07-06"}
        ])
        
        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-06',
            'appointment_time': '10:00',
            'purpose': 'Valid Slot Discussion'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_called_once()
        inserted_payload = queries["appointments"].insert.call_args[0][0]
        self.assertEqual(inserted_payload["status"], "requested")

    @patch('app.supabase')
    def test_appointments_validation_custom_request_in_range(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        # Mock coordinators settings with custom request window 09:00 - 17:00
        queries["users"].execute.return_value = MagicMock(data=[
            {"global_meeting_settings": {
                "allow_custom_requests": True,
                "request_start_time": "09:00",
                "request_end_time": "17:00"
            }}
        ])
        queries["appointment_slots"].execute.return_value = MagicMock(data=[]) # No available pre-created slots
        
        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-06',
            'appointment_time': '10:30',  # Within 09:00 - 17:00 range
            'purpose': 'Custom Request Window Discussion'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_called_once()
        inserted_payload = queries["appointments"].insert.call_args[0][0]
        self.assertEqual(inserted_payload["status"], "requested")

    @patch('app.supabase')
    def test_coordinator_bulk_generate_slots(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        response = self.client.post('/coordinator/bulk_slots', data={
            'action': 'generate_slots',
            'start_date': '2026-07-01',
            'end_date': '2026-07-03',
            'start_time': '09:00',
            'end_time': '11:00',
            'duration_minutes': '60',
            'registration_limit': '1',
            'days_of_week': ['0', '1', '2'] # Mon, Tue, Wed
        })
        self.assertEqual(response.status_code, 302)
        # Should call insert on appointment_slots
        queries["appointment_slots"].insert.assert_called_once()

    @patch('app.supabase')
    def test_coordinator_reschedule_past_meetings(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)
        
        # Past uncompleted meeting
        queries["appointments"].execute.return_value = MagicMock(data=[{
            "id": 99,
            "user_id": 222,
            "purpose": "Past Meeting",
            "appointment_date": "2020-01-01",
            "appointment_time": "10:00",
            "status": "scheduled",
            "coordinator_id": 111,
            "email": "user@example.com",
            "name": "User Two"
        }])
        
        # Settings mock
        queries["users"].execute.return_value = MagicMock(data=[{
            "global_meeting_settings": {
                "reschedule_default_time": "10:00",
                "holidays": []
            }
        }])
        
        # No slots next day
        queries["appointment_slots"].execute.return_value = MagicMock(data=[])
        
        response = self.client.post('/coordinator/bulk_slots/reschedule_past')
        self.assertEqual(response.status_code, 302)
        # Should call update on appointments table to shift the date
        queries["appointments"].update.assert_called_once()
        update_payload = queries["appointments"].update.call_args[0][0]
        self.assertEqual(update_payload["status"], "scheduled")
        self.assertGreater(update_payload["appointment_date"], "2026-06-25")

    @patch('app.supabase')
    def test_coordinator_save_release_limit_date(self, mock_supabase):
        self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # 1. Invalid date format
        response = self.client.post('/coordinator/bulk_slots/settings', data={
            'request_start_time': '09:00',
            'request_end_time': '17:00',
            'reschedule_default_time': '10:00',
            'release_limit_date': 'abc'
        })
        self.assertEqual(response.status_code, 302)
        queries["users"].update.assert_not_called()

        # 2. Past date limit (e.g. 2020-01-01)
        response = self.client.post('/coordinator/bulk_slots/settings', data={
            'request_start_time': '09:00',
            'request_end_time': '17:00',
            'reschedule_default_time': '10:00',
            'release_limit_date': '2020-01-01'
        })
        self.assertEqual(response.status_code, 302)
        queries["users"].update.assert_not_called()

        # 3. Valid date limit (future date relative to any testing context)
        response = self.client.post('/coordinator/bulk_slots/settings', data={
            'request_start_time': '09:00',
            'request_end_time': '17:00',
            'reschedule_default_time': '10:00',
            'release_limit_date': '2026-10-15'
        })
        self.assertEqual(response.status_code, 302)
        queries["users"].update.assert_called_once()
        updated_settings = queries["users"].update.call_args[0][0]["global_meeting_settings"]
        self.assertEqual(updated_settings["release_limit_date"], "2026-10-15")

    @patch('app.supabase')
    def test_user_request_past_release_limit(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        queries["users"].execute.return_value = MagicMock(data=[
            {
                "global_meeting_settings": {
                    "allow_custom_requests": True,
                    "release_limit_date": "2026-07-10"
                }
            }
        ])

        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-12', # Past the limit 2026-07-10
            'appointment_time': '10:00',
            'purpose': 'Request past limit'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_called_once()
        inserted_payload = queries["appointments"].insert.call_args[0][0]
        self.assertEqual(inserted_payload["status"], "rescheduled")

    @patch('app.supabase')
    def test_coordinator_create_slot_past_release_limit(self, mock_supabase):
        user = self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock coordinator settings returning release_limit_date
        user.global_meeting_settings = {
            "release_limit_date": "2026-07-10"
        }

        response = self.client.post('/coordinator/slots', data={
            'slot_date': '2026-07-12', # Past the limit 2026-07-10
            'slot_time': '10:00'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointment_slots"].insert.assert_not_called()

    @patch('app.supabase')
    def test_coordinator_bulk_slots_past_release_limit(self, mock_supabase):
        user = self.mock_login(user_role="coordinator", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock coordinator settings returning release_limit_date
        user.global_meeting_settings = {
            "release_limit_date": "2026-07-10"
        }

        # 1. Generator range end date past limit
        response = self.client.post('/coordinator/bulk_slots', data={
            'action': 'generate_slots',
            'start_date': '2026-07-01',
            'end_date': '2026-07-15', # Past the limit 2026-07-10
            'start_time': '09:00',
            'end_time': '11:00',
            'duration_minutes': '60',
            'registration_limit': '1',
            'days_of_week': ['0']
        })
        self.assertEqual(response.status_code, 302)
        queries["appointment_slots"].insert.assert_not_called()

        # 2. CSV slot past limit
        csv_data = "date,time,duration_minutes,registration_limit,auto_accept\n2026-07-12,09:00,30,1,true\n"
        response = self.client.post('/coordinator/bulk_slots', data={
            'action': 'upload_csv',
            'csv_file': (BytesIO(csv_data.encode('utf-8')), 'test.csv')
        })
        self.assertEqual(response.status_code, 302)
        queries["appointment_slots"].insert.assert_not_called()

    @patch('app.supabase')
    def test_appointments_request_matches_slot(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock psycopg2: 
        # 1. Duplicate daily limit check -> None
        # 2. Match available slot check -> {"id": 456}
        self.mock_cursor.fetchone.side_effect = [None, {"id": 456}]

        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-06',
            'appointment_time': '10:00',
            'purpose': 'Request matching slot'
        })
        # Verifying it does a HTTP 307 redirect to book slot
        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers['Location'].endswith('/appointments/slot/456/book'))

    @patch('app.supabase')
    def test_appointments_duplicate_day_custom_request(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock psycopg2 returning duplicate appt row (i.e. already has an appt today)
        self.mock_cursor.fetchone.return_value = {"id": 88}

        response = self.client.post('/appointments', data={
            'appointment_date': '2026-07-06',
            'appointment_time': '10:00',
            'purpose': 'Duplicate Request'
        })
        self.assertEqual(response.status_code, 302)
        queries["appointments"].insert.assert_not_called()

    @patch('app.supabase')
    def test_appointments_duplicate_day_direct_booking(self, mock_supabase):
        self.mock_login(user_role="user", user_id=111)
        queries = self.setup_supabase_mock(mock_supabase)

        # Mock psycopg2:
        # 1. Fetch slot details
        # 2. Daily limit check -> returns active booking {"id": 88}
        self.mock_cursor.fetchone.side_effect = [
            {"id": 1, "status": "available", "registration_limit": 2, "slot_date": "2026-06-26", "slot_time": "10:00"},
            {"id": 88}
        ]

        response = self.client.post('/appointments/slot/1/book', data={
            'purpose': 'Book slot',
            'notes': 'Notes'
        })
        self.assertEqual(response.status_code, 302)
        # Should not insert duplicate booking or update slot status to booked
        queries["appointments"].insert.assert_not_called()

if __name__ == "__main__":
    unittest.main()
