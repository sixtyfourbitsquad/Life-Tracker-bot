from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime, timedelta
import os

from fpdf import FPDF

from .db import Database
from .utils import tz_offset_minutes, local_date_str


def _minutes_to_hhmm(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def _hm_from_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


async def generate_user_report_pdf(db: Database, user_id: int, tz_name: str, days: int, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    user = await db.get_user(user_id) or {}
    target_ml = int(user.get("daily_water_target_ml", 4000))
    cup_ml = int(user.get("cup_size_ml", 250))
    wake_m = user.get("wake_time_minutes")
    sleep_m = user.get("sleep_time_minutes")

    tz_off = tz_offset_minutes(tz_name)
    today_local = datetime.fromisoformat(local_date_str(tz_name)).date()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    
    def _try_add_unicode_fonts(p: FPDF) -> str | None:
        # Allow manual override
        reg = os.environ.get("PDF_FONT_REGULAR")
        bold = os.environ.get("PDF_FONT_BOLD")
        if reg and os.path.exists(reg):
            try:
                p.add_font("DejaVu", "", reg, uni=True)
                if bold and os.path.exists(bold):
                    p.add_font("DejaVu", "B", bold, uni=True)
                else:
                    # Use regular for bold if bold file not provided
                    p.add_font("DejaVu", "B", reg, uni=True)
                return "DejaVu"
            except Exception:
                pass
        # Common system paths
        candidates = [
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
             "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]
        for reg_path, bold_path in candidates:
            if os.path.exists(reg_path):
                try:
                    p.add_font("DejaVu", "", reg_path, uni=True)
                    if os.path.exists(bold_path):
                        p.add_font("DejaVu", "B", bold_path, uni=True)
                    else:
                        p.add_font("DejaVu", "B", reg_path, uni=True)
                    return "DejaVu"
                except Exception:
                    continue
        return None

    unicode_font = _try_add_unicode_fonts(pdf)

    def safe(text: str) -> str:
        if unicode_font:
            return text
        # Replace common non-ASCII chars if Unicode font not available
        return (
            text.replace("—", "-")
                .replace("–", "-")
                .replace("“", '"')
                .replace("”", '"')
                .replace("’", "'")
        )

    if unicode_font:
        pdf.set_font(unicode_font, "B", 16)
    else:
        pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, safe("LifeTrack Pro — Daily Summary Report"), ln=1)

    if unicode_font:
        pdf.set_font(unicode_font, size=11)
    else:
        pdf.set_font("Helvetica", size=11)
    pdf.ln(2)

    # Compute quick summary over range
    days_list = [(today_local - timedelta(days=i)).isoformat() for i in range(days)]
    total_water_sum = 0
    days_meet_target = 0
    ex_days = 0
    ret_days = 0
    sleep_minutes_sum = 0
    sleep_days_count = 0
    screen_minutes_sum = 0
    for d in days_list:
        tw = await db.get_water_total_for_date(user_id, d, tz_off)
        total_water_sum += tw
        summary = await db.get_day_summary(user_id, d)
        tgt = int(summary.get("water_target_ml", target_ml))
        if tgt and tw >= tgt:
            days_meet_target += 1
        if summary.get("did_exercise"):
            ex_days += 1
        if summary.get("did_retain"):
            ret_days += 1
        sm = summary.get("sleep_minutes")
        if sm is not None:
            sleep_minutes_sum += int(sm)
            sleep_days_count += 1
        screen_minutes_sum += int(summary.get("screen_time_minutes", 0))

    avg_water = int(round(total_water_sum / max(1, len(days_list))))
    avg_sleep = int(round(sleep_minutes_sum / max(1, sleep_days_count))) if sleep_days_count else None
    avg_screen = int(round(screen_minutes_sum / max(1, len(days_list))))

    info_lines = [
        ("User ID", str(user_id)),
        ("Time Zone", tz_name),
        ("Daily Water Target (ml)", str(target_ml)),
        ("Cup Size (ml)", str(cup_ml)),
        ("Wake Time", _hm_from_minutes(wake_m)),
        ("Sleep Time", _hm_from_minutes(sleep_m)),
        ("Report Range", f"Last {days} days (ending {today_local.isoformat()})"),
        ("Avg Water (ml)", str(avg_water)),
        ("Days Met Target", f"{days_meet_target}/{len(days_list)}"),
        ("Exercise Days", str(ex_days)),
        ("Retention Days", str(ret_days)),
        ("Avg Sleep (h:mm)", _minutes_to_hhmm(avg_sleep)),
        ("Avg Screen (min)", str(avg_screen)),
    ]
    for k, v in info_lines:
        pdf.cell(60, 7, safe(f"{k}"))
        pdf.cell(0, 7, safe(v), ln=1)

    pdf.ln(3)
    # Table header
    headers = ["Date", "Water (ml/%target)", "Exercise", "Retention", "Sleep", "Screen(min)", "Activities"]
    col_widths = [28, 45, 28, 28, 28, 28, 70]
    if unicode_font:
        pdf.set_font(unicode_font, "B", 11)
    else:
        pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(230, 230, 230)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, safe(h), border=1, fill=True)
    pdf.ln(8)

    if unicode_font:
        pdf.set_font(unicode_font, size=10)
    else:
        pdf.set_font("Helvetica", size=10)

    def draw_header():
        if unicode_font:
            pdf.set_font(unicode_font, "B", 11)
        else:
            pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(230, 230, 230)
        for h, w in zip(headers, col_widths):
            pdf.cell(w, 8, safe(h), border=1, fill=True)
        pdf.ln(8)
        if unicode_font:
            pdf.set_font(unicode_font, size=10)
        else:
            pdf.set_font("Helvetica", size=10)

    fill_toggle = False
    for i in range(days):
        d = (today_local - timedelta(days=i)).isoformat()
        total_water = await db.get_water_total_for_date(user_id, d, tz_off)
        summary = await db.get_day_summary(user_id, d)
        day_target = int(summary.get("water_target_ml", target_ml))
        percent = int(round((total_water / day_target) * 100)) if day_target else 0
        did_ex = "Yes" if summary.get("did_exercise") else "No"
        did_ret = "Yes" if summary.get("did_retain") else "No"
        sleep_min = summary.get("sleep_minutes")
        sleep_str = _minutes_to_hhmm(sleep_min)
        screen_min = int(summary.get("screen_time_minutes", 0))
        acts = summary.get("activities") or []
        acts_str = "; ".join([a if not b else f"{a}: {b}" for a, b in acts]) or "-"

        # Compute row height based on activities wrapping
        lines = pdf.multi_cell(col_widths[-1], 7, safe(acts_str), split_only=True)
        row_h = max(7, 7 * len(lines))

        # Page break check
        if pdf.will_page_break(row_h):
            pdf.add_page()
            # Reprint title small and header
            if unicode_font:
                pdf.set_font(unicode_font, "B", 12)
            else:
                pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, safe("LifeTrack Pro — Daily Summary Report (cont.)"), ln=1)
            draw_header()

        # Row fill color
        if fill_toggle:
            pdf.set_fill_color(246, 246, 246)
        else:
            pdf.set_fill_color(255, 255, 255)
        fill_toggle = not fill_toggle

        start_x = pdf.get_x()
        start_y = pdf.get_y()

        cells = [
            d,
            f"{total_water} ({percent}%)",
            did_ex,
            did_ret,
            sleep_str,
            str(screen_min),
        ]
        # Draw fixed-height cells
        for idx, (val, w) in enumerate(zip(cells, col_widths[:-1])):
            align = "R" if idx in (1, 5) else "L"
            pdf.cell(w, row_h, safe(str(val)), border=1, fill=True, align=align)

        # Draw activities as wrapped cell
        pdf.set_xy(start_x + sum(col_widths[:-1]), start_y)
        pdf.multi_cell(col_widths[-1], 7, safe(acts_str), border=1, fill=True)

        # Move to next row baseline
        pdf.set_xy(start_x, start_y + row_h)

    pdf.output(out_path)
    return out_path


