COLORS = {"OK":"GREEN", "WARNING":"ORANGE", "CRITICAL":"RED", "UNKNOWN":"GRAY"}


def reviewed_result(original: dict, review: dict | None) -> dict:
    if review is None:
        return original
    result = {**original, "original_result":original, "latest_review":review,
              "status":review["status"], "color":COLORS[review["status"]], "review_status":review["decision"],
              "confidence":None, "box":None}
    if review["status"] in ("OK", "UNKNOWN"):
        result.update(defect_id=None, defect_code=None, defect="Норма" if review["status"] == "OK" else "Не удалось определить",
                      recommendation="Решение инженера: " + review["comment"])
    return result


def valid_review(decision: str, status: str, comment: str) -> bool:
    return bool(comment.strip() and ((decision == "CONFIRMED" and status in ("OK", "WARNING", "CRITICAL"))
                                    or (decision == "REJECTED" and status == "UNKNOWN")))
