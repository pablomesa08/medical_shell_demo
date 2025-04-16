from enum import Enum

class BaseMetaData: {
    "original_images": {},
    "derivatives": {},
    "patient_data": {},
    "segmentations": {},
    "versions": {}    
}

class GitCommands(Enum):
    COMMANDS_TO_COMPLETE = [
        'init',
        'status',
        'log',
        'diff',
        'commit',
        'add',
        'register',
        'compare',
        'visualize',
        'patient-info',
        'history',
        'export',
        'help',
        'register-original',
        'register-derivative',
        'show-derivatives',
        'show-patient-tree',
    ]