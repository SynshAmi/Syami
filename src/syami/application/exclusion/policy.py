import fnmatch
import os
from pathlib import Path

from syami.infrastructure.database.db import get_connection


class ExclusionPolicy:
    """
    Determines whether a filesystem path should be excluded from indexing.

    Exclusions come from two sources:

    1. Built-in safety exclusions
    2. User-defined exclusions stored in SQLite

    This class only evaluates paths.
    It does not scan directories or modify the database.
    """

    DEFAULT_DIRECTORY_NAMES = {
        # Development / generated directories
        ".git",
        ".svn",
        ".hg",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",

        # Sensitive user configuration / credential directories
        ".ssh",
        ".gnupg",
        ".aws",
        ".azure",

        # Windows/system directories
        "$Recycle.Bin",
        "System Volume Information",
    }

    DEFAULT_FILE_NAMES = {
        "pagefile.sys",
        "hiberfil.sys",
        "swapfile.sys",
    }

    DEFAULT_ENVIRONMENT_DIRECTORIES = {
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "WINDIR",
        "SYSTEMROOT",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
    }

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._user_exclusions = []
        self._load_user_exclusions()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return os.path.normcase(
            os.path.abspath(os.fspath(path))
        )

    def _load_user_exclusions(self):
        connection = get_connection() if self.db_path is None else get_connection(self.db_path)

        try:
            rows = connection.execute(
                """
                SELECT pattern, match_type
                FROM user_exclusions
                WHERE enabled = 1
                """
            ).fetchall()

            self._user_exclusions = [
                {
                    "pattern": row["pattern"],
                    "match_type": row["match_type"],
                }
                for row in rows
            ]

        finally:
            connection.close()

    def should_exclude(
        self,
        path: str,
        is_directory: bool = False,
    ) -> bool:
        """
        Return True if the path must not be indexed.
        """

        normalized_path = self._normalize_path(path)

        if self._is_default_exclusion(
            normalized_path,
            is_directory,
        ):
            return True

        if self._matches_user_exclusion(
            normalized_path,
            is_directory,
        ):
            return True

        return False

    def _is_default_exclusion(
        self,
        path: str,
        is_directory: bool,
    ) -> bool:
        path_object = Path(path)

        if is_directory:
            if self._is_default_environment_directory(path):
                return True

            if path_object.name.lower() in {
                name.lower()
                for name in self.DEFAULT_DIRECTORY_NAMES
            }:
                return True

            return False

        return path_object.name.lower() in {
            name.lower()
            for name in self.DEFAULT_FILE_NAMES
        }

    def _is_default_environment_directory(
        self,
        path: str,
    ) -> bool:
        for variable in self.DEFAULT_ENVIRONMENT_DIRECTORIES:
            value = os.environ.get(variable)

            if not value:
                continue

            normalized_default = self._normalize_path(value)

            if path == normalized_default:
                return True

        return False

    def _matches_user_exclusion(
        self,
        path: str,
        is_directory: bool,
    ) -> bool:
        filename = Path(path).name

        for exclusion in self._user_exclusions:
            pattern = exclusion["pattern"]
            match_type = exclusion["match_type"]

            if match_type == "directory":
                if self._directory_matches(
                    path,
                    pattern,
                ):
                    return True

            elif match_type == "file":
                if path == self._normalize_path(pattern):
                    return True

            elif match_type == "glob":
                if fnmatch.fnmatch(
                    filename,
                    pattern,
                ):
                    return True

        return False

    def _directory_matches(
        self,
        path: str,
        exclusion_path: str,
    ) -> bool:
        normalized_exclusion = self._normalize_path(
            exclusion_path
        )

        try:
            common_path = os.path.commonpath(
                [path, normalized_exclusion]
            )
        except ValueError:
            # Different drives on Windows.
            return False

        return common_path == normalized_exclusion