"""
Database migration script: create the Threat <-> Asset link table and backfill historical data.
Run: python -m app.scripts.migrate_threat_asset_links
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text, create_engine
from app.core.config import settings


def _build_pg8000_url() -> str:
    if settings.database_url.startswith("postgresql+asyncpg://"):
        return settings.database_url.replace("postgresql+asyncpg://", "postgresql+pg8000://", 1)
    if settings.sync_database_url.startswith("postgresql+psycopg2://"):
        return settings.sync_database_url.replace("postgresql+psycopg2://", "postgresql+pg8000://", 1)
    return settings.sync_database_url


engine = create_engine(_build_pg8000_url(), future=True)


ALTER_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS threat_asset_links (
        threat_id VARCHAR(36) NOT NULL REFERENCES threats(id) ON DELETE CASCADE,
        asset_id VARCHAR(36) NOT NULL REFERENCES toe_assets(id) ON DELETE CASCADE,
        PRIMARY KEY (threat_id, asset_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_threat_asset_links_threat_id ON threat_asset_links (threat_id)",
    "CREATE INDEX IF NOT EXISTS idx_threat_asset_links_asset_id ON threat_asset_links (asset_id)",
]


def run_migration():
    print("=== Threat Asset Links Migration ===")
    with engine.begin() as conn:
        for stmt in ALTER_STATEMENTS:
            sql = " ".join(stmt.split())
            print(f"Executing: {sql}")
            conn.execute(text(stmt))
    backfill_links()
    print("\n[OK] Migration complete.")


def backfill_links():
    print("Starting backfill for historical Threat <-> Asset links...")
    with engine.begin() as conn:
        asset_rows = conn.execute(text("""
            SELECT id, toe_id, name
            FROM toe_assets
            WHERE deleted_at IS NULL
        """)).mappings().all()
        threat_rows = conn.execute(text("""
            SELECT id, toe_id, assets_affected, adverse_action, threat_agent
            FROM threats
            WHERE deleted_at IS NULL
        """)).mappings().all()
        existing_links = conn.execute(text("SELECT threat_id, asset_id FROM threat_asset_links")).mappings().all()

        asset_map: dict[str, list[dict]] = {}
        for asset in asset_rows:
            asset_map.setdefault(asset["toe_id"], []).append(asset)

        linked_pairs = {(item["threat_id"], item["asset_id"]) for item in existing_links}
        linked_threat_ids = {item["threat_id"] for item in existing_links}
        inserted = 0

        for threat in threat_rows:
            if threat["id"] in linked_threat_ids:
                continue
            toe_assets = asset_map.get(threat["toe_id"], [])
            if not toe_assets:
                continue

            text_blob = _normalize_text(" ".join([
                threat["assets_affected"] or "",
                threat["adverse_action"] or "",
                threat["threat_agent"] or "",
            ]))
            if not text_blob:
                continue

            for asset in toe_assets:
                matched = any(term and term in text_blob for term in _build_asset_search_terms(asset["name"]))
                if not matched:
                    continue
                pair = (threat["id"], asset["id"])
                if pair in linked_pairs:
                    continue
                conn.execute(
                    text("INSERT INTO threat_asset_links (threat_id, asset_id) VALUES (:threat_id, :asset_id)"),
                    {"threat_id": threat["id"], "asset_id": asset["id"]},
                )
                linked_pairs.add(pair)
                inserted += 1

    print(f"Backfill complete: inserted {inserted} Threat <-> Asset links")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _build_asset_search_terms(name: str) -> list[str]:
    normalized = _normalize_text(name)
    terms = [normalized] if normalized else []
    for token in re.split(r"[^a-zA-Z0-9_./-]+", normalized):
        if len(token) >= 3 and token not in terms:
            terms.append(token)
    return terms


if __name__ == "__main__":
    run_migration()