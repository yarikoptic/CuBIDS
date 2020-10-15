"""Main module."""
import bids
import json
from pathlib import Path
from bids.layout import parse_file_entities
import pandas as pd
import pdb

bids.config.set_option('extension_initial_dot', True)

NON_KEY_ENTITIES = set(["subject", "session", "extension"])
# Multi-dimensional keys SliceTiming
IMAGING_PARAMS = set([
    "ParallelReductionFactorInPlane", "ParallelAcquisitionTechnique",
    "ParallelAcquisitionTechnique", "PartialFourier", "PhaseEncodingDirection",
    "EffectiveEchoSpacing", "TotalReadoutTime", "EchoTime",
    "SliceEncodingDirection", "DwellTime", "FlipAngle",
    "MultibandAccelerationFactor", "RepetitionTime", "SliceTiming",
    "VolumeTiming", "NumberOfVolumesDiscardedByScanner",
    "NumberOfVolumesDiscardedByUser"])


class BOnD(object):

    def __init__(self, data_root):  

        self.path = data_root
        self.layout = bids.BIDSLayout(self.path, validate = False)
        self.keys_files = {}
       
    def fieldmaps_ok(self):
        pass

    def rename_files(self, filters, pattern, replacement):
        """
        # @Params
            # - filters: pybids entities dictionary to find files to rename
            # - pattern: the substring of the file we would like to replace
            # - replacement: the substring that will replace "pattern"
        # @Returns
            # - None

        >>> my_bond.rename_files({"PhaseEncodingDirection": 'j-',
        ...                       "EchoTime": 0.005},
        ...                       "acq-123", "acq-12345_dir-PA"
        ...                     )
        """
        files_to_change = self.layout.get(return_type='filename', **filters)
        for bidsfile in files_to_change:
            path = Path(bidsfile.path)
            old_name = path.stem
            old_ext = path.suffix
            directory = path.parent
            new_name = old_name.replace(pattern, replacement) + old_ext
            path.rename(Path(directory, new_name))

    def get_param_groups(self, key_group):
        key_entities = _key_group_to_entities(key_group)
        key_entities["extension"] = ".nii[.gz]*"
        matching_files = self.layout.get(return_type="file", scope="self",
                                         regex_search=True, **key_entities)
        return _get_param_groups(matching_files, self.layout)

    def get_file_params(self, key_group):
        # files = self.keys_files[key_group] 
        # return _get_file_params(files, self.layout)
        key_entities = _key_group_to_entities(key_group)
        key_entities["extension"] = ".nii[.gz]*"
        matching_files = self.layout.get(return_type="file", scope="self",
                                         regex_search=True, **key_entities)
        return _get_file_params(matching_files, self.layout)
    

    def get_key_groups(self):
        key_groups = set()
        for path in Path(self.path).rglob("*.*"):
            if path.suffix == ".json" and path.stem != "dataset_description":
                key_groups.update((_file_to_key_group(path),))
                # FILL THE DICTIONARY OF KEY GROUP, LIST OF FILENAMES PAIRS
                ret = _file_to_key_group(path)
                if ret not in self.keys_files.keys():
                    self.keys_files[ret] = []    
                self.keys_files[ret].append(path)
        return sorted(key_groups)
   
    
    def get_filenames(self, key_group): 
        # NEW - WORKS
        return self.keys_files[key_group]


    
    
    def change_filenames(self, key_group, split_params, pattern, replacement):
        # NEW
        #files = self.keys_files[key_group]
        # for each filename in the key group, check if it's params match split_params
        # if they match, perform the replacement acc to pattern/replacement
        new_paths = []
        changes = 0
        dict_files_params = self.get_file_params(key_group)
        for filename in dict_files_params.keys(): 
            if dict_files_params[filename] == split_params:
                # DO REPLACEMENT!
                path = Path(filename)
                old_name = path.stem
                old_ext = path.suffix
                directory = path.parent
                new_name = old_name.replace(pattern, replacement) + old_ext
                path.rename(Path(directory, new_name)) 
                new_paths.append(path)
                changes += 1
        return (new_paths, changes)

       
    def change_metadata(self, filters, pattern, metadata):

        # TODO: clean prints and add warnings

        files_to_change = self.layout.get(return_type='object', **filters)

        if not files_to_change:

            print('NO FILES FOUND')
        for bidsfile in files_to_change:

            # get the sidecar file
            bidsjson_file = bidsfile.get_associations()

            if not bidsjson_file:
                print("NO JSON FILES FOUND IN ASSOCIATIONS")
                continue

            json_file = [x for x in bidsjson_file if 'json' in x.filename]

            if not len(json_file) == 1:

                print("FOUND IRREGULAR ASSOCIATIONS")

            else:

                # get the data from it
                json_file = json_file[0]

                sidecar = json_file.get_dict()
                sidecar.update(metadata)

                # write out
                _update_json(json_file.path, sidecar)


