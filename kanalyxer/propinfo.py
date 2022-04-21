"""database class"""
from dataclasses import dataclass
from pathlib import Path
import datetime

from kjmarotools.proprietdin import rename_proprietary_din_file


@dataclass
class FileInfo:
    """
    --------------------------------------------------------------------------
    File information used in kanalyser.py
    --------------------------------------------------------------------------
    - kdin: bool          # The file has Kjmaro date-in-name
    - ekdin: bool         # The file has Kjmaro edit-date-in-name
    - prpdin: bool        # The file has Proprietary edit-date-in-name
    - metadte: bool       # The file has a valid Metadata original-date
    - readable: bool      # The file metadata is readable
    - editable: bool      # The file metadata is editable
    - abs_path: Path      # Absolute path of the file

    - _metadata_original_date: This is only filled if metadate=True and using
                               the following functions:
        - set_metadate_original()
        - get_metadate_original()
    --------------------------------------------------------------------------
    """
    # pylint: disable=too-many-instance-attributes
    kdin: bool      # The file has Kjmaro date-in-name
    ekdin: bool     # The file has Kjmaro edit-date-in-name
    prpdin: bool    # The file has Proprietary edit-date-in-name
    metadte: bool   # The file has a valid Metadata original-date
    readable: bool  # The file metadata is readable
    editable: bool  # The file metadata is editable
    abs_path: Path  # Absolute path of the file
    _metadata_original_date = datetime.datetime(1, 1, 1)  # see __doc__

    def set_metadate_original(self, date2add: datetime.datetime) -> None:
        """add the original metadate -> [self.metadte must be True]"""
        assert self.metadte, "self.metadte must be True"
        self._metadata_original_date = date2add

    def get_metadate_original(self) -> datetime.datetime:
        """get the original metadate -> [self.metadte must be True]"""
        assert self.metadte, "self.metadte must be True"
        return self._metadata_original_date


def update_proprietary_din(fileinfo: FileInfo, year_bounds=(1800, 2300)
                           ) -> FileInfo:
    """
    --------------------------------------------------------------------------
    Rename the proprietary file with KDIN and return the FileInfo updated.
    - Updated <kdin=True> <prpdin=False> <abs_path=NewPathName>
    --------------------------------------------------------------------------
    """
    new_path = rename_proprietary_din_file(fileinfo.abs_path, year_bounds)
    if new_path.name != fileinfo.abs_path.name:
        fileinfo.abs_path = new_path
        fileinfo.prpdin = False
        fileinfo.kdin = True
    return fileinfo
