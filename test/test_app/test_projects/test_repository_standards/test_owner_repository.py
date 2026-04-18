import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.projects.repository_standards.db_models import Relationship
from app.projects.repository_standards.repositories.owner_repository import OwnerRepository


class TestOwnerRepository(unittest.TestCase):
    def test_delete_by_id_uses_bulk_relationship_delete(self):
        db_session = MagicMock()
        repository = OwnerRepository(db_session=db_session)
        repository.find_by_id = MagicMock(return_value=SimpleNamespace(id=123))

        query = MagicMock()
        filtered = MagicMock()
        db_session.query.return_value = query
        query.filter.return_value = filtered

        deleted = repository.delete_by_id("123")

        self.assertTrue(deleted)
        db_session.query.assert_called_once_with(Relationship)
        query.filter.assert_called_once()
        filtered.delete.assert_called_once_with(synchronize_session=False)
        db_session.delete.assert_called_once()
        db_session.commit.assert_called_once()

    def test_delete_by_id_returns_false_when_owner_missing(self):
        db_session = MagicMock()
        repository = OwnerRepository(db_session=db_session)
        repository.find_by_id = MagicMock(return_value=None)

        deleted = repository.delete_by_id("123")

        self.assertFalse(deleted)
        db_session.query.assert_not_called()
        db_session.delete.assert_not_called()
        db_session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
