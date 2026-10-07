-- =====================================================
-- Think.4U - Neon Serverless PostgreSQL Schema Setup
-- Optimized for Neon DB & Neon Auth (Better Auth)
-- =====================================================

BEGIN;

-- Enable pgcrypto (standard in PostgreSQL / Neon DB)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =====================================================
-- 1) SHARED HELPER FUNCTIONS
-- =====================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- =====================================================
-- 2) APPLICATION TABLES (PUBLIC SCHEMA)
-- =====================================================

-- 2.1 Users table (compatible with direct Flask-Login and Neon Auth bridge)
CREATE TABLE IF NOT EXISTS public.users (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    neon_user_id TEXT UNIQUE, -- Optional link to neon_auth.users.id
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    phone TEXT,
    address TEXT,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    role TEXT NOT NULL DEFAULT 'donor',
    email_verified BOOLEAN NOT NULL DEFAULT false,
    last_login_at TIMESTAMPTZ,
    global_meeting_settings JSONB NOT NULL DEFAULT '{"show_chat": true, "show_screen_share": true, "show_raise_hand": true, "show_participants": true, "record_meeting": false, "holidays": [], "request_start_time": "09:00", "request_end_time": "17:00", "allow_custom_requests": true, "reschedule_default_time": "10:00"}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.2 Donations
CREATE TABLE IF NOT EXISTS public.donations (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    amount INTEGER NOT NULL CHECK (amount > 0),
    donation_ref TEXT,
    donation_number BIGINT,
    purpose_type TEXT NOT NULL DEFAULT 'self',
    purpose_id TEXT,
    purpose_label TEXT,
    razorpay_order_id TEXT UNIQUE,
    razorpay_payment_id TEXT,
    razorpay_signature TEXT,
    payment_method TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    receipt_emailed BOOLEAN NOT NULL DEFAULT false,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.3 Volunteers
CREATE TABLE IF NOT EXISTS public.volunteers (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    interest TEXT,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.4 Programs
CREATE TABLE IF NOT EXISTS public.programs (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.5 CMS Content (Key-Value Dynamic Content)
CREATE TABLE IF NOT EXISTS public.cms_content (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.6 Notifications
CREATE TABLE IF NOT EXISTS public.notifications (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.7 Appointments
CREATE TABLE IF NOT EXISTS public.appointments (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    coordinator_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    slot_id BIGINT,
    name TEXT,
    email TEXT,
    appointment_date TEXT,
    appointment_time TEXT,
    requested_date TEXT,
    requested_time TEXT,
    scheduled_date TEXT,
    scheduled_time TEXT,
    purpose TEXT NOT NULL,
    notes TEXT,
    meet_url TEXT,
    status TEXT NOT NULL DEFAULT 'requested',
    meeting_settings JSONB NOT NULL DEFAULT '{"show_chat": true, "show_screen_share": true, "show_raise_hand": true, "show_participants": true}'::jsonb,
    recording_url TEXT,
    share_recording BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.8 Appointment Slots
CREATE TABLE IF NOT EXISTS public.appointment_slots (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    coordinator_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    booked_by_user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    slot_date TEXT NOT NULL,
    slot_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 30,
    meet_url TEXT,
    auto_accept BOOLEAN NOT NULL DEFAULT true,
    status TEXT NOT NULL DEFAULT 'available',
    registration_limit INTEGER NOT NULL DEFAULT 1,
    meeting_settings JSONB NOT NULL DEFAULT '{"show_chat": true, "show_screen_share": true, "show_raise_hand": true, "show_participants": true}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.9 Grievances
CREATE TABLE IF NOT EXISTS public.grievances (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    related_donation_id BIGINT REFERENCES public.donations(id) ON DELETE SET NULL,
    name TEXT,
    email TEXT,
    issue_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    admin_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.10 Volunteer Events
CREATE TABLE IF NOT EXISTS public.volunteer_events (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    program_id BIGINT REFERENCES public.programs(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    city TEXT,
    event_date TEXT,
    event_time TEXT,
    image_url TEXT,
    max_registrations INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.11 Event Participants
CREATE TABLE IF NOT EXISTS public.event_participants (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    event_id BIGINT NOT NULL REFERENCES public.volunteer_events(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name TEXT,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'donor',
    status TEXT NOT NULL DEFAULT 'registered',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, user_id)
);

-- 2.12 Event Certificates
CREATE TABLE IF NOT EXISTS public.event_certificates (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    event_id BIGINT NOT NULL REFERENCES public.volunteer_events(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    certificate_url TEXT,
    review_note TEXT,
    reviewed_by_user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, user_id)
);

-- 2.13 Fundraisers
CREATE TABLE IF NOT EXISTS public.fundraisers (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    target_amount NUMERIC NOT NULL DEFAULT 0,
    raised_amount NUMERIC NOT NULL DEFAULT 0,
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.14 Media Assets (Stored in S3/Cloudflare R2 or direct CDN)
CREATE TABLE IF NOT EXISTS public.media_assets (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    media_type TEXT NOT NULL,
    placement TEXT NOT NULL,
    title TEXT,
    url TEXT NOT NULL,
    is_published BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 100,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.15 Contact Messages
CREATE TABLE IF NOT EXISTS public.contact_messages (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.16 Cookie Consents
CREATE TABLE IF NOT EXISTS public.cookie_consents (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    anon_session_id TEXT,
    accepted BOOLEAN NOT NULL DEFAULT true,
    policy_version TEXT NOT NULL DEFAULT '1',
    ip_hash TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.17 Security Events
CREATE TABLE IF NOT EXISTS public.security_events (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_hash TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2.18 Meeting Attendance
CREATE TABLE IF NOT EXISTS public.meeting_attendance (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    meeting_key TEXT NOT NULL,
    appointment_id BIGINT REFERENCES public.appointments(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'coordinator', 'participant')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (meeting_key, user_id)
);

-- =====================================================
-- 3) FOREIGN KEY CONSTRAINTS & ALTERATIONS
-- =====================================================

DO $$
BEGIN
    ALTER TABLE public.appointments
        ADD CONSTRAINT appointments_slot_fk
        FOREIGN KEY (slot_id) REFERENCES public.appointment_slots(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
    WHEN undefined_table THEN NULL;
END $$;

-- Check Constraints
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE public.users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('donor', 'volunteer', 'both', 'admin', 'coordinator'));

ALTER TABLE public.event_participants DROP CONSTRAINT IF EXISTS event_participants_role_check;
ALTER TABLE public.event_participants
    ADD CONSTRAINT event_participants_role_check
    CHECK (role IN ('donor', 'volunteer', 'both', 'admin', 'coordinator'));

ALTER TABLE public.event_participants DROP CONSTRAINT IF EXISTS event_participants_status_check;
ALTER TABLE public.event_participants
    ADD CONSTRAINT event_participants_status_check
    CHECK (status IN ('registered', 'attended', 'cancelled'));

ALTER TABLE public.event_certificates DROP CONSTRAINT IF EXISTS event_certificates_status_check;
ALTER TABLE public.event_certificates
    ADD CONSTRAINT event_certificates_status_check
    CHECK (status IN ('pending', 'approved', 'rejected'));

ALTER TABLE public.donations DROP CONSTRAINT IF EXISTS donations_status_check;
ALTER TABLE public.donations
    ADD CONSTRAINT donations_status_check
    CHECK (status IN ('pending', 'paid', 'failed', 'cancelled'));

ALTER TABLE public.donations DROP CONSTRAINT IF EXISTS donations_purpose_type_check;
ALTER TABLE public.donations
    ADD CONSTRAINT donations_purpose_type_check
    CHECK (purpose_type IN ('self', 'program', 'fundraiser', 'event'));

ALTER TABLE public.appointments DROP CONSTRAINT IF EXISTS appointments_status_check;
ALTER TABLE public.appointments
    ADD CONSTRAINT appointments_status_check
    CHECK (status IN ('requested', 'pending', 'scheduled', 'booked', 'rescheduled', 'completed', 'cancelled'));

ALTER TABLE public.appointment_slots DROP CONSTRAINT IF EXISTS appointment_slots_status_check;
ALTER TABLE public.appointment_slots
    ADD CONSTRAINT appointment_slots_status_check
    CHECK (status IN ('available', 'booked', 'unavailable', 'cancelled'));

ALTER TABLE public.grievances DROP CONSTRAINT IF EXISTS grievances_status_check;
ALTER TABLE public.grievances
    ADD CONSTRAINT grievances_status_check
    CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'));

ALTER TABLE public.fundraisers DROP CONSTRAINT IF EXISTS fundraisers_status_check;
ALTER TABLE public.fundraisers
    ADD CONSTRAINT fundraisers_status_check
    CHECK (status IN ('active', 'paused', 'closed'));

ALTER TABLE public.media_assets DROP CONSTRAINT IF EXISTS media_assets_media_type_check;
ALTER TABLE public.media_assets
    ADD CONSTRAINT media_assets_media_type_check
    CHECK (media_type IN ('image', 'video'));

ALTER TABLE public.media_assets DROP CONSTRAINT IF EXISTS media_assets_placement_check;
ALTER TABLE public.media_assets
    ADD CONSTRAINT media_assets_placement_check
    CHECK (placement IN ('home_hero', 'home_gallery', 'home_video'));

-- =====================================================
-- 4) HIGH-PERFORMANCE INDEXES
-- =====================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uuid ON public.users(uuid);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);
CREATE INDEX IF NOT EXISTS idx_users_neon_id ON public.users(neon_user_id) WHERE neon_user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_donations_uuid ON public.donations(uuid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_donations_ref_unique ON public.donations(donation_ref) WHERE donation_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_donations_number ON public.donations(donation_number);
CREATE INDEX IF NOT EXISTS idx_donations_user_id ON public.donations(user_id);
CREATE INDEX IF NOT EXISTS idx_donations_email ON public.donations(email);
CREATE INDEX IF NOT EXISTS idx_donations_status ON public.donations(status);
CREATE INDEX IF NOT EXISTS idx_donations_purpose ON public.donations(purpose_type, purpose_id);
CREATE INDEX IF NOT EXISTS idx_donations_created_at ON public.donations(created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_volunteers_uuid ON public.volunteers(uuid);
CREATE INDEX IF NOT EXISTS idx_volunteers_user_id ON public.volunteers(user_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_email ON public.volunteers(email);
CREATE INDEX IF NOT EXISTS idx_volunteers_status ON public.volunteers(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_programs_uuid ON public.programs(uuid);
CREATE INDEX IF NOT EXISTS idx_programs_status ON public.programs(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cms_content_uuid ON public.cms_content(uuid);
CREATE INDEX IF NOT EXISTS idx_cms_content_key ON public.cms_content(key);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_uuid ON public.notifications(uuid);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON public.notifications(user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_uuid ON public.appointments(uuid);
CREATE INDEX IF NOT EXISTS idx_appointments_user_created ON public.appointments(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointments_coordinator ON public.appointments(coordinator_id, scheduled_date, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON public.appointments(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_appointment_slots_uuid ON public.appointment_slots(uuid);
CREATE INDEX IF NOT EXISTS idx_appointment_slots_availability ON public.appointment_slots(status, slot_date, slot_time);
CREATE INDEX IF NOT EXISTS idx_appointment_slots_coordinator ON public.appointment_slots(coordinator_id, slot_date, slot_time);

CREATE UNIQUE INDEX IF NOT EXISTS idx_grievances_uuid ON public.grievances(uuid);
CREATE INDEX IF NOT EXISTS idx_grievances_user_id ON public.grievances(user_id);
CREATE INDEX IF NOT EXISTS idx_grievances_related_donation ON public.grievances(related_donation_id);
CREATE INDEX IF NOT EXISTS idx_grievances_status ON public.grievances(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_volunteer_events_uuid ON public.volunteer_events(uuid);
CREATE INDEX IF NOT EXISTS idx_volunteer_events_program_id ON public.volunteer_events(program_id);
CREATE INDEX IF NOT EXISTS idx_volunteer_events_status_date ON public.volunteer_events(status, event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_volunteer_events_program_unique ON public.volunteer_events(program_id) WHERE program_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_participants_uuid ON public.event_participants(uuid);
CREATE INDEX IF NOT EXISTS idx_event_participants_event_id ON public.event_participants(event_id);
CREATE INDEX IF NOT EXISTS idx_event_participants_user_id ON public.event_participants(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_certificates_uuid ON public.event_certificates(uuid);
CREATE INDEX IF NOT EXISTS idx_event_certificates_event_id ON public.event_certificates(event_id);
CREATE INDEX IF NOT EXISTS idx_event_certificates_user_id ON public.event_certificates(user_id);
CREATE INDEX IF NOT EXISTS idx_event_certificates_status ON public.event_certificates(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_fundraisers_uuid ON public.fundraisers(uuid);
CREATE INDEX IF NOT EXISTS idx_fundraisers_status ON public.fundraisers(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_media_assets_uuid ON public.media_assets(uuid);
CREATE INDEX IF NOT EXISTS idx_media_assets_public ON public.media_assets(placement, media_type, is_published, sort_order);

CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_messages_uuid ON public.contact_messages(uuid);
CREATE INDEX IF NOT EXISTS idx_contact_messages_status_created ON public.contact_messages(status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cookie_consents_uuid ON public.cookie_consents(uuid);
CREATE INDEX IF NOT EXISTS idx_cookie_consents_user ON public.cookie_consents(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cookie_consents_anon ON public.cookie_consents(anon_session_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_security_events_uuid ON public.security_events(uuid);
CREATE INDEX IF NOT EXISTS idx_security_events_type_created ON public.security_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_meeting_attendance_key ON public.meeting_attendance(meeting_key);

-- =====================================================
-- 5) AUTOMATIC UPDATED_AT TRIGGERS
-- =====================================================

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_donations_updated_at ON public.donations;
CREATE TRIGGER trg_donations_updated_at BEFORE UPDATE ON public.donations
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_volunteers_updated_at ON public.volunteers;
CREATE TRIGGER trg_volunteers_updated_at BEFORE UPDATE ON public.volunteers
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_programs_updated_at ON public.programs;
CREATE TRIGGER trg_programs_updated_at BEFORE UPDATE ON public.programs
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_cms_content_updated_at ON public.cms_content;
CREATE TRIGGER trg_cms_content_updated_at BEFORE UPDATE ON public.cms_content
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON public.appointments;
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON public.appointments
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_appointment_slots_updated_at ON public.appointment_slots;
CREATE TRIGGER trg_appointment_slots_updated_at BEFORE UPDATE ON public.appointment_slots
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_grievances_updated_at ON public.grievances;
CREATE TRIGGER trg_grievances_updated_at BEFORE UPDATE ON public.grievances
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_volunteer_events_updated_at ON public.volunteer_events;
CREATE TRIGGER trg_volunteer_events_updated_at BEFORE UPDATE ON public.volunteer_events
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_event_participants_updated_at ON public.event_participants;
CREATE TRIGGER trg_event_participants_updated_at BEFORE UPDATE ON public.event_participants
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_event_certificates_updated_at ON public.event_certificates;
CREATE TRIGGER trg_event_certificates_updated_at BEFORE UPDATE ON public.event_certificates
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_fundraisers_updated_at ON public.fundraisers;
CREATE TRIGGER trg_fundraisers_updated_at BEFORE UPDATE ON public.fundraisers
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_media_assets_updated_at ON public.media_assets;
CREATE TRIGGER trg_media_assets_updated_at BEFORE UPDATE ON public.media_assets
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_contact_messages_updated_at ON public.contact_messages;
CREATE TRIGGER trg_contact_messages_updated_at BEFORE UPDATE ON public.contact_messages
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 2.21 Management Members (Governing Body, Core Team, Managing Team)
CREATE TABLE IF NOT EXISTS public.management_members (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('governing_body', 'core_team', 'managing_team')),
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    image_url TEXT,
    tags TEXT,
    description TEXT,
    social_links JSONB DEFAULT '{}'::jsonb,
    sort_order INT NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mgmt_category_sort ON public.management_members (category, is_active, sort_order);

DROP TRIGGER IF EXISTS trg_management_members_updated_at ON public.management_members;
CREATE TRIGGER trg_management_members_updated_at BEFORE UPDATE ON public.management_members
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

COMMIT;
