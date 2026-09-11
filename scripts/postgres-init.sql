-- DEVELOPMENT ONLY.
-- Production credentials must be provisioned through infrastructure/secrets management.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'education_app') THEN
    CREATE ROLE education_app LOGIN PASSWORD 'education_app_dev'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;

GRANT CONNECT ON DATABASE education_os TO education_app;
