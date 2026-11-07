def enqueue_analysis(analysis_id: str) -> None:
    """Enfileira usando o id da análise como task_id do Celery."""
    from app.worker import analyze_candidate

    analyze_candidate.apply_async(args=[analysis_id], task_id=analysis_id)
