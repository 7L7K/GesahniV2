-- docker/initdb/00-init.sql
-- Runs once by postgres entrypoint. Creates app role + both DBs.
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') THEN
      CREATE ROLE app LOGIN PASSWORD 'app_pw' CREATEDB;
   END IF;
END
$$;

-- Create dev DB if missing
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gesahni') THEN
      EXECUTE 'CREATE DATABASE gesahni OWNER app';
   END IF;
END
$$;

-- Create test DB if missing
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gesahni_test') THEN
      EXECUTE 'CREATE DATABASE gesahni_test OWNER app';
   END IF;
END
$$;
