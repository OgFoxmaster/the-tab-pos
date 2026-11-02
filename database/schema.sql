CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(40) NOT NULL DEFAULT 'cashier',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100) DEFAULT 'General',
    unit VARCHAR(30) DEFAULT 'unit',
    buying_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    selling_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(30),
    email VARCHAR(120),
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    movement_type VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    reference VARCHAR(80),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales (
    id SERIAL PRIMARY KEY,
    sale_number VARCHAR(50) UNIQUE NOT NULL,
    cashier_id INTEGER NOT NULL REFERENCES users(id),
    subtotal NUMERIC(12, 2) DEFAULT 0,
    discount NUMERIC(12, 2) DEFAULT 0,
    total NUMERIC(12, 2) DEFAULT 0,
    payment_method VARCHAR(40) DEFAULT 'cash',
    payment_status VARCHAR(40) DEFAULT 'paid',
    sale_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sale_items (
    id SERIAL PRIMARY KEY,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    total NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    method VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    reference VARCHAR(120),
    status VARCHAR(40) DEFAULT 'completed',
    paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    category VARCHAR(80) DEFAULT 'General',
    amount NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(40) DEFAULT 'cash',
    recorded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_events (
    id SERIAL PRIMARY KEY,
    actor_id INTEGER REFERENCES users(id),
    event_type VARCHAR(80) NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
