from adapters.repositories.task_repository_crud import TaskCrudMixin
from adapters.repositories.task_repository_common import TaskRepositoryCommon
from adapters.repositories.task_repository_occurrence import TaskOccurrenceMixin


class TaskRepository(
    TaskCrudMixin,
    TaskOccurrenceMixin,
    TaskRepositoryCommon,
):
    pass
