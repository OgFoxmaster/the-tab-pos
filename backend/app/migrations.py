"""Forward-only, additive schema migrations.

The project intentionally has no migration framework. `create_all` builds fresh
databases, and this module patches columns introduced after the first release so an
existing shop database keeps working. Every statement is additive and idempotent.
"""

from sqlalchemy import inspect, text

from .db import engine

_TABLES = {
    "companies": "CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, slug VARCHAR(100) NOT NULL UNIQUE, is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP)",
    "branches": "CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, name VARCHAR(160) NOT NULL, address VARCHAR(250), is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP)",
}

_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "phone": "ALTER TABLE users ADD COLUMN phone VARCHAR(30)",
        "company_id": "ALTER TABLE users ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE users ADD COLUMN branch_id INTEGER",
        "department": "ALTER TABLE users ADD COLUMN department VARCHAR(40) DEFAULT 'cashier'",
    },
    "products": {
        "company_id": "ALTER TABLE products ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE products ADD COLUMN branch_id INTEGER",
    },
    "stock_movements": {
        "company_id": "ALTER TABLE stock_movements ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE stock_movements ADD COLUMN branch_id INTEGER",
    },
    "sales": {
        "company_id": "ALTER TABLE sales ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE sales ADD COLUMN branch_id INTEGER",
        "client_reference": "ALTER TABLE sales ADD COLUMN client_reference VARCHAR(64)",
        "customer_name": "ALTER TABLE sales ADD COLUMN customer_name VARCHAR(120)",
        "vat": "ALTER TABLE sales ADD COLUMN vat NUMERIC(12, 2) DEFAULT 0",
        "refunded_at": "ALTER TABLE sales ADD COLUMN refunded_at TIMESTAMP",
        "refunded_by": "ALTER TABLE sales ADD COLUMN refunded_by INTEGER REFERENCES users(id)",
    },
    "expenses": {
        "company_id": "ALTER TABLE expenses ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE expenses ADD COLUMN branch_id INTEGER",
    },
    "audit_events": {
        "company_id": "ALTER TABLE audit_events ADD COLUMN company_id INTEGER",
        "branch_id": "ALTER TABLE audit_events ADD COLUMN branch_id INTEGER",
    },
    "sale_items": {
        "cost_price": "ALTER TABLE sale_items ADD COLUMN cost_price NUMERIC(10, 2)",
    },
}

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_client_reference ON sales (client_reference)",
    "CREATE INDEX IF NOT EXISTS ix_sales_sale_time ON sales (sale_time)",
)


def run_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table, statement in _TABLES.items():
            if table not in existing_tables:
                connection.execute(text(statement))
                print(f"Migrated: created {table}")
        existing_tables = set(inspect(engine).get_table_names())
        inspector = inspect(engine)
        for table, columns in _COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, statement in columns.items():
                if name not in present:
                    connection.execute(text(statement))
                    print(f"Migrated: added {table}.{name}")

        if "sales" in existing_tables:
            for statement in _INDEXES:
                connection.execute(text(statement))
