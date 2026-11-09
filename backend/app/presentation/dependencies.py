from dataclasses import dataclass
from app.application.auth import AuthService
from app.application.use_case.administration import CreateUserUseCase, IssueKeyUseCase, RevokeKeyUseCase, CatalogueCreateUseCase, AdminQueriesUseCase
from app.infrastructure.passwords import Passwords
from app.infrastructure.repository import Repository
from app.infrastructure.queries.admin import AdminQueries

@dataclass(frozen=True)
class Services:
    auth: AuthService
    users: CreateUserUseCase
    issue_key: IssueKeyUseCase
    revoke_key: RevokeKeyUseCase
    catalogue: CatalogueCreateUseCase
    queries: AdminQueriesUseCase

def create_services(*, session_factory) -> Services:
    repository=Repository(session_factory)
    passwords=Passwords()
    return Services(
        auth=AuthService(repository,passwords),
        users=CreateUserUseCase(users=repository,passwords=passwords),
        issue_key=IssueKeyUseCase(keys=repository),
        revoke_key=RevokeKeyUseCase(keys=repository),
        catalogue=CatalogueCreateUseCase(records=repository),
        queries=AdminQueriesUseCase(queries=AdminQueries(session_factory)),
    )
