from fastapi import APIRouter, Depends, HTTPException
from app.database import execute, fetch_all
from app.models.schemas import ResultsResponse
from app.routers.analysis import _assert_analysis_owner, analysis_store
from app.routers.auth import get_current_user
from app.services.risk_model import generate_guidance

router = APIRouter()


@router.get("/history")
async def get_results_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    rows = fetch_all(
        """
        SELECT ar.id, ar.result_payload, ar.created_at
        FROM analysis_results ar
        JOIN audio_files af ON af.id = ar.audio_file_id
        WHERE af.user_id = CAST(:user_id AS uuid)
        ORDER BY ar.created_at DESC
        LIMIT :limit
        """,
        {
            "user_id": current_user["user_id"],
            "limit": max(1, min(int(limit or 10), 50)),
        },
    )
    items = []
    for row in rows:
        payload = row["result_payload"]
        analysis = payload if isinstance(payload, dict) else {}
        items.append({
            "analysis": analysis,
            "verification_type": analysis.get("verification_type") or "parent_call",
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "saved_at": row["created_at"].isoformat() if row.get("created_at") else None,
        })
    return {"items": items}


@router.get("/{analysis_id}", response_model=ResultsResponse)
async def get_results(analysis_id: str, current_user: dict = Depends(get_current_user)):
    stored = _assert_analysis_owner(analysis_id, current_user)
    if not stored:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")

    risk_level = getattr(stored["risk_level"], "value", stored["risk_level"])

    guidance_data = generate_guidance(
        risk_level=risk_level,
        risk_score=stored["risk_score"],
        confidence_score=stored["confidence_score"],
    )

    return ResultsResponse(
        analysis=stored,
        guidance=guidance_data["guidance"],
        risk_explanation=guidance_data["risk_explanation"],
        next_steps=guidance_data["next_steps"],
        legal_notice=guidance_data["legal_notice"],
    )


@router.get("/{analysis_id}/summary")
async def get_results_summary(analysis_id: str, current_user: dict = Depends(get_current_user)):
    stored = _assert_analysis_owner(analysis_id, current_user)
    if not stored:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")

    risk_level = getattr(stored["risk_level"], "value", stored["risk_level"])

    guidance_data = generate_guidance(
        risk_level=risk_level,
        risk_score=stored["risk_score"],
        confidence_score=stored["confidence_score"],
    )

    risk_level_kr = {
        "low": "낮음",
        "middle": "중간",
        "high": "높음",
    }

    return {
        "analysis_id": analysis_id,
        "cognitive_status": stored["cognitive_status"],
        "cognitive_status_label": stored["cognitive_status_label"],
        "dementia_stage": stored["dementia_stage"],
        "risk_score": stored["risk_score"],
        "risk_level": risk_level,
        "risk_level_label": risk_level_kr.get(risk_level, risk_level),
        "model_probabilities": stored["model_probabilities"],
        "result_message": stored["result_message"],
        "confidence_score": stored["confidence_score"],
        "processing_time_seconds": stored["processing_time_seconds"],
        "risk_explanation": guidance_data["risk_explanation"],
        "top_guidance": guidance_data["guidance"][:3] if guidance_data["guidance"] else [],
        "disclaimer": stored["disclaimer"],
    }


@router.delete("/{analysis_id}")
async def delete_result_history_item(analysis_id: str, current_user: dict = Depends(get_current_user)):
    stored = _assert_analysis_owner(analysis_id, current_user)
    if not stored:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")

    execute(
        """
        DELETE FROM analysis_results
        WHERE id = CAST(:analysis_id AS uuid)
        """,
        {"analysis_id": analysis_id},
    )
    analysis_store.pop(analysis_id, None)
    return {
        "analysis_id": analysis_id,
        "message": "분석 이력이 삭제되었습니다.",
    }
