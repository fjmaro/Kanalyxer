"""Metadata manager for MediaOfficer"""
from typing import Optional, Tuple
from pathlib import Path
from enum import Enum
import datetime

from kpilexifmanager import PilExifManager
from kexiftoolmanager import ExifToolManager


class MetaManager:
    """
    --------------------------------------------------------------------------
    --------------------------------------------------------------------------
    """
    class LoadId(Enum):
        """Enum for identify the current file loader"""
        PILLOW = 0
        EXIFTOOL = 1

    def __init__(self, log_path: Path, year_bounds=(1800, 2300),
                 pilexif_log=True, pilexif_only=False) -> None:
        self._filepath: Optional[Path] = None
        self._load_id = self.LoadId.PILLOW
        self._exftool = ExifToolManager(logger=True, log_path=log_path)
        self._pilexif = PilExifManager(logger=pilexif_log, log_path=log_path)

        exfdtc = self._exftool.exiftool_detected
        self._pilonly = pilexif_only if exfdtc else True
        self._year_bounds = year_bounds

    @property
    def pilexif_only(self) -> bool:
        """return if ExifToolManager is not being used"""
        return self._pilonly

    @property
    def readable_extensions(self) -> Tuple[str]:
        """return the MetaManager readable extensions"""
        read0 = self._pilexif.READABLE_EXTENSIONS
        read1 = self._exftool.readable_extensions
        return read0 + (read1 if not self._pilonly else ())

    @property
    def editable_extensions(self) -> Tuple[str]:
        """return the MetaManager editable extensions"""
        edit0 = self._pilexif.EDITABLE_EXTENSIONS
        edit1 = self._exftool.editable_extensions
        return edit0 + (edit1 if not self._pilonly else ())

    def file_has_damaged_date(self, file: Path) -> bool:
        """return if a possible damaged date is in the file metadata"""
        try:
            tmp = PilExifManager(logger=False)
            tmp.load_file(file)
            has_date_kwd = tmp.has_date_original
        except AssertionError as asserr:
            if self._pilonly:
                raise asserr
            tmp = ExifToolManager(logger=False)
            tmp.load_file(file)
            has_date_kwd = tmp.has_metadata_date_original_field
        return has_date_kwd and tmp.get_date_original().year == 1

    def get_file_damaged_date(self, file: Path) -> str:
        """return the possible damaged date"""
        try:
            tmp = PilExifManager(False)
            tmp.load_file(file)
        except AssertionError as asserr:
            if self._pilonly:
                raise asserr
            tmp = ExifToolManager(logger=False)
            tmp.load_file(file)
        return tmp.get_date_original_as_str()

    def load_file(self, file: Path) -> None:
        """
        ----------------------------------------------------------------------
        Load the file into the most suitable metadata manager.
        - Pillow: Faster
        - ExifTool: Compatible with more extensions
        ----------------------------------------------------------------------
        """
        assert file.suffix[1:].upper() in self.readable_extensions
        self._filepath = file
        if file.suffix[1:].upper() in self._pilexif.READABLE_EXTENSIONS:
            try:
                self._load_id = self.LoadId.PILLOW
                self._pilexif.load_file(file)
                return
            except ValueError as valerr:
                if self._pilonly:
                    raise valerr
        self._load_id = self.LoadId.EXIFTOOL
        self._exftool.load_file(file)

    def save_file(self, overwrite=True) -> None:
        """save the file loaded"""
        if self._load_id == self.LoadId.PILLOW:
            self._pilexif.save_file(overwrite=overwrite)
        else:
            self._exftool.save_file(overwrite=overwrite)

    def has_valid_date_original(self) -> bool:
        """
        ----------------------------------------------------------------------
        Return if the loaded file has a original date or equivalent and if the
        date is in the year_bounds configured
        ----------------------------------------------------------------------
        """
        if self._load_id == self.LoadId.PILLOW:
            has_date = self._pilexif.has_date_original
        else:
            has_date = self._exftool.has_metadata_date_original
        if has_date:
            date_original = self.get_date_original()
            year0, year1 = self._year_bounds
            return year0 <= date_original.year <= year1
        return False

    def get_date_original(self) -> datetime.datetime:
        """
        ----------------------------------------------------------------------
        Return the file metadata original date or equivalent.
        - has_valid_original_date() must be called first to avoid errors
        ----------------------------------------------------------------------
        """
        if self._load_id == self.LoadId.PILLOW:
            return self._pilexif.get_date_original()
        return self._exftool.get_date_original()

    def set_date_original(self, date2add: datetime.datetime) -> None:
        """Set the date2add as the original date of the file loaded"""
        # pylint: disable=protected-access
        assert self._filepath is not None, "No file loaded to set date"
        assert self._filepath.suffix[1:].upper() in self.editable_extensions
        if self._load_id == self.LoadId.EXIFTOOL:
            self._exftool.set_date_original(date2add)
            self._exftool.save_file(overwrite=True)
            return

        suffix = self._pilexif._filepath.suffix[1:].upper()
        if suffix in PilExifManager.EDITABLE_EXTENSIONS:
            self._pilexif.set_date_original(date2add)
            self._pilexif.save_file(overwrite=True)
            return

        self._load_id = self.LoadId.EXIFTOOL
        self._exftool.load_file(self._pilexif._filepath)
        self._exftool.set_date_original(date2add)
        self._exftool.save_file(overwrite=True)
