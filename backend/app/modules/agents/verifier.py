from fastapi import HTTPException, status

from app.modules.agents.schemas import IntegrationRunAdvisorOutput


def verify_integration_run_advisor_output(output: IntegrationRunAdvisorOutput) -> None:
    counts = output.counts
    if counts.total != counts.valid + counts.invalid + counts.conflicts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if any(issue.category not in {"INVALID", "CONFLICT", "FAILED"} for issue in output.issues):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.provenance.source_sha256 != output.evidence_refs[0].provenance_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.evidence_refs[0].source_entity_id != output.run_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
