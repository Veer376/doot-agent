-- Local profile only; not a replacement for Supabase Auth.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY, email text);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT '00000000-0000-4000-8000-000000000001'::uuid $$;
DO $$ BEGIN CREATE ROLE doot_local NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT doot_local TO CURRENT_USER;
