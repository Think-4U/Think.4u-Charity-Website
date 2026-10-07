-- ================================================================
-- Think.4U — Neon DB Row Level Security (RLS) Policies
-- ================================================================
-- SECURITY MODEL:
--   • The Flask backend connects as `neondb_owner` (the DB owner).
--   • FORCE ROW LEVEL SECURITY means even the table owner must
--     satisfy a policy — no silent bypass possible.
--   • Only `neondb_owner` has explicit ALLOW policies.
--   • Any other PostgreSQL principal (e.g., someone who steals a
--     read-only credential) is denied all access by default.
--   • SSL + channel_binding=require is enforced at the transport layer.
-- ================================================================

BEGIN;

-- ----------------------------------------------------------------
-- ENABLE + FORCE RLS on all 18 tables
-- FORCE means even the table owner (neondb_owner) must pass a policy.
-- ----------------------------------------------------------------
ALTER TABLE public.users                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users                FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.donations            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donations            FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.volunteers           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteers           FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.programs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.programs             FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.cms_content          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_content          FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.notifications        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications        FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.appointments         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointments         FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.appointment_slots    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointment_slots    FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.grievances           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grievances           FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.volunteer_events     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_events     FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.event_participants   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_participants   FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.event_certificates   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_certificates   FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.fundraisers          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fundraisers          FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.media_assets         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.media_assets         FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.contact_messages     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_messages     FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.cookie_consents      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cookie_consents      FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.security_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_events      FORCE  ROW LEVEL SECURITY;

ALTER TABLE public.meeting_attendance   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_attendance   FORCE  ROW LEVEL SECURITY;

-- ----------------------------------------------------------------
-- DROP any stale policies (idempotent re-run safety)
-- ----------------------------------------------------------------
DO $$
DECLARE
    pol RECORD;
BEGIN
    FOR pol IN
        SELECT policyname, tablename
        FROM pg_policies
        WHERE schemaname = 'public'
        AND policyname LIKE 'think4u_%'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol.policyname, pol.tablename);
    END LOOP;
END $$;

-- ================================================================
-- POLICIES: Grant neondb_owner (Flask backend) full access.
-- All other principals are denied by default (no matching policy).
-- ================================================================

-- users (sensitive — never expose directly)
CREATE POLICY think4u_users_app
    ON public.users FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- donations (financial — backend only)
CREATE POLICY think4u_donations_app
    ON public.donations FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- volunteers
CREATE POLICY think4u_volunteers_app
    ON public.volunteers FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- programs
CREATE POLICY think4u_programs_app
    ON public.programs FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- cms_content
CREATE POLICY think4u_cms_content_app
    ON public.cms_content FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- notifications
CREATE POLICY think4u_notifications_app
    ON public.notifications FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- appointments
CREATE POLICY think4u_appointments_app
    ON public.appointments FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- appointment_slots
CREATE POLICY think4u_appointment_slots_app
    ON public.appointment_slots FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- grievances
CREATE POLICY think4u_grievances_app
    ON public.grievances FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- volunteer_events
CREATE POLICY think4u_volunteer_events_app
    ON public.volunteer_events FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- event_participants
CREATE POLICY think4u_event_participants_app
    ON public.event_participants FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- event_certificates
CREATE POLICY think4u_event_certificates_app
    ON public.event_certificates FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- fundraisers
CREATE POLICY think4u_fundraisers_app
    ON public.fundraisers FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- media_assets
CREATE POLICY think4u_media_assets_app
    ON public.media_assets FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- contact_messages
CREATE POLICY think4u_contact_messages_app
    ON public.contact_messages FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- cookie_consents
CREATE POLICY think4u_cookie_consents_app
    ON public.cookie_consents FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- security_events (audit log — read by app, written by app)
CREATE POLICY think4u_security_events_app
    ON public.security_events FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- meeting_attendance
CREATE POLICY think4u_meeting_attendance_app
    ON public.meeting_attendance FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- management_members
ALTER TABLE public.management_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY think4u_management_members_app
    ON public.management_members FOR ALL TO neondb_owner
    USING (true) WITH CHECK (true);

-- ================================================================
-- VERIFY: list enabled policies (for confirmation)
-- ================================================================
SELECT
    tablename,
    policyname,
    cmd,
    roles
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;

COMMIT;
