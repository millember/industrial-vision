NOTIFICATION_ROLES = ("MASTER", "ENGINEER")
REPORT_READER_ROLES = ("MASTER", "ENGINEER", "HEAD", "ADMIN")


def can_report(processing_status: str, result: dict | None) -> bool:
    return bool(processing_status == "COMPLETED" and result
                and result.get("status") in ("WARNING", "CRITICAL")
                and result.get("review_status") in ("UNREVIEWED", "CONFIRMED")
                and result.get("analysis_source") in ("MOCK", "MODEL")
                and type(result.get("defect_id")) is int and result["defect_id"] > 0)
