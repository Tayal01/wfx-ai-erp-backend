-- WFX AI ERP Assistant - Supabase PostgreSQL schema
-- Run this in Supabase SQL Editor before importing CSV data.

create extension if not exists vector;

create table if not exists buyers (
    buyer_id text primary key,
    company_name text not null unique,
    country text not null,
    buyer_category text not null,
    created_at timestamptz not null default now()
);

create table if not exists suppliers (
    supplier_id text primary key,
    company_name text not null unique,
    country text not null,
    contact text not null,
    lead_time_days integer not null check (lead_time_days >= 0),
    rating numeric(3, 2) not null check (rating >= 0 and rating <= 5),
    created_at timestamptz not null default now()
);

create table if not exists finished_goods (
    style_number text primary key,
    style_name text not null,
    category text not null,
    fabric text not null,
    gsm integer not null check (gsm > 0),
    color text not null,
    print text not null,
    season text not null,
    brand text not null,
    supplier text not null references suppliers(company_name),
    cost numeric(12, 2) not null check (cost >= 0),
    selling_price numeric(12, 2) not null check (selling_price >= 0),
    image_url text,
    embedding vector(512),
    created_at timestamptz not null default now()
);


create table if not exists sales_orders (
    order_number text primary key,
    buyer text not null references buyers(company_name),
    style_number text not null references finished_goods(style_number),
    quantity integer not null check (quantity > 0),
    unit_price numeric(12, 2) not null check (unit_price >= 0),
    shipment_date date not null,
    status text not null,
    created_at timestamptz not null default now()
);

create table if not exists sales_invoices (
    invoice_number text primary key,
    sales_order text not null references sales_orders(order_number),
    amount numeric(14, 2) not null check (amount >= 0),
    currency text not null,
    payment_status text not null,
    created_at timestamptz not null default now()
);

create table if not exists tech_packs (
    tech_pack_id text primary key,
    style_number text not null unique references finished_goods(style_number),
    fabric_details text not null,
    construction text not null,
    wash_instructions text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_buyers_company_name on buyers(company_name);
create index if not exists idx_suppliers_company_name on suppliers(company_name);
create index if not exists idx_finished_goods_category on finished_goods(category);
create index if not exists idx_finished_goods_supplier on finished_goods(supplier);
create index if not exists idx_finished_goods_season on finished_goods(season);
create index if not exists idx_sales_orders_buyer on sales_orders(buyer);
create index if not exists idx_sales_orders_style_number on sales_orders(style_number);
create index if not exists idx_sales_orders_status on sales_orders(status);
create index if not exists idx_sales_orders_shipment_date on sales_orders(shipment_date);
create index if not exists idx_sales_invoices_sales_order on sales_invoices(sales_order);
create index if not exists idx_sales_invoices_payment_status on sales_invoices(payment_status);
create index if not exists idx_tech_packs_style_number on tech_packs(style_number);

alter table buyers enable row level security;
alter table suppliers enable row level security;
alter table finished_goods enable row level security;
alter table sales_orders enable row level security;
alter table sales_invoices enable row level security;
alter table tech_packs enable row level security;
