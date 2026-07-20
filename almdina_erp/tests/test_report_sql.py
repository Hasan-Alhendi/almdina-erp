from types import SimpleNamespace

from almdina_erp.almdina_erp.report.factory_operations_summary import factory_operations_summary as report


def test_factory_operations_summary_uses_order_alias_for_date_filters(monkeypatch):
    queries = []

    def fake_sql(query, values=None, as_dict=False, **kwargs):
        queries.append(query)
        if "group by" in query.lower():
            return []
        return [SimpleNamespace(
            full_boards=0,
            source_area=0,
            used_area=0,
            waste_area=0,
            reusable_area=0,
            scrap_area=0,
            planned_cost=0,
            actual_cost=0,
            material_variance=0,
            internal_loss=0,
        )]

    monkeypatch.setattr(report.frappe.db, "sql", fake_sql)
    monkeypatch.setattr(report.frappe.db, "count", lambda *args, **kwargs: 0)

    report.execute({"from_date": "2026-01-01", "to_date": "2026-12-31"})
    assert queries
    status_query = queries[0].lower()
    assert "from `tabdoor cutting order` o" in status_query
    assert "o.order_date >=" in status_query
    assert "o.order_date <=" in status_query
