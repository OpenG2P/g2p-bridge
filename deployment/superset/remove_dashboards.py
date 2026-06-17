"""Remove ALL G2P Bridge Superset assets (dashboards, charts, datasets and the
g2p_bridge / spar / example_bank connections) from Superset. Run inside the
Superset pod when permanently decommissioning the bridge:
  python remove_dashboards.py

Targeted strictly to the bridge's own databases — it does not touch any other
Superset content. Idempotent (safe if some assets are already gone).
"""
from superset.app import create_app

app = create_app()
with app.app_context():
    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    # 1. Dashboards (slug g2p-bridge-*)
    for d in db.session.query(Dashboard).filter(Dashboard.slug.like("g2p-bridge%")).all():
        print("delete dashboard:", d.slug)
        db.session.delete(d)
    db.session.commit()

    # 2. For each bridge connection: its charts -> datasets -> the database.
    for name in ["g2p_bridge", "spar", "example_bank"]:
        database = db.session.query(Database).filter_by(database_name=name).first()
        if not database:
            continue
        tables = db.session.query(SqlaTable).filter_by(database_id=database.id).all()
        tids = [t.id for t in tables]
        if tids:
            for s in (
                db.session.query(Slice)
                .filter(Slice.datasource_id.in_(tids), Slice.datasource_type == "table")
                .all()
            ):
                print("delete chart:", s.slice_name)
                db.session.delete(s)
            db.session.commit()
        for t in tables:
            print("delete dataset:", t.table_name)
            db.session.delete(t)
        db.session.commit()
        print("delete connection:", name)
        db.session.delete(database)
        db.session.commit()

    print("OK — G2P Bridge Superset assets removed")
