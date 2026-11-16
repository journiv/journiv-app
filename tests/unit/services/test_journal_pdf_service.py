import sys
import uuid
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlmodel import Session, create_engine

from app.core.exceptions import JournalNotFoundError, TagNotFoundError
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import Moment
from app.models.moment_tag_link import MomentTagLink
from app.models.tag import Tag
from app.models.user import User
from app.services.pdf_service import JournalPDFService, PDFService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _add_entry(
    session: Session,
    *,
    user_id: uuid.UUID,
    journal_id: uuid.UUID,
    logged_date: date,
    title: str,
    tag_ids: tuple[uuid.UUID, ...] = (),
    is_draft: bool = False,
) -> Entry:
    moment = Moment(user_id=user_id, logged_date_tz=logged_date)
    session.add(moment)
    session.flush()
    entry = Entry(
        user_id=user_id,
        journal_id=journal_id,
        moment_id=moment.id,
        title=title,
        content_delta={"ops": [{"insert": f"{title} content\n"}]},
        is_draft=is_draft,
    )
    session.add(entry)
    for tag_id in tag_ids:
        session.add(MomentTagLink(moment_id=moment.id, tag_id=tag_id))
    session.commit()
    return entry


def test_journal_pdf_filters_by_inclusive_date_range_and_tag(monkeypatch):
    session = _session()
    user = User(
        email=f"{uuid.uuid4()}@example.com", password="password123", name="Test"
    )
    session.add(user)
    session.commit()
    journal = Journal(user_id=user.id, title="Therapy Notes")
    other_journal = Journal(user_id=user.id, title="Other Journal")
    share_tag = Tag(user_id=user.id, name="share in therapy")
    other_tag = Tag(user_id=user.id, name="other")
    session.add_all([journal, other_journal, share_tag, other_tag])
    session.commit()

    _add_entry(
        session,
        user_id=user.id,
        journal_id=journal.id,
        logged_date=date(2025, 1, 1),
        title="Start boundary",
        tag_ids=(share_tag.id,),
    )
    _add_entry(
        session,
        user_id=user.id,
        journal_id=journal.id,
        logged_date=date(2025, 1, 31),
        title="End boundary",
        tag_ids=(share_tag.id,),
    )
    _add_entry(
        session,
        user_id=user.id,
        journal_id=journal.id,
        logged_date=date(2025, 1, 15),
        title="Other tag",
        tag_ids=(other_tag.id,),
    )
    _add_entry(
        session,
        user_id=user.id,
        journal_id=journal.id,
        logged_date=date(2025, 1, 15),
        title="Draft",
        tag_ids=(share_tag.id,),
        is_draft=True,
    )
    _add_entry(
        session,
        user_id=user.id,
        journal_id=other_journal.id,
        logged_date=date(2025, 1, 15),
        title="Other journal",
        tag_ids=(share_tag.id,),
    )

    service = JournalPDFService(session)
    generated = {}

    def generate_journal_pdf_stream(*, journal_title, entries, base_url):
        generated["title"] = journal_title
        generated["entries"] = entries
        generated["base_url"] = base_url
        return BytesIO(b"%PDF")

    monkeypatch.setattr(
        service.entry_pdf_service, "_get_base_url", lambda: "https://journiv.test"
    )
    monkeypatch.setattr(
        service.entry_pdf_service.pdf_service,
        "generate_journal_pdf_stream",
        generate_journal_pdf_stream,
    )

    pdf, filename = service.generate_journal_pdf(
        journal_id=journal.id,
        user_id=user.id,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tag_id=share_tag.id,
    )

    assert pdf.read() == b"%PDF"
    assert filename == "Therapy-Notes-journal.pdf"
    assert generated["title"] == "Therapy Notes"
    assert [entry["title"] for entry in generated["entries"]] == [
        "Start boundary",
        "End boundary",
    ]
    assert generated["base_url"] == "https://journiv.test"

    service.generate_journal_pdf(journal_id=journal.id, user_id=user.id)
    assert [entry["title"] for entry in generated["entries"]] == [
        "Start boundary",
        "Other tag",
        "End boundary",
    ]


def test_journal_pdf_stream_renders_template_with_base_url(monkeypatch):
    rendered = {}

    class FakeHTML:
        def __init__(self, *, string, base_url):
            rendered["html"] = string
            rendered["base_url"] = base_url

        def write_pdf(self):
            return b"%PDF"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

    pdf = PDFService().generate_journal_pdf_stream(
        journal_title="Journal & Notes",
        entries=[
            {
                "title": "Entry",
                "date": "January 1, 2025",
                "location": None,
                "mood": None,
                "tags": None,
                "content": "<p>Body</p>",
                "attachment_items": [],
            }
        ],
        base_url="https://journiv.test",
    )

    assert pdf.read() == b"%PDF"
    assert rendered["base_url"] == "https://journiv.test"
    assert "Journal &amp; Notes" in rendered["html"]
    assert "<p>Body</p>" in rendered["html"]
    assert ".journal-entry + .journal-entry" in rendered["html"]
    assert "break-before: page;" in rendered["html"]
    assert "page-break-before: always;" in rendered["html"]

    PDFService().generate_journal_pdf_stream(
        journal_title="Empty Journal",
        entries=[],
        base_url="https://journiv.test",
    )
    assert "<p>No entries matched these filters.</p>" in rendered["html"]
    assert "0 entries" not in rendered["html"]
    empty_body = rendered["html"].split("</style>", maxsplit=1)[1]
    assert "journal-cover--has-entries" not in empty_body


def test_journal_pdf_rejects_reversed_date_range():
    service = JournalPDFService(session=_session())
    with pytest.raises(ValueError, match="Start date"):
        service.generate_journal_pdf(
            journal_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            start_date=date(2025, 2, 1),
            end_date=date(2025, 1, 1),
        )


def test_journal_pdf_requires_owned_journal_and_tag():
    session = _session()
    user = User(
        email=f"{uuid.uuid4()}@example.com", password="password123", name="Test"
    )
    session.add(user)
    session.commit()
    journal = Journal(user_id=user.id, title="My Journal")
    other_user = User(
        email=f"{uuid.uuid4()}@example.com", password="password123", name="Other"
    )
    session.add_all([journal, other_user])
    session.commit()
    service = JournalPDFService(session)

    with pytest.raises(JournalNotFoundError):
        service.generate_journal_pdf(
            journal_id=journal.id,
            user_id=other_user.id,
        )
    with pytest.raises(TagNotFoundError):
        service.generate_journal_pdf(
            journal_id=journal.id,
            user_id=user.id,
            tag_id=uuid.uuid4(),
        )
