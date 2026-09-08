-- ============================================================
--  Banking Agentic AI System — PostgreSQL Schema
--  Run: psql -U postgres -d banking_agent -f schema.sql
-- ============================================================

-- Clean slate (development only — remove in production)
DROP SCHEMA IF EXISTS banking CASCADE;
CREATE SCHEMA banking;
SET search_path TO banking;


-- ============================================================
--  DOMAIN TABLES (the actual banking data)
-- ============================================================

-- ── Customers ────────────────────────────────────────
CREATE TABLE customers (
    customer_id     VARCHAR(20)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    address         TEXT,
    password_hash   VARCHAR(255) NOT NULL,       -- bcrypt hash
    kyc_status      VARCHAR(20)  NOT NULL DEFAULT 'pending'
                    CHECK (kyc_status IN ('pending', 'verified', 'under_review', 'rejected')),
    kyc_last_updated TIMESTAMPTZ,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customers_email ON customers (email);


-- ── Roles & Permissions (RBAC) ───────────────────────
CREATE TABLE roles (
    role_id     SERIAL       PRIMARY KEY,
    role_name   VARCHAR(50)  NOT NULL UNIQUE,    -- e.g. 'view_accounts'
    description VARCHAR(200)
);

CREATE TABLE customer_roles (
    customer_id VARCHAR(20)  NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    role_id     INTEGER      NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    granted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (customer_id, role_id)
);


-- ── Accounts ─────────────────────────────────────────
CREATE TABLE accounts (
    account_id  VARCHAR(20)    PRIMARY KEY,
    customer_id VARCHAR(20)    NOT NULL REFERENCES customers(customer_id),
    type        VARCHAR(20)    NOT NULL
                CHECK (type IN ('savings', 'checking', 'fixed_deposit', 'current')),
    balance     DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    currency    VARCHAR(3)     NOT NULL DEFAULT 'USD',
    status      VARCHAR(20)    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'frozen', 'closed', 'dormant')),
    opened_date DATE           NOT NULL DEFAULT CURRENT_DATE,
    closed_date DATE,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_customer ON accounts (customer_id);
CREATE INDEX idx_accounts_status   ON accounts (status);


