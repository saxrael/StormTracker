import datetime


def generate_text_ledger(
    submissions: list[dict],
    defaulters: list[dict],
    date_label: datetime.date | str,
) -> str:
    display_date = (
        date_label.strftime("%Y-%m-%d")
        if isinstance(date_label, datetime.date)
        else str(date_label)
    )
    lines = [f"StormTracker Daily Analytics - {display_date}", ""]

    lines.append("### Defaulters")
    if not defaulters:
        lines.append("None. Everyone submitted!")
    else:
        for d in defaulters:
            display = (
                d.get("full_name") or d.get("username") or f"ID:{d.get('telegram_id')}"
            )
            lines.append(f"- {display}")

    lines.append("")
    lines.append("### Detailed Submissions")
    if not submissions:
        lines.append("No submissions found for today.")
    else:
        for sub in submissions:
            display = (
                sub.get("full_name")
                or sub.get("username")
                or f"ID:{sub.get('telegram_id')}"
            )
            lines.append(
                f"- **{display}** - {sub.get('exercise_type')}: "
                f"{sub.get('overall_score_percentage')}% "
                f"(Questions: {sub.get('total_correct')}/{sub.get('total_questions')})"
            )
            details = sub.get("granular_details", [])
            if details:
                details_str = ", ".join(
                    [f"{d['item_name']}: {d['accuracy_percentage']}%" for d in details]
                )
                lines.append(f"  Details: {details_str}")

    return "\n".join(lines)
