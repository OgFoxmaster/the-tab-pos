"""Forward-only, additive schema migrations.

The project intentionally has no migration framework. `create_all` builds fresh
databases, and this module patches columns introduced after the first release so an
existing shop database keeps working. Every statement is additive and idempotent.
"""

from sqlalchemy import inspect, text

from .db import engine

_COLUMNS: dict[str, dict[str, str]] = {
    "sales": {
        "client_reference": "ALTER TABLE sales ADD COLUMN client_reference VARCHAR(64)",
        "customer_name": "ALTER TABLE sales ADD COLUMN customer_name VARCHAR(120)",
        "vat": "ALTER TABLE sales ADD COLUMN vat NUMERIC(12, 2) DEFAULT 0",
        "refunded_at": "ALTER TABLE sales ADD COLUMN refunded_at TIMESTAMP",
        "refunded_by": "ALTER TABLE sales ADD COLUMN refunded_by INTEGER REFERENCES users(id)",
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
