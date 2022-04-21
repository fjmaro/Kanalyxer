"""Analyser"""
from typing import List, Tuple
from logging import Logger
from pathlib import Path
import datetime
import shutil
import os

from kjmarotools import proprietdin
from kjmarotools.basics import filetools, conventions, logtools, ostools

from . import metamgr, propinfo


class Analyxer:
    """
    --------------------------------------------------------------------------
    Kjmaro Negatives Arranger
    --------------------------------------------------------------------------
    The purpose of this program is to have and maintain all the files in the
    given folder with a safe file-original-date (or equivalent) and if the
    folder has a valid KDIN-bounds, ensure that the file belongs to those.
    - Scans for files with datetime in risk
    - Fix the files following well-known proprietary conventions
    - Apply the date date the given in the Kjmaro Edit-Date-in-name (EKDIN) to
      the files containing it.
      - If the file has exif-editable -> Apply to exif
      - If not, apply including it as a DIN
    - Scans the folders to detect files out of folder KDIN-bounds
    --------------------------------------------------------------------------
    """
    # pylint: disable=too-many-instance-attributes
    TO_REVIEW_PATH = "Files to review"
    SKIP_EXTENSIONS = ("DMG", "XSL", "XML", "TXT", "DOC", "DOCX", "PPT", "DB",
                       "LNK", "GIF", "BUP", "IFO", "VOB", "MP3", "ODT", "RAR",
                       "PDF", "RTF", "DS_STORE")

    def __init__(self, base_path2scan: Path, logger: Logger,
                 meta_loggers_path: Path,
                 folder_patterns: Tuple[str, ...] = (),
                 year_bounds=(1800, 2300), pilexif_log=True) -> None:
        # pylint: disable=too-many-arguments

        # Input variables to the class
        self.log = logger
        self.files2scan: List[Path] = []
        self.year_bounds = year_bounds
        self.fld_patterns = folder_patterns
        self.base_path2scan = base_path2scan
        self.meta_logs_path = meta_loggers_path
        self.metadata_editor = metamgr.MetaManager(meta_loggers_path,
                                                   year_bounds, pilexif_log)

        # Internal variables of the class
        self.files2analyse: List[propinfo.FileInfo] = []
        self.__phs = "[ALX] <NewModulePhase> "
        self.__res = "[ALX] <NewResultsBlock> "

    def load_files2analyse(self) -> None:
        """
        ----------------------------------------------------------------------
        Get all the files valid to be analysed and keep its information for
        fuerther analysis in the next steps
        ----------------------------------------------------------------------
        """
        self.log.info(f"{self.__phs}Scanning files in path...")
        folders2scan = filetools.get_folders_tree(self.base_path2scan,
                                                  self.fld_patterns)
        files_in_path = filetools.get_files_tree(folders2scan)

        for file in files_in_path:
            if file.name.upper().split(".")[-1] in self.SKIP_EXTENSIONS:
                continue
            if file.suffix[1:].upper() in self.SKIP_EXTENSIONS:
                continue

            valid_mtadate = False
            suffix = file.suffix[1:].upper()
            if suffix in self.metadata_editor.readable_extensions:
                self.metadata_editor.load_file(file)
                valid_mtadate = self.metadata_editor.has_valid_date_original()
                if valid_mtadate:
                    metadate_orig = self.metadata_editor.get_date_original()

            finfo = propinfo.FileInfo(
                conventions.is_file_kdin(file, self.year_bounds),
                conventions.is_file_ekdin(file, self.year_bounds),
                proprietdin.is_proprietary_din(file, self.year_bounds),
                valid_mtadate,
                suffix in self.metadata_editor.readable_extensions,
                suffix in self.metadata_editor.editable_extensions,
                file)

            if valid_mtadate:
                finfo.set_metadate_original(metadate_orig)
            self.files2analyse.append(finfo)
        inf_msg = f"{self.__res}Files found to be analyzed = %s"
        self.log.info(inf_msg, len(self.files2analyse))

    def rename_files_with_proprietary_convention(self) -> List[Path]:
        """
        ----------------------------------------------------------------------
        Rename any file following one of the defined proprietary conventions
        allocated in kpropriet.py
        ----------------------------------------------------------------------
        """
        infmsg = f"{self.__phs}Scanning proprietary date-in-name files to"
        self.log.info(infmsg + " rename...")
        files_renamed: List[Path] = []
        files_existing: List[Path] = []
        for idx, fileinfo in enumerate(self.files2analyse):

            if fileinfo.prpdin:
                original_path = fileinfo.abs_path
                updated_info = propinfo.update_proprietary_din(fileinfo)
                if updated_info.abs_path == original_path:
                    files_existing.append(original_path)
                else:
                    self.files2analyse[idx] = updated_info
                    files_renamed.append(updated_info.abs_path)

        if files_renamed:
            imsg = f"{self.__res}Files with proprietary date-in-name "
            imsg += "renamed = %s"
            self.log.info(imsg, len(files_renamed))
            for fle in files_renamed:
                self.log.info("[ALX] [PropRenamed]: %s",
                              str(fle.relative_to(self.base_path2scan)))
        if files_existing:
            imsg = f"{self.__res}Files not renamed because the renamed "
            imsg += "file already exists = %s"
            self.log.warning(imsg, len(files_existing))
            for fle in files_existing:
                self.log.warning(
                    "[ALX] [Duplicated] (%s): %s",
                    proprietdin.kdin_from_proprietary_din(fle).name,
                    str(fle.relative_to(self.base_path2scan)))
        return files_existing

    def analyse_files_date_integrity(self) -> List[Path]:
        """
        ----------------------------------------------------------------------
        Verify that for all the files given they have a valid ExifOriginalDate
        or KDIN in its filename (Kjmaro date-in-name convention)
        ----------------------------------------------------------------------
        """
        self.log.info(f"{self.__phs}Checking file-dates integrity...")
        files_damaged: List[Path] = []
        files_date2review: List[Path] = []
        for idx, fileinfo in enumerate(self.files2analyse):
            if fileinfo.kdin or fileinfo.ekdin:
                continue
            if fileinfo.metadte or fileinfo.prpdin:
                continue

            # Try to extract damaged original dates from the metadata
            if fileinfo.readable:
                abs_pth = fileinfo.abs_path
                if self.metadata_editor.file_has_damaged_date(abs_pth):
                    dtei = self.metadata_editor.get_file_damaged_date(abs_pth)
                    dmg2path = abs_pth.joinpath(str(dtei))
                    files_damaged.append(dmg2path)
                    continue

            # Dates in risk -> Write TRKDIN (KDIN with Date-To-Review)
            mdf_date = ostools.get_file_modify_date(fileinfo.abs_path)
            new_name = conventions.file_clean2trkdin(fileinfo.abs_path,
                                                     mdf_date)
            os.rename(fileinfo.abs_path, new_name)
            files_date2review.append(new_name)
            fileinfo.abs_path = new_name
            fileinfo.kdin = True
            self.files2analyse[idx] = fileinfo

        if files_damaged:
            imsg = f"{self.__res}Files with damaged metadata-date found = %s"
            self.log.warning(imsg, len(files_damaged))
            for fle in files_damaged:
                self.log.warning("[ALX] [DateDamaged] (%s): %s", fle.name,
                                 str(fle.parent.relative_to(
                                     self.base_path2scan)))
        if files_date2review:
            imsg = f"{self.__res}Files with dates-to-review renamed and found"
            imsg += " = %s"
            self.log.warning(imsg, len(files_date2review))
            for fle in files_date2review:
                self.log.warning("[ALX] [Date2Review]: %s",
                                 str(fle.relative_to(self.base_path2scan)))
        clean_files_damaged = [x.parent for x in files_damaged]
        return clean_files_damaged + files_date2review

    def write_date_to_files_with_edition_kdin(self) -> List[Path]:
        """
        ----------------------------------------------------------------------
        Risky step (The metadata-edited files updated must be reviewed). This
        function stores the KEDIN in the files metadata (if writable):
        - The file is metadata is not writable the date is stored in the file
          name using the Kjmaro DIN convention.
        ----------------------------------------------------------------------
        """
        # pylint:disable=too-many-branches,too-many-locals,too-many-statements
        infmsg = f"{self.__phs}Scanning edition-date-in-name files to store"
        self.log.info(infmsg + "...")
        folder2review = filetools.itername(
            self.meta_logs_path.joinpath(self.TO_REVIEW_PATH))
        fld4f2rev_originals = folder2review.joinpath("originals")
        fld4f2rev_edited = folder2review.joinpath("edited")

        meta_edited: List[Path] = []
        files_din_renamed: List[Path] = []
        for idx, fileinfo in enumerate(self.files2analyse):
            if fileinfo.ekdin:
                if fileinfo.editable:
                    # Create the folders if editable file is finally found
                    os.makedirs(fld4f2rev_originals, exist_ok=True)
                    os.makedirs(fld4f2rev_edited, exist_ok=True)

                    # Move a copy of the file before the edition
                    nme = fld4f2rev_originals.joinpath(fileinfo.abs_path.name)
                    shutil.copy2(fileinfo.abs_path, nme)

                    # Edit the metadata exif
                    date2add = conventions.get_file_ekdin(fileinfo.abs_path,
                                                          self.year_bounds)
                    self.metadata_editor.load_file(fileinfo.abs_path)
                    self.metadata_editor.set_date_original(date2add)
                    self.metadata_editor.save_file()

                    # Move a copy of the new file
                    nme = fld4f2rev_edited.joinpath(fileinfo.abs_path.name)
                    shutil.copy2(fileinfo.abs_path, nme)

                    # Rename the file edited
                    new_rnme = filetools.itername(
                        conventions.file_ekdin2clean(fileinfo.abs_path))
                    os.rename(fileinfo.abs_path, new_rnme)
                    meta_edited.append(new_rnme)
                    fileinfo.metadte = True
                    fileinfo.ekdin = False
                    fileinfo.abs_path = new_rnme
                    fileinfo.set_metadate_original(date2add)
                    self.files2analyse[idx] = fileinfo
                    continue

                new_rnme = filetools.itername(conventions.file_ekdin2kdin(
                    fileinfo.abs_path, self.year_bounds))
                os.rename(fileinfo.abs_path, new_rnme)
                files_din_renamed.append(new_rnme)
                fileinfo.abs_path = new_rnme
                fileinfo.ekdin = False
                fileinfo.kdin = True
                self.files2analyse[idx] = fileinfo

        if files_din_renamed:
            imsg = f"{self.__res}Files with edition date-in-name renamed = %s"
            self.log.info(imsg, len(files_din_renamed))
            for fle in files_din_renamed:
                self.log.info("[ALX] [EdinRenamed]: %s",
                              str(fle.relative_to(self.base_path2scan)))
        if meta_edited:
            imsg = f"{self.__res}Files with metadata date field edited = %s"
            self.log.warning(imsg, len(meta_edited))
            imsg = "[ALX] For reviewing this metadata edition see folders: "
            imsg += f"<{fld4f2rev_originals.name}> and "
            imsg += f"<{fld4f2rev_edited.name}> allocated in "
            imsg += f"<{folder2review.name}> folder."
            self.log.warning(imsg)
            for fle in meta_edited:
                self.log.info("[ALX] [Edin2Metadt]: %s",
                              str(fle.relative_to(self.base_path2scan)))
        return files_din_renamed + meta_edited

    def analyse_files_date_consistency(self, margin_secs=60) -> List[Path]:
        """
        ----------------------------------------------------------------------
        Check for all the files with a valid Metadata Original Date and valid
        date-in-name that the date is the same in both cases (with a margin
        of <margin_secs>). Log the inconsistent Metadata-date for the review.
        ----------------------------------------------------------------------
        """
        infmsg = f"{self.__phs}Scanning file Metadates and KDIN consistency"
        self.log.info(infmsg + "...")
        inconsistent: List[Path] = []
        for fileinfo in self.files2analyse:
            if fileinfo.kdin and fileinfo.metadte:
                meta_date = fileinfo.get_metadate_original()
                kdin_date = conventions.get_file_kdin(fileinfo.abs_path,
                                                      self.year_bounds)
                if abs((meta_date - kdin_date).total_seconds()) > margin_secs:
                    inconsistent.append(fileinfo.abs_path.joinpath(
                        str(meta_date)))

        if inconsistent:
            imsg = f"{self.__res}Files with inconsistent Metadates and KDIN "
            imsg += "detected = %s >>> (Metadata dates are given in the "
            imsg += "following list)"
            self.log.warning(imsg, len(inconsistent))
            for fle in inconsistent:
                dtt_fmt = r"%Y-%m-%d %H:%M:%S"
                dttm = datetime.datetime.strptime(str(fle.name)[:19], dtt_fmt)
                self.log.warning("[ALX] [Inconsistent] (%s): %s",
                                 conventions.date2ekdin(dttm),
                                 str(fle.parent.relative_to(
                                     self.base_path2scan)))
        return [x.parent for x in inconsistent]

    def detect_files_out_of_folder_date_bounds(self) -> List[Path]:
        """
        ----------------------------------------------------------------------
        Verfy that for that all the given files its *valid-date is in the
        folder DIN-bounds according to Kjmaro convention. (Only for the cases
        where the folder has a valid DIN-bounds)
        ----------------------------------------------------------------------
        - *valid-date: A date is valid it one of the following assumptions is
                       <True> and the date is in the given year_bounds.
            - Has KDIN and it is in year_bounds
            - Has ExifOriginalDate or equivalent and it is in year_bounds
        ----------------------------------------------------------------------
        """
        infmsg = f"{self.__phs}Checking file-dates out of folder-bounds..."
        self.log.info(infmsg)
        discrepances: List[Path] = []
        for fileinfo in self.files2analyse:
            folder_path = fileinfo.abs_path.parent

            if conventions.is_folder_kdin(folder_path, self.year_bounds):
                fld_bounds = conventions.get_folder_kdin_bounds(
                    folder_path, self.year_bounds)
                if fileinfo.kdin:
                    kdn = conventions.get_file_kdin(fileinfo.abs_path,
                                                    self.year_bounds)
                    if fld_bounds[0] <= kdn <= fld_bounds[1]:
                        continue
                    discrepances.append(fileinfo.abs_path.joinpath(str(kdn)))

                elif fileinfo.ekdin:
                    edn = conventions.get_file_ekdin(fileinfo.abs_path,
                                                     self.year_bounds)
                    if fld_bounds[0] <= edn <= fld_bounds[1]:
                        continue
                    discrepances.append(fileinfo.abs_path.joinpath(str(edn)))

                elif fileinfo.readable and fileinfo.metadte:
                    dto = fileinfo.get_metadate_original()
                    if fld_bounds[0] <= dto <= fld_bounds[1]:
                        continue
                    discrepances.append(fileinfo.abs_path.joinpath(str(dto)))

        if discrepances:
            imsg = f"{self.__res}Files with dates out of folder-bounds "
            imsg += "detected = %s"
            self.log.warn(imsg, len(discrepances))
            for fle in discrepances:
                self.log.warning("[ALX] [OutOfBounds] (%s): %s", fle.name,
                                 str(fle.parent.relative_to(
                                     self.base_path2scan)))
        return [x.parent for x in discrepances]

    def run(self, margin_secs=60, embedded=False) -> bool:
        """
        ----------------------------------------------------------------------
        Execute Analyxer with the defined configuration
        # - log_actions: log the folders created and files moved
        # - embedded: It won't stop after successful execution
        ----------------------------------------------------------------------
        """
        self.log.info("[ALX] <INIT> Analyxer initialized ...")
        self.log.info(f"[ALX] <CNFG> base_path2scan = {self.base_path2scan}")
        self.log.info(f"[ALX] <CNFG> fld_patterns = {self.fld_patterns}")
        self.log.info(f"[ALX] <CNFG> skip_extensions = {self.SKIP_EXTENSIONS}")
        self.log.info(f"[ALX] <CNFG> Review_folder = [{self.TO_REVIEW_PATH}]")
        self.log.info(f"[ALX] <CNFG> year_bounds = {self.year_bounds}")
        tgs0 = "[PropRenamed] [Duplicated] [DateDamaged] [Date2Review]"
        tgs1 = "[EdinRenamed] [Edin2Metadt] [Inconsistent] [OutOfBounds]"
        self.log.info("[ALX] <TAGS> " + tgs0)
        self.log.info("[ALX] <TAGS> " + tgs1)

        self.load_files2analyse()
        self.rename_files_with_proprietary_convention()
        warns0 = self.analyse_files_date_integrity()
        warns1 = self.write_date_to_files_with_edition_kdin()
        warns2 = self.analyse_files_date_consistency(margin_secs)
        warns3 = self.detect_files_out_of_folder_date_bounds()

        if not embedded:
            input("\nPROCESS FINALIZED\n\t\tPRESS ENTER TO RESUME")
        return bool(len(warns0) + len(warns1) + len(warns2) + len(warns3))


if __name__ == "__main__":
    # ========================================================================
    # For executing this example remove the relative '.' imports
    # ========================================================================
    _THIS_FILE_PATH = Path(__file__).parent.resolve()
    _POSITIVE_FOLDER = _THIS_FILE_PATH.parent.parent
    _LOGGER = logtools.get_fast_logger("Analyxer", _THIS_FILE_PATH)
    _FOLDER_PATTERNS = ("1.*", "2.*", "3.*", "4.*", "5.*", )
    Analyxer(_POSITIVE_FOLDER, _LOGGER, _THIS_FILE_PATH,
             _FOLDER_PATTERNS,).run()