def _update_json(json_file, metadata):

    if _validateJSON(metadata):
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
    else:

        print("INVALID JSON DATA")
    #metadata.update


def _validateJSON(json_data):

    # TODO
    return True
    '''try:
        json.load(json_data)
    except ValueError as err:
        return False
    return True
    '''


def _key_group_to_entities(key_group):
    return dict([group.split("-") for group in key_group.split("_")])


def _entities_to_key_group(entities):
    group_keys = sorted(entities.keys() - NON_KEY_ENTITIES)
    return "_".join(
        ["{}-{}".format(key, entities[key]) for key in group_keys])


def _file_to_key_group(filename):
    entities = parse_file_entities(str(filename))
    return _entities_to_key_group(entities)


def _get_param_groups(files, layout):
    """Finds a list of *parameter groups* from a list of files.

    Parameters:
    -----------

    files : list
        List of file names

    Returns:
    --------

    parameter_groups : list
        A list of unique parameter groups

    For each file in `files`, find critical parameters for metadata. Then find
    unique sets of these critical parameters.
    """

    dfs = []
    for path in files:
        metadata = layout.get_metadata(path)
        wanted_keys = metadata.keys() & IMAGING_PARAMS
        example_data = {key: metadata[key] for key in wanted_keys}
        
        # Expand slice timing to multiple columns
        SliceTime = example_data.get('SliceTiming')
        if SliceTime:
            # round each slice time to one place after the decimal
            for i in range(len(SliceTime)):
                SliceTime[i] = round(SliceTime[i], 1)
            example_data.update(
                {"SliceTime%03d" % SliceNum: time for
                 SliceNum, time in enumerate(SliceTime)})
            del example_data['SliceTiming']
        
        dfs.append(example_data)

    return pd.DataFrame(dfs).drop_duplicates()


def _get_file_params(files, layout):
    """Finds a list of *parameter groups* from a list of files.

    Parameters:
    -----------

    files : list
        List of file names

    Returns:
    --------

    parameter_groups : list
        A list of unique parameter groups

    For each file in `files`, find critical parameters for metadata. Then find
    unique sets of these critical parameters.
    """
    dict_files_params = {}
    
    for path in files:
        metadata = layout.get_metadata(path)
        wanted_keys = metadata.keys() & IMAGING_PARAMS
        example_data = {key: metadata[key] for key in wanted_keys}
        
        # Expand slice timing to multiple columns
        SliceTime = example_data.get('SliceTiming')
        if SliceTime:
            # round each slice time to one place after the decimal
            for i in range(len(SliceTime)):
                SliceTime[i] = round(SliceTime[i], 1)
            example_data.update(
                {"SliceTime%03d" % SliceNum: time for
                 SliceNum, time in enumerate(SliceTime)})
            del example_data['SliceTiming']
        
        dict_files_params[path] = example_data

    return dict_files_params
