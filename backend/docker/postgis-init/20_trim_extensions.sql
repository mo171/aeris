-- Removes the PostGIS extensions AERIS does not use, so the database contains only what it needs.
--
-- what  : Drops `postgis_tiger_geocoder` (US census address geocoding) and `postgis_topology`
--         (topological editing). Neither is used anywhere in this system.
-- where : Mounted into /docker-entrypoint-initdb.d/ and run once, on a fresh volume, after the image's own
--         10_postgis.sh has installed them. Numbered 20 so it sorts after that script.
-- how   : The image installs four extensions by default. Beyond being unused, the two dropped here put
--         `topology` and `tiger` on the search_path, which makes SQLAlchemy reflection - and therefore
--         `alembic check` - see roughly a hundred tables that no model describes.
--
--         `migrations/env.py` also filters extension-owned tables, because a managed Postgres such as
--         Supabase may install these and we cannot drop them there. This script is the local half: do not
--         rely on it alone.

DROP EXTENSION IF EXISTS postgis_tiger_geocoder CASCADE;
DROP EXTENSION IF EXISTS postgis_topology CASCADE;
DROP EXTENSION IF EXISTS fuzzystrmatch CASCADE;
