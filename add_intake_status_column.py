#!/usr/bin/env python3
"""
Add intake_status column to intake_items table
"""
import os
import sys
from factory_shipping import create_app
from factory_shipping.extensions import db

def add_column():
    app = create_app()

    with app.app_context():
        try:
            # Check if column already exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('intake_items')]

            if 'intake_status' in columns:
                print("Column 'intake_status' already exists. Skipping.")
                return

            # Add the column
            from sqlalchemy import text
            sql = text("""
            ALTER TABLE intake_items
            ADD COLUMN intake_status VARCHAR(20) NOT NULL DEFAULT '通常' AFTER shipped_at,
            ADD INDEX idx_intake_status (intake_status)
            """)

            with db.engine.connect() as conn:
                conn.execute(sql)
                conn.commit()
            print("Successfully added intake_status column to intake_items table")

        except Exception as e:
            print(f"Error adding column: {e}")
            sys.exit(1)

if __name__ == '__main__':
    add_column()
