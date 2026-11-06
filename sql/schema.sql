-- Tables for the invoice intake workflow. Safe to run more than once.

create table if not exists invoices_seen (
    file_hash text primary key,
    file_name text,
    received_at timestamptz default now()
);

create table if not exists invoices_posted (
    id serial primary key,
    vendor text,
    invoice_number text,
    bill_id text,
    total numeric(12, 2),
    extracted jsonb,
    posted_at timestamptz default now(),
    unique (vendor, invoice_number)
);

create table if not exists invoice_exceptions (
    id serial primary key,
    file_name text,
    vendor text,
    invoice_number text,
    issues text[],
    extracted jsonb,
    created_at timestamptz default now()
);

create table if not exists invoice_failures (
    id serial primary key,
    file_name text,
    node text,
    error text,
    created_at timestamptz default now(),
    retried_at timestamptz
);
