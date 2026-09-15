# -*- coding: utf-8 -*-
"""Разовая правка 15.09 вечер: техсобес КИРБ назначен, две новые вакансии."""
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app import crud, models, schemas
from app.database import SessionLocal

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 9, 15, 20, 0, tzinfo=MSK)


def main() -> None:
    s = SessionLocal()
    try:
        # --- КИРБ: техсобес назначен на пятницу 18.09, 10:00
        kirb = crud.get_vacancy(s, 107)
        if kirb is not None and not any(e.title == "Техсобеседование назначено" for e in kirb.events):
            was = kirb.status.value
            crud.add_event(s, kirb, schemas.EventCreate(
                type=models.EventType.interview,
                title="Техсобеседование назначено",
                details="Пятница 18.09.2026, 10:00 МСК, на месте (Neva Towers). Готовиться по KIRB_Interview_Prep.md.",
                happened_at=NOW,
            ))
            kirb.next_action = "Техсобеседование 18.09 в 10:00 - подготовка по KIRB_Interview_Prep.md"
            kirb.next_action_at = date(2026, 9, 18)
            s.commit()
            print(f"107 ООО КИРБ: {was} -> {kirb.status.value}, техсобес 18.09 10:00")
        else:
            print("107 ООО КИРБ: событие уже стоит, пропускаю")

        # --- ФизЭл: HR написал сам, письмо готово к отправке
        if s.query(models.Company).filter_by(name="ООО ФизЭл").first():
            print("ООО ФизЭл: уже в базе, пропускаю")
        else:
            fizel = crud.create_vacancy(s, schemas.VacancyCreate(
                company_name="ООО ФизЭл",
                title="Fullstack-разработчик (Agent-Coding)",
                source_url=None,
                salary_min=200000,
                salary_note="От 200 000 ₽/мес до вычета, 2 раза в месяц. HR написал сам, не отклик Ивана.",
                work_format=models.WorkFormat.office,
                location="Москва, м. Тимирязевская",
                track=models.Track.dev,
                resume_used="Python-разработчик",
                match_note=(
                    "HR вышел сам 15.09. Сильное совпадение: agent-coding - ежедневная реальная практика "
                    "Ивана с Claude Code, редкий и честный козырь. Python и PostgreSQL - уверенно. "
                    "Пробелы: Go (только вводные курсы, не продакшн), React - есть опыт («электронный "
                    "секретарь»), но не в этом объёме, high-load/real-time и домен РЛС/телеметрии - нет. "
                    "Опыт коммерческой разработки от 1 года - закрыт. Мнение: Под вопросом, не Рекомендую - "
                    "слишком много незакрытых пунктов требований (Go, high-load, домен), но agent-coding "
                    "и Python дают реальный шанс пройти скрининг."
                ),
            ))
            crud.add_event(s, fizel, schemas.EventCreate(
                type=models.EventType.reply,
                title="HR написал сам с предложением",
                details="Вакансия Fullstack-разработчик (Agent-Coding), Go/Python/PostgreSQL/React.",
                happened_at=NOW,
            ))
            fizel.next_action = "Отправить письмо HR, указать зарплатные ожидания"
            fizel.next_action_at = date(2026, 9, 16)
            s.commit()
            print(f"Новая вакансия: ФизЭл #{fizel.id}")

        # --- Online Reservation System: сопровождение БД
        if s.query(models.Company).filter_by(name="Online Reservation System").first():
            print("Online Reservation System: уже в базе, пропускаю")
        else:
            ors = crud.create_vacancy(s, schemas.VacancyCreate(
                company_name="Online Reservation System",
                title="Старший специалист по работе с базой данных",
                source_url=None,
                work_format=models.WorkFormat.hybrid,
                track=models.Track.support,
                resume_used="Специалист сопровождения систем",
                match_note=(
                    "Сильный матч на сопровождение: анализ и контроль данных, разбор инцидентов, SQL-выгрузки - "
                    "прямое повторение опыта со сверкой балансов/платежей/проводок. Sybase ASE - не в опыте, "
                    "но реляционная СУБД, тот же принцип, что PostgreSQL/MS SQL. Мнение: Рекомендую."
                ),
            ))
            crud.add_event(s, ors, schemas.EventCreate(
                type=models.EventType.note,
                title="Письмо подготовлено, ждёт отправки",
                happened_at=NOW,
            ))
            ors.next_action = "Отправить письмо"
            ors.next_action_at = date(2026, 9, 16)
            s.commit()
            print(f"Новая вакансия: Online Reservation System #{ors.id}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
