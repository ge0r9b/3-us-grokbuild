-- Postgres schema for the dynamic US districts app.
-- Shapes stay in the app's own encoding. PostGIS is enabled so a later
-- load can store real geometries without a second project.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dataset (
  path text PRIMARY KEY,
  body text NOT NULL,
  bytes integer NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- County presidential results. Keys in the static files are "State|County"
-- and values are [Democratic votes, Republican votes, total].
CREATE TABLE IF NOT EXISTS election_county (
  year integer NOT NULL,
  state text NOT NULL,
  county text NOT NULL,
  dem integer NOT NULL,
  rep integer NOT NULL,
  total integer NOT NULL,
  PRIMARY KEY (year, state, county)
);

CREATE TABLE IF NOT EXISTS zcta (
  zip text PRIMARY KEY,
  lat double precision NOT NULL,
  lon double precision NOT NULL
);
