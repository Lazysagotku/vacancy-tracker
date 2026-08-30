"""Импорт вакансий из индекса career-notes/research/README.md.

Индекс уже содержит всё нужное: приоритет, компанию, роль, условия, вердикт
и имя файла с разбором. Скрипт разбирает строки таблицы и наполняет базу,
чтобы не переносить полтора десятка разборов руками.

Запуск:
    python -m scripts.import_from_markdown [путь_к_README]
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crud, models, schemas  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

DEFAULT_INDEX = Path(r"c:\projects\Новая папка (3)\career-notes\research\README.md")

# Что означает метка в колонке приоритета
PRIORITY_MARKERS = {
    "⛔": (models.Status.skipped, 5),
    "🕐": (models.Status.reserve, 4),
    "🎲": (models.Status.applied, 4),
    "—": (models.Status.applied, 3),
}


def parse_priority(cell: str) -> tuple[models.Status, int]:
    """Из '🔥 1' или '⛔' достаёт статус и числовой приоритет."""
    for marker, result in PRIORITY_MARKERS.items():
        if marker in cell:
            return result
    match = re.search(r"\d+", cell)
    priority = int(match.group()) if match else 3
    return models.Status.researched, min(priority, 5)


def parse_company_and_title(cell: str) -> tuple[str, str]:
    """Из '**GyroMind** - разработчик ИИ-агентов' достаёт компанию и роль."""
    clean = cell.replace("**", "").strip()
    for separator in (" - ", " — ", ", "):
        if separator in clean:
            company, title = clean.split(separator, 1)
            return company.strip(), title.strip()
    return clean, clean


def parse_work_format(conditions: str) -> models.WorkFormat:
    lowered = conditions.lower()
    if "удал" in lowered:
        return models.WorkFormat.remote
    if "гибрид" in lowered:
        return models.WorkFormat.hybrid
    if "офис" in lowered:
        return models.WorkFormat.office
    return models.WorkFormat.unknown


def parse_salary(conditions: str) -> tuple[int | None, int | None, str | None]:
    """Понимает записи вида '160к', '150-160к', 'от 250к', '120-160к'."""
    text = conditions.replace(" ", "")
    range_match = re.search(r"(\d{2,3})[-–](\d{2,3})к", text)
    if range_match:
        return int(range_match.group(1)) * 1000, int(range_match.group(2)) * 1000, None
    single_match = re.search(r"(?:от)?(\d{2,3})к", text)
    if single_match:
        value = int(single_match.group(1)) * 1000
        if "от" in text:
            return value, None, "от"
        return value, value, None
    if "вилки нет" in conditions.lower() or "без цифры" in conditions.lower():
        return None, None, "вилка не указана"
    return None, None, None


APPLIED_LIKE = {
    models.Status.applied,
    models.Status.screening,
    models.Status.interview,
    models.Status.offer,
    models.Status.rejected,
}


def date_from_filename(research_file: str | None) -> date | None:
    """Из 'career-notes/research/2026-08-28_b2b-center.md' достаёт 2026-08-28."""
    if not research_file:
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", research_file)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def parse_row(line: str) -> dict | None:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 5:
        return None
    priority_cell, name_cell, conditions, verdict, file_cell = cells[:5]
    if priority_cell.lower().startswith("приоритет") or set(priority_cell) <= {"-", ":"}:
        return None

    status, priority = parse_priority(priority_cell)
    company, title = parse_company_and_title(name_cell)
    salary_min, salary_max, salary_note = parse_salary(conditions)
    research_file = file_cell.strip("` ").split("`")[0].strip() or None

    return {
        "company": company,
        "title": title,
        "status": status,
        "priority": priority,
        "work_format": parse_work_format(conditions),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_note": salary_note or (conditions if len(conditions) < 300 else None),
        "match_note": verdict.replace("**", "") or None,
        "research_file": f"career-notes/research/{research_file}" if research_file else None,
    }


def main(index_path: Path) -> None:
    if not index_path.exists():
        raise SystemExit(f"Индекс не найден: {index_path}")

    init_db()
    session = SessionLocal()
    created = skipped = 0
    try:
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|"):
                continue
            row = parse_row(line)
            if row is None:
                continue

            company = crud.get_or_create_company(session, row.pop("company"))
            title = row["title"]
            exists = any(
                v.title == title and v.company_id == company.id
                for v in crud.list_vacancies(session)
            )
            if exists:
                skipped += 1
                continue

            # Если отклик уже отправлен, датой берём дату разбора из имени файла
            if row["status"] in APPLIED_LIKE:
                row["applied_at"] = date_from_filename(row.get("research_file"))

            vacancy = models.Vacancy(company_id=company.id, **row)
            session.add(vacancy)
            created += 1
        session.commit()
    finally:
        session.close()

    print(f"Импортировано: {created}, пропущено (уже были): {skipped}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INDEX
    main(path)
