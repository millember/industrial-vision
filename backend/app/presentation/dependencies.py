from dataclasses import dataclass
from app.application.auth import AuthService
from app.application.use_case.administration import CreateUserUseCase, IssueKeyUseCase, RevokeKeyUseCase, CatalogueCreateUseCase, AdminQueriesUseCase
from app.infrastructure.passwords import Passwords
from app.infrastructure.repository import Repository
from app.infrastructure.queries.admin import AdminQueries
from app.application.use_case.preview import PreviewInspectionUseCase
from app.infrastructure.images import PillowImageDecoder
from app.infrastructure.mock_model import MockModelAdapter

@dataclass(frozen=True)
class Services:
    auth: AuthService
    users: CreateUserUseCase
    issue_key: IssueKeyUseCase
    revoke_key: RevokeKeyUseCase
    catalogue: CatalogueCreateUseCase
    queries: AdminQueriesUseCase
    preview: PreviewInspectionUseCase

def create_services(*, session_factory, analysis_mode: str = "disabled") -> Services:
    if analysis_mode not in ("disabled", "mock"):
        raise ValueError("ANALYSIS_MODE must be disabled or mock")
    repository=Repository(session_factory)
    passwords=Passwords()
    return Services(
        auth=AuthService(repository,passwords),
        users=CreateUserUseCase(users=repository,passwords=passwords),
        issue_key=IssueKeyUseCase(keys=repository),
        revoke_key=RevokeKeyUseCase(keys=repository),
        catalogue=CatalogueCreateUseCase(records=repository),
        queries=AdminQueriesUseCase(queries=AdminQueries(session_factory)),
        preview=PreviewInspectionUseCase(queries=AdminQueries(session_factory), images=PillowImageDecoder(),
                                         model=MockModelAdapter() if analysis_mode == "mock" else None),
    )
