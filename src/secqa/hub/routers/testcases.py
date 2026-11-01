from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..deps import DB, Actor, get_or_404, project_by_key
from ..models import AuditLog, Run, TestCase, TestCaseStatus, TestResult, TestType, utcnow
from ..schemas import Page, TestCaseCreate, TestCaseOut, TestCaseUpdate, TestResultOut

router = APIRouter(tags=["test cases"])


def _with_last_result(db: Session, cases: list[TestCase]) -> list[TestCaseOut]:
    if not cases:
        return []
    latest = (
        select(TestResult.test_case_id, func.max(TestResult.id).label("rid"))
        .where(TestResult.test_case_id.in_([c.id for c in cases]))
        .group_by(TestResult.test_case_id)
        .subquery()
    )
    last = {tc_id: (status_, run_id) for tc_id, status_, run_id in db.execute(
        select(TestResult.test_case_id, TestResult.status, TestResult.run_id)
        .join(latest, TestResult.id == latest.c.rid)
    ).all()}
    out = []
    for c in cases:
        st, run_id = last.get(c.id, (None, None))
        out.append(TestCaseOut.model_validate(c).model_copy(update={"last_status": st, "last_run_id": run_id}))
    return out


@router.get("/testcases", response_model=Page[TestCaseOut])
def list_testcases(
    db: DB,
    project: str | None = None,
    type_: TestType | None = Query(None, alias="type"),
    suite: str | None = None,
    status_: TestCaseStatus | None = Query(None, alias="status"),
    q: str | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    stmt = select(TestCase)
    if project:
        stmt = stmt.where(TestCase.project_id == project_by_key(db, project).id)
    if type_:
        stmt = stmt.where(TestCase.type == type_)
    if suite:
        stmt = stmt.where(TestCase.suite == suite)
    if status_:
        stmt = stmt.where(TestCase.status == status_)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(TestCase.title.ilike(like), TestCase.key.ilike(like),
                              TestCase.description.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    cases = db.scalars(stmt.order_by(TestCase.suite, TestCase.id).limit(limit).offset(offset)).all()
    return Page(items=_with_last_result(db, list(cases)), total=total or 0, limit=limit, offset=offset)


@router.post("/projects/{key}/testcases", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED)
def create_testcase(key: str, body: TestCaseCreate, db: DB, actor: Actor):
    project = project_by_key(db, key)
    project.testcase_seq += 1
    tc = TestCase(project_id=project.id, key=f"{project.key}-TC-{project.testcase_seq}",
                  **body.model_dump(exclude={"steps"}), steps=[s.model_dump() for s in body.steps])
    db.add(tc)
    db.flush()
    db.add(AuditLog(project_id=project.id, actor=actor, action=f"created test case {tc.key}"))
    db.commit()
    return _with_last_result(db, [tc])[0]


@router.get("/testcases/{tc_id}", response_model=TestCaseOut)
def get_testcase(tc_id: int, db: DB):
    return _with_last_result(db, [get_or_404(db, TestCase, tc_id)])[0]


@router.patch("/testcases/{tc_id}", response_model=TestCaseOut)
def update_testcase(tc_id: int, body: TestCaseUpdate, db: DB):
    tc = get_or_404(db, TestCase, tc_id)
    changes = body.model_dump(exclude_unset=True)
    if "steps" in changes and changes["steps"] is not None:
        changes["steps"] = [dict(s) for s in changes["steps"]]
    for field, value in changes.items():
        setattr(tc, field, value)
    tc.updated_at = utcnow()
    db.commit()
    return _with_last_result(db, [tc])[0]


@router.delete("/testcases/{tc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_testcase(tc_id: int, db: DB):
    db.delete(get_or_404(db, TestCase, tc_id))
    db.commit()


@router.get("/testcases/{tc_id}/history", response_model=list[TestResultOut])
def testcase_history(tc_id: int, db: DB, limit: int = 50):
    tc = get_or_404(db, TestCase, tc_id)
    rows = db.scalars(
        select(TestResult).join(Run).where(TestResult.test_case_id == tc.id)
        .order_by(TestResult.id.desc()).limit(min(limit, 500))
    ).all()
    return [TestResultOut.model_validate(r).model_copy(update={"test_case_key": tc.key}) for r in rows]
