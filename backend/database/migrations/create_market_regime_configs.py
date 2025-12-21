#!/usr/bin/env python3
"""
Migration: Create Market Regime Configs Table
- market_regime_configs: Configuration for Market Regime classification thresholds
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from database.connection import DATABASE_URL


def migrate():
    """Create market_regime_configs table with idempotency"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'market_regime_configs'
            )
        """))
        table_exists = result.scalar()

        if table_exists:
            print("market_regime_configs table already exists, skipping creation")
        else:
            # Create table
            conn.execute(text("""
                CREATE TABLE market_regime_configs (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    is_default BOOLEAN DEFAULT false,
                    rolling_window INTEGER DEFAULT 48,
                    breakout_cvd_z FLOAT DEFAULT 1.5,
                    breakout_oi_z FLOAT DEFAULT 1.0,
                    breakout_price_atr FLOAT DEFAULT 0.5,
                    breakout_taker_high FLOAT DEFAULT 1.8,
                    breakout_taker_low FLOAT DEFAULT 0.55,
                    absorption_cvd_z FLOAT DEFAULT 1.5,
                    absorption_price_atr FLOAT DEFAULT 0.3,
                    trap_cvd_z FLOAT DEFAULT 1.0,
                    trap_oi_z FLOAT DEFAULT -1.0,
                    exhaustion_cvd_z FLOAT DEFAULT 1.0,
                    exhaustion_rsi_high FLOAT DEFAULT 70.0,
                    exhaustion_rsi_low FLOAT DEFAULT 30.0,
                    stop_hunt_range_atr FLOAT DEFAULT 1.0,
                    stop_hunt_close_atr FLOAT DEFAULT 0.3,
                    noise_cvd_z FLOAT DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("market_regime_configs table created")

        # Check if default config exists, insert if not (idempotent)
        result = conn.execute(text("""
            SELECT COUNT(*) FROM market_regime_configs WHERE is_default = true
        """))
        default_exists = result.scalar() > 0

        if not default_exists:
            conn.execute(text("""
                INSERT INTO market_regime_configs (
                    name, is_default, rolling_window,
                    breakout_cvd_z, breakout_oi_z, breakout_price_atr,
                    breakout_taker_high, breakout_taker_low,
                    absorption_cvd_z, absorption_price_atr,
                    trap_cvd_z, trap_oi_z,
                    exhaustion_cvd_z, exhaustion_rsi_high, exhaustion_rsi_low,
                    stop_hunt_range_atr, stop_hunt_close_atr, noise_cvd_z
                ) VALUES (
                    'Default', true, 48,
                    1.5, 1.0, 0.5, 1.8, 0.55,
                    1.5, 0.3,
                    1.0, -1.0,
                    1.0, 70.0, 30.0,
                    1.0, 0.3, 0.5
                )
            """))
            print("Default config inserted")

        conn.commit()
        print("Market Regime configs migration completed")


def upgrade():
    """Entry point for migration manager"""
    migrate()


if __name__ == "__main__":
    migrate()
