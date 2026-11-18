-- Separate database for pytest's integration tests, so `make test`
-- never truncates the tables the dashboard reads from.
CREATE DATABASE rent_test;
