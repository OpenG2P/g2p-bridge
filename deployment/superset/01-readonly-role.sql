-- Read-only Postgres role used by Superset to connect to the G2P Bridge data
-- (bridge + SPAR + Example Bank). Run as a Postgres superuser, e.g.:
--   kubectl -n <ns> exec -i <postgres-pod> -- psql -U postgres -f - < 01-readonly-role.sql
-- Change the password before using in any non-trial environment, and set the
-- same value in the Superset database connections (see provision_dashboards.py
-- or enter it at import time).

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'superset_ro') THEN
    CREATE ROLE superset_ro LOGIN PASSWORD 'CHANGE_ME';
  END IF;
END $$;

-- g2p_bridge (database name = bridge release name, dashes -> underscores).
GRANT CONNECT ON DATABASE g2p_bridge TO superset_ro;
\connect g2p_bridge
GRANT USAGE ON SCHEMA public TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO superset_ro;

-- SPAR mapper.
\connect postgres
GRANT CONNECT ON DATABASE spar TO superset_ro;
\connect spar
GRANT USAGE ON SCHEMA public TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO superset_ro;

-- Example Bank simulator.
\connect postgres
GRANT CONNECT ON DATABASE example_bank_db TO superset_ro;
\connect example_bank_db
GRANT USAGE ON SCHEMA public TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO superset_ro;
