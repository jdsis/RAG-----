import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import ensure_user_knowledge_base, get_current_user
from app.models import EvaluationResult, User
from app.schemas import EvaluationRunRequest
from app.services.rag_service import NO_ANSWER, retrieve_chunks

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/run")
def run_evaluation(
    payload: EvaluationRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_user_knowledge_base(db, current_user, payload.knowledge_base_id)
    results = []
    for case in payload.cases:
        started = time.time()
        chunks = retrieve_chunks(db, current_user, payload.knowledge_base_id, case.question)
        joined = "\n".join(chunk.content for chunk in chunks)
        hit = all(keyword in joined for keyword in case.expected_keywords) if case.expected_keywords else bool(chunks)
        no_answer = not chunks
        result = EvaluationResult(
            user_id=current_user.id,
            knowledge_base_id=payload.knowledge_base_id,
            test_question=case.question,
            expected_keywords=",".join(case.expected_keywords),
            actual_answer=NO_ANSWER if no_answer else joined[:1000],
            hit=hit,
            response_time_ms=int((time.time() - started) * 1000),
            no_answer=no_answer,
        )
        db.add(result)
        results.append({"question": case.question, "hit": hit, "no_answer": no_answer})
    db.commit()
    total = len(results) or 1
    return {
        "total": len(results),
        "hit_rate": sum(1 for item in results if item["hit"]) / total,
        "no_answer_rate": sum(1 for item in results if item["no_answer"]) / total,
        "results": results,
    }
