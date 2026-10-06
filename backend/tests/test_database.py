import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Analysis
from tests.helpers import SESSION_A


def make_row(**overrides) -> Analysis:
    data = dict(
        session_id=SESSION_A,
        log_input="log text",
        category="Docker",
        summary="s",
        severity="HIGH",
        root_cause="r",
        affected_component="c",
        evidence=["e1", "e2"],
        recommended_fix=["f"],
        commands=["cmd"],
        prevention=["p"],
        devops_insight="i",
        confidence=0.9,
        ai_model="m",
    )
    data.update(overrides)
    return Analysis(**data)


def test_row_round_trip_keeps_json_lists():
    with SessionLocal() as db:
        row = make_row()
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.id is not None
        assert row.created_at is not None
        assert row.evidence == ["e1", "e2"]
        assert row.commands == ["cmd"]


@pytest.mark.parametrize(
    "override",
    [{"severity": "BANANA"}, {"confidence": 1.5}, {"confidence": -0.1}],
)
def test_database_constraints_reject_bad_values(override):
    with SessionLocal() as db:
        db.add(make_row(**override))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
