import matplotlib

matplotlib.use("Agg")
import datetime
import os
import tempfile
from collections import defaultdict

import matplotlib.pyplot as plt
from fpdf import FPDF


def generate_pdf_report(
    submissions: list[dict], defaulters: list[dict], target_date: datetime.date
) -> str:
    scores_by_user = defaultdict(list)
    scores_by_type = defaultdict(list)
    for sub in submissions:
        display = (
            sub.get("full_name")
            or sub.get("username")
            or f"ID:{sub.get('telegram_id')}"
        )
        score = sub.get("overall_score_percentage", 0)
        scores_by_user[display].append(score)
        extype = sub.get("exercise_type", "Unknown")
        scores_by_type[extype].append(score)

    avg_by_user = {k: sum(v) / len(v) for k, v in scores_by_user.items()}
    avg_by_type = {k: sum(v) / len(v) for k, v in scores_by_type.items()}

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp1:
        chart1_path = tmp1.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp2:
        chart2_path = tmp2.name

    if avg_by_user:
        fig, ax = plt.subplots(figsize=(8, max(3, len(avg_by_user) * 0.5)))
        names = list(avg_by_user.keys())
        scores = list(avg_by_user.values())
        bars = ax.barh(names, scores, color="#4A90D9")
        ax.set_xlim(0, 100)
        ax.set_xlabel("Average Score (%)")
        ax.set_title("Leaderboard — Average Score by Student")
        for bar, score in zip(bars, scores):
            ax.text(
                bar.get_width() + 1,
                bar.get_y() + bar.get_height() / 2,
                f"{score:.1f}%",
                va="center",
                fontsize=9,
            )
        plt.tight_layout()
        plt.savefig(chart1_path, dpi=150)
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No Data Available", ha="center", va="center", fontsize=14)
        ax.set_axis_off()
        plt.savefig(chart1_path, dpi=150)
        plt.close(fig)

    if avg_by_type:
        fig, ax = plt.subplots(figsize=(7, 4))
        types = list(avg_by_type.keys())
        scores = list(avg_by_type.values())
        bars = ax.bar(types, scores, color="#5CB85C")
        ax.set_ylim(0, 100)
        ax.set_ylabel("Average Score (%)")
        ax.set_title("Performance by Exercise Type")
        for bar, score in zip(bars, scores):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{score:.1f}%",
                ha="center",
                fontsize=9,
            )
        plt.tight_layout()
        plt.savefig(chart2_path, dpi=150)
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No Data Available", ha="center", va="center", fontsize=14)
        ax.set_axis_off()
        plt.savefig(chart2_path, dpi=150)
        plt.close(fig)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16, style="B")
    pdf.cell(
        0,
        10,
        txt=f"StormTracker Daily Analytics - {target_date.strftime('%Y-%m-%d')}",
        ln=True,
        align="C",
    )
    pdf.ln(5)

    pdf.set_font("Arial", size=13, style="B")
    pdf.cell(0, 8, txt="Leaderboard", ln=True)
    pdf.image(chart1_path, w=190)
    pdf.ln(5)

    pdf.set_font("Arial", size=13, style="B")
    pdf.cell(0, 8, txt="Performance by Exercise Type", ln=True)
    pdf.image(chart2_path, w=190)
    pdf.ln(5)

    pdf.add_page()

    pdf.set_font("Arial", size=14, style="B")
    pdf.cell(0, 10, txt="Defaulters", ln=True)
    pdf.set_font("Arial", size=12)
    if not defaulters:
        pdf.cell(0, 10, txt="None. Everyone submitted!", ln=True)
    else:
        for d in defaulters:
            display = (
                d.get("full_name") or d.get("username") or f"ID:{d.get('telegram_id')}"
            )
            pdf.cell(0, 10, txt=f"- {display}", ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", size=14, style="B")
    pdf.cell(0, 10, txt="Detailed Submissions", ln=True)
    pdf.set_font("Arial", size=12)

    if not submissions:
        pdf.cell(0, 10, txt="No submissions found for today.", ln=True)
    else:
        for sub in submissions:
            display = (
                sub.get("full_name")
                or sub.get("username")
                or f"ID:{sub.get('telegram_id')}"
            )
            line1 = (
                f"{display} - {sub.get('exercise_type')}: "
                f"{sub.get('overall_score_percentage')}% "
                f"({sub.get('total_correct')}/{sub.get('total_questions')})"
            )
            pdf.cell(0, 8, txt=line1, ln=True)
            details = sub.get("granular_details", [])
            if details:
                details_str = ", ".join(
                    [f"{d['item_name']}: {d['accuracy_percentage']}%" for d in details]
                )
                pdf.set_font("Arial", size=10, style="I")
                pdf.multi_cell(0, 6, txt=f"  Details: {details_str}")
                pdf.set_font("Arial", size=12, style="")

    os.remove(chart1_path)
    os.remove(chart2_path)

    filename = f"StormTracker_Report_{target_date.strftime('%Y-%m-%d')}.pdf"
    pdf_path = os.path.join(tempfile.gettempdir(), filename)

    pdf.output(pdf_path)

    return pdf_path
