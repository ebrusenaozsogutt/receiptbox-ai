-- Runs once, when the postgres volume is first created.
-- A separate database so that `pytest` can never touch development data.
CREATE DATABASE receiptbox_test;
