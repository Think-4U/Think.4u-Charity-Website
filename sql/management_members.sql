-- ==============================================================================
-- Think.4U - Management Members Schema
-- Table for Governing Body, Core Team, and Managing Team
-- ==============================================================================

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

-- Index for fast queries ordered by category & sort order
CREATE INDEX IF NOT EXISTS idx_mgmt_category_sort ON public.management_members (category, is_active, sort_order);

-- RLS Policies
ALTER TABLE public.management_members ENABLE ROW LEVEL SECURITY;

-- Public can read active management members
CREATE POLICY "Public can view active management members"
    ON public.management_members
    FOR SELECT
    USING (is_active = true);

-- Authenticated service role has full access
CREATE POLICY "Service role full access on management members"
    ON public.management_members
    FOR ALL
    USING (true)
    WITH CHECK (true);