-- ── Transactions ─────────────────────────────────────
CREATE TABLE transactions (
    transaction_id  VARCHAR(30)    PRIMARY KEY,
    account_id      VARCHAR(20)    NOT NULL REFERENCES accounts(account_id),
    type            VARCHAR(10)    NOT NULL
                    CHECK (type IN ('credit', 'debit')),
    amount          DECIMAL(15, 2) NOT NULL CHECK (amount > 0),
    balance_after   DECIMAL(15, 2),              -- running balance snapshot
    description     VARCHAR(255)   NOT NULL,
    category        VARCHAR(50)    NOT NULL,
    reference_id    VARCHAR(50),                  -- external ref (e.g. payment gateway)
    status          VARCHAR(20)    NOT NULL DEFAULT 'completed'
                    CHECK (status IN ('pending', 'completed', 'failed', 'reversed')),
    transaction_date TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_txn_account      ON transactions (account_id);
CREATE INDEX idx_txn_date         ON transactions (account_id, transaction_date DESC);
CREATE INDEX idx_txn_category     ON transactions (account_id, category);
CREATE INDEX idx_txn_status       ON transactions (status);


-- ── Service Requests ─────────────────────────────────
CREATE TABLE service_requests (
    request_id   VARCHAR(30)  PRIMARY KEY,
    customer_id  VARCHAR(20)  NOT NULL REFERENCES customers(customer_id),
    account_id   VARCHAR(20)  REFERENCES accounts(account_id),  -- nullable (not all requests are account-specific)
    type         VARCHAR(30)  NOT NULL
                 CHECK (type IN ('change_address', 'chequebook_request', 'kyc_update',
                                 'card_replacement', 'account_closure', 'dispute')),
    status       VARCHAR(20)  NOT NULL DEFAULT 'submitted'
                 CHECK (status IN ('submitted', 'processing', 'completed', 'rejected', 'cancelled')),
    details      JSONB        NOT NULL DEFAULT '{}',   -- flexible payload per request type
    notes        TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_sr_customer ON service_requests (customer_id);
CREATE INDEX idx_sr_status   ON service_requests (status);
CREATE INDEX idx_sr_type     ON service_requests (type);


-- ============================================================
--  INFRASTRUCTURE TABLES (session, observability, cost)
-- ============================================================

-- ── Sessions (conversation history + shared state) ───
CREATE TABLE sessions (
    session_id   VARCHAR(30)  PRIMARY KEY,
    customer_id  VARCHAR(20)  NOT NULL REFERENCES customers(customer_id),
    shared_state JSONB        NOT NULL DEFAULT '{}',   -- inter-agent context
    agent_context JSONB       NOT NULL DEFAULT '{}',   -- per-agent context
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_customer ON sessions (customer_id);
CREATE INDEX idx_sessions_active   ON sessions (is_active, last_activity DESC);


-- ── Conversation Messages ────────────────────────────
CREATE TABLE conversation_messages (
    message_id  SERIAL       PRIMARY KEY,
    session_id  VARCHAR(30)  NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role        VARCHAR(10)  NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT         NOT NULL,
    agent_used  VARCHAR(30),                     -- which agent generated this response
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_session ON conversation_messages (session_id, created_at);


-- ── Agent Traces (observability) ─────────────────────
CREATE TABLE agent_traces (
    trace_id      SERIAL       PRIMARY KEY,
    session_id    VARCHAR(30)  NOT NULL REFERENCES sessions(session_id),
    agent         VARCHAR(30)  NOT NULL,           -- coordinator, accounts_agent, etc.
    action        VARCHAR(50)  NOT NULL,           -- routing, balance_enquiry, etc.
    tool_calls    JSONB        NOT NULL DEFAULT '[]',
    input_tokens  INTEGER      NOT NULL DEFAULT 0,
    output_tokens INTEGER      NOT NULL DEFAULT 0,
    latency_ms    REAL         NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_traces_session ON agent_traces (session_id);
CREATE INDEX idx_traces_agent   ON agent_traces (agent, created_at DESC);
CREATE INDEX idx_traces_errors  ON agent_traces (error) WHERE error IS NOT NULL;


-- ── Cost Records ─────────────────────────────────────
CREATE TABLE cost_records (
    cost_id        SERIAL         PRIMARY KEY,
    session_id     VARCHAR(30)    NOT NULL REFERENCES sessions(session_id),
    model          VARCHAR(100)   NOT NULL,
    input_tokens   INTEGER        NOT NULL,
    output_tokens  INTEGER        NOT NULL,
    estimated_cost DECIMAL(10, 6) NOT NULL,       -- USD
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cost_session ON cost_records (session_id);
CREATE INDEX idx_cost_date    ON cost_records (created_at DESC);


-- ── PII Redaction Mappings (per session) ─────────────
CREATE TABLE pii_redaction_map (
    map_id      SERIAL       PRIMARY KEY,
    session_id  VARCHAR(30)  NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    placeholder VARCHAR(50)  NOT NULL,             -- [REDACTED_EMAIL_1]
    original    VARCHAR(500) NOT NULL,             -- the actual PII value
    pii_type    VARCHAR(20)  NOT NULL,             -- SSN, EMAIL, PHONE, etc.
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pii_session ON pii_redaction_map (session_id);


-- ── Audit Log (who did what, when) ───────────────────
CREATE TABLE audit_log (
    log_id       SERIAL       PRIMARY KEY,
    customer_id  VARCHAR(20),
    action       VARCHAR(50)  NOT NULL,            -- login, chat, address_change, etc.
    resource     VARCHAR(50),                      -- what was accessed/modified
    details      JSONB        NOT NULL DEFAULT '{}',
    ip_address   INET,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_customer ON audit_log (customer_id, created_at DESC);
CREATE INDEX idx_audit_action   ON audit_log (action, created_at DESC);


-- ============================================================
--  HELPER: auto-update updated_at columns
-- ============================================================

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_customers_updated
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_accounts_updated
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_service_requests_updated
    BEFORE UPDATE ON service_requests
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();


-- ============================================================
--  VIEWS (handy queries the agents/API will use often)
-- ============================================================

-- Customer's full profile with roles
CREATE VIEW v_customer_profile AS
SELECT
    c.customer_id,
    c.name,
    c.email,
    c.phone,
    c.address,
    c.kyc_status,
    c.is_active,
    ARRAY_AGG(r.role_name ORDER BY r.role_name) AS roles
FROM customers c
LEFT JOIN customer_roles cr ON c.customer_id = cr.customer_id
LEFT JOIN roles r ON cr.role_id = r.role_id
GROUP BY c.customer_id;


-- Account summary for a customer
CREATE VIEW v_account_summary AS
SELECT
    a.account_id,
    a.customer_id,
    c.name AS customer_name,
    a.type,
    a.balance,
    a.currency,
    a.status,
    a.opened_date,
    COUNT(t.transaction_id) AS total_transactions,
    MAX(t.transaction_date) AS last_transaction_date
FROM accounts a
JOIN customers c ON a.customer_id = c.customer_id
LEFT JOIN transactions t ON a.account_id = t.account_id
GROUP BY a.account_id, c.name;


-- Session cost summary
CREATE VIEW v_session_costs AS
SELECT
    cr.session_id,
    s.customer_id,
    COUNT(*)              AS total_calls,
    SUM(cr.input_tokens)  AS total_input_tokens,
    SUM(cr.output_tokens) AS total_output_tokens,
    SUM(cr.estimated_cost) AS total_cost_usd
FROM cost_records cr
JOIN sessions s ON cr.session_id = s.session_id
GROUP BY cr.session_id, s.customer_id;


-- ============================================================
--  SEED DATA
-- ============================================================

-- Roles
INSERT INTO roles (role_name, description) VALUES
    ('view_accounts',      'View account balances and details'),
    ('view_transactions',  'View transaction history and statements'),
    ('request_services',   'Submit service requests (address, chequebook, KYC)');

-- Customers (password is bcrypt hash of "demo123")
INSERT INTO customers (customer_id, name, email, phone, address, password_hash, kyc_status, kyc_last_updated) VALUES
    ('cust_001', 'Alice Johnson', 'alice.johnson@email.com', '+1-555-0101',
     '123 Main St, Springfield, IL 62701',
     '$2b$12$LJ3m4ys4Hz3YeiDqF3GNnuVpNfGqr0MXhqQk6B5bIcGddGaRZxKy2',   -- demo123
     'verified', '2024-06-15'),
    ('cust_002', 'Bob Smith', 'bob.smith@email.com', '+1-555-0102',
     '456 Oak Ave, Chicago, IL 60601',
     '$2b$12$LJ3m4ys4Hz3YeiDqF3GNnuVpNfGqr0MXhqQk6B5bIcGddGaRZxKy2',   -- demo123
     'pending', '2024-01-10');

-- Alice gets full access, Bob gets limited
INSERT INTO customer_roles (customer_id, role_id) VALUES
    ('cust_001', 1), ('cust_001', 2), ('cust_001', 3),  -- Alice: all roles
    ('cust_002', 1), ('cust_002', 2);                    -- Bob: no services

-- Accounts
INSERT INTO accounts (account_id, customer_id, type, balance, currency, status, opened_date) VALUES
    ('acc_1001', 'cust_001', 'savings',  15420.75, 'USD', 'active', '2020-03-15'),
    ('acc_1002', 'cust_001', 'checking',  3280.50, 'USD', 'active', '2019-11-01'),
    ('acc_2001', 'cust_002', 'savings',   8750.00, 'USD', 'active', '2022-07-20');

-- Transactions
INSERT INTO transactions (transaction_id, account_id, type, amount, balance_after, description, category, transaction_date) VALUES
    -- Alice's savings (acc_1001)
    ('txn_001', 'acc_1001', 'credit', 3500.00, 15420.75, 'Salary deposit',        'income',        '2024-08-25 09:00:00+00'),
    ('txn_002', 'acc_1001', 'debit',    85.50, 11920.75, 'Electric bill',          'utilities',     '2024-08-22 14:30:00+00'),
    ('txn_003', 'acc_1001', 'debit',    42.30, 11878.45, 'Grocery Store',          'groceries',     '2024-08-20 11:15:00+00'),
    ('txn_004', 'acc_1001', 'debit',   200.00, 11678.45, 'Transfer to checking',   'transfer',      '2024-08-18 16:00:00+00'),
    ('txn_005', 'acc_1001', 'credit',  150.00, 11828.45, 'Refund - Amazon',        'refund',        '2024-08-15 10:00:00+00'),

    -- Alice's checking (acc_1002)
    ('txn_006', 'acc_1002', 'debit',    55.00,  3225.50, 'Netflix + Spotify',      'entertainment', '2024-08-25 08:00:00+00'),
    ('txn_007', 'acc_1002', 'debit',   120.00,  3105.50, 'Gas station',            'transport',     '2024-08-23 17:45:00+00'),
    ('txn_008', 'acc_1002', 'credit',  200.00,  3305.50, 'Transfer from savings',  'transfer',      '2024-08-18 16:00:00+00'),

    -- Bob's savings (acc_2001)
    ('txn_009', 'acc_2001', 'credit', 4200.00,  8750.00, 'Salary deposit',         'income',        '2024-08-24 09:30:00+00'),
    ('txn_010', 'acc_2001', 'debit',  1200.00,  4550.00, 'Rent payment',           'housing',       '2024-08-20 12:00:00+00');


-- ============================================================
--  USEFUL QUERIES (reference for building your MCP tools)
-- ============================================================

-- Balance enquiry
-- SELECT account_id, type, balance, currency, status
-- FROM accounts WHERE account_id = 'acc_1001';

-- List customer accounts
-- SELECT account_id, type, balance, currency, status
-- FROM accounts WHERE customer_id = 'cust_001';

-- Recent transactions with optional category filter
-- SELECT transaction_id, type, amount, description, category, transaction_date
-- FROM transactions
-- WHERE account_id = 'acc_1001'
--   AND ($1 = '' OR category = $1)
-- ORDER BY transaction_date DESC
-- LIMIT $2;

-- Monthly statement
-- SELECT
--     COUNT(*) AS txn_count,
--     SUM(CASE WHEN type = 'credit' THEN amount ELSE 0 END) AS total_credits,
--     SUM(CASE WHEN type = 'debit'  THEN amount ELSE 0 END) AS total_debits
-- FROM transactions
-- WHERE account_id = 'acc_1001'
--   AND DATE_TRUNC('month', transaction_date) = DATE_TRUNC('month', $1::DATE);

-- Customer roles for authorisation
-- SELECT r.role_name
-- FROM customer_roles cr
-- JOIN roles r ON cr.role_id = r.role_id
-- WHERE cr.customer_id = 'cust_001';

-- Session cost report
-- SELECT * FROM v_session_costs WHERE session_id = 'sess_abc123';
