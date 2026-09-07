# I/O Functions for wrapping the ingestion/writing of data.
from __future__ import annotations

import re
from pathlib import Path

from brukeropusreader import read_file

from prospecpy.prospecpy import ProSpecPy


def import_run_data(path_to_data: Path, input_type="water vapour", output_folder=None):
    """
    Function to import raw spectra data from the file system/a given folder.

    Parameters:
    - path_to_data: Path
        pathlib object which contains the location of the desired data to import.
    - input_type: str
        Type of input data being imported ("water vapour" or "raw spectra").
    - output_folder: str
        Path to the output folder where processed files will be saved (used only for "raw spectra").

    Returns:
    - raw_data: dict
        Dictionary containing the raw data, read in as OPUSFiles.
    - raw_data_objects: list
        List containing ProSpecPy objects if input_type is "raw spectra".
    """
    # Pulling in all sample data from designated file path
    raw_files = list(path_to_data.iterdir())
    raw_files.sort()

    # Initializing dict of raw spectra files from the file system
    raw_data = dict()  # Dictionary to hold raw OPUS files
    raw_data_objects = []  # List to hold ProSpecPy objects for "raw spectra"

    # Populating the raw_test_data dict with all the read in raw opus files
    for i in raw_files:
        if not i.name.startswith(".DS_Store"):
            # Extract batch ID and sample name from the file path
            batch_id, sample_name = batch_id_sample_name(str(i))
            # Read the file and store it in the raw_data dictionary
            raw_data[f"{i.name}"] = read_file(i)
            output_folder_for_sample = None

            if input_type == "raw spectra":
                # Construct the output folder path for the sample
                if output_folder is not None:
                    output_folder_for_sample = f"{output_folder}/{batch_id}/{sample_name}"
                # Initialize a new ProSpecPy object for the sample
                new_prospecpy_obj = ProSpecPy(output_folder_for_sample)
                # Set the raw_data attribute of the ProSpecPy object
                new_prospecpy_obj.set_raw_data(read_file(i), sample_name, batch_id)
                # Add the ProSpecPy object to the list
                raw_data_objects.append(new_prospecpy_obj)

    if input_type == "raw spectra":
        return (
            raw_data_objects  # Return the list of ProSpecPy objects if input_type is 'raw spectra'
        )

    return raw_data  # Return the dictionary of raw data for other input types


def batch_id_sample_name(filepath):
    """
    Function to extract batch ID and sample name from a given file path.

    Parameters:
    - filepath: str
        The file path from which to extract the batch ID and sample name.

    Returns:
    - batch_id: str or None
        The extracted batch ID, if present.
    - sample_name: str or None
        The extracted sample name, if present.
    """
    # Regular expression to find and extract the portion of the path after 'opus_files'
    batch_id_file_name_pattern = re.search(r"opus_files\s*(.*)", filepath)
    # Extract the matched portion or set to None if not found
    batch_id_file_name_path = (
        batch_id_file_name_pattern.group(1) if batch_id_file_name_pattern else None
    )
    batch_id = None
    sample_name = None
    if batch_id_file_name_path is not None:
        # Split the extracted path into parts using '/'
        parts = batch_id_file_name_path.split("/")
        if len(parts) == 3:
            # if there are 3 elements in parts they will be in this order ['', batch_id, sample_name]
            batch_id = parts[1]
            sample_name = parts[2]
        if len(parts) == 2:
            # if there are 2 elements in parts they will be in this order ['', sample_name]
            sample_name = parts[1]
    return batch_id, sample_name


# Split the string wherever '/' occurs
