# Native libraries
import os
import subprocess
import json
from typing import List
import numpy as np
from datetime import datetime
import atexit

# Non - native libraries
import nibabel as nib

try:
    import readline  # For Linux/Mac
except ImportError:
    try:
        from pyreadline3 import Readline  # Modern alternative for Windows
        readline = Readline()
    except ImportError:
        import pyreadline as readline
        import warnings
        warnings.warn("pyreadline may have problems in Python 3.10+, install pyreadline3")

from src.models import utils

class VersioningShell:
    def __init__(self):
        self.history_file = os.path.expanduser("~/.vcs_shell")
        self.current_directory = os.getcwd()
        self.readline = None
        self.setup_readline()
        self.metadata_file = "dummy_metadata.json"
        self.__verify_path_existence()
        
    def __verify_path_existence(self) -> None:
        """
        Verifies if the metadata file exists in the current directory.
        If it does not exist, it initializes the metadata by calling `set_metadata`.
        """
        if not os.path.exists(os.path.join(self.current_directory, self.metadata_file)):
            self.set_metadata()
            
    def set_metadata(self) -> None:
        """
        Creates a new metadata file with base metadata and stages it in Git.
        """
        base_metadata = utils.BaseMetaData
        
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='w') as f:
            json.dump(base_metadata, f, indent=4)
            
        self.__add_staging_to_git()
            
    def __add_staging_to_git(self) -> None:
        """
        Adds all changes in the current directory to the Git staging area.
        """
        subprocess.run(args=['git', 'add'], 
                        cwd=self.current_directory)
        
    def setup_readline(self) -> None:
        """
        Configures the `readline` library for command-line history and autocompletion.
        Loads the command history from a file and sets up a completer for commands.
        """
        if os.path.exists(self.history_file):
            try:
                readline.read_history_file(self.history_file)
            except Exception:
                open(self.history_file, 'a').close()
        
        atexit.register(self.save_command_history)
        
        readline.set_history_length(1000)
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self.command_completer)
        
    def save_command_history(self) -> None:
        """
        Saves the command history to a file when the program exits.
        Handles exceptions if the file cannot be written.
        """
        try:
            readline.write_history_file(self.history_file)
        except Exception as e:
            print(f"\033[33mWarning: Could not save command history: {str(e)}\033[0m")
            
    def command_completer(self, text, state) -> List[str] | None:
        """
        Provides autocompletion for commands based on the input text.
        Returns a list of matching commands or `None` if no matches are found.
        """
        commands = utils.GitCommands.COMMANDS_TO_COMPLETE.value
        
        options = [cmd for cmd in commands if cmd.startswith(text)]
        if state < len(options):
            return options[state]
        return None
    
    def display_prompt(self) -> str:
        try:
            git_root_cmd = ["git", "rev-parse", "--show-toplevel"]
            branch_cmd = ["git", "branch", "--show-current"]
            
            git_root = subprocess.check_output(
                git_root_cmd,
                stderr=subprocess.PIPE,
                cwd=self.current_directory,
                text=True,
                shell=True  # Necessary for Windows compatibility
            ).strip()
            
            repository_name = os.path.basename(git_root)
            
            branch = subprocess.check_output(
                branch_cmd,
                stderr=subprocess.PIPE,
                cwd=self.current_directory,
                text=True,
                shell=True 
            ).strip()
            
            return f"\033[32m{repository_name}\033[0m:\033[34m{branch}\033[0m (med-git) $ "
        
        except subprocess.CalledProcessError:
            # If it is not a git repository or the command fails
            return f"\033[31m{os.getcwd()}\033[0m (no repository) $ "
        except Exception as e:
            # Catch any other exceptions and print a warning message
            print(f"\033[33mWarning: Prompt error - {str(e)}\033[0m")
            return "> "
    
    def register_original_image(self, image_file, patient_id, study_info) -> str | None:
        """
        Registers an original medical image in the metadata file.
        Computes a unique ID for the image, stores its metadata, and stages the changes in Git.
        """
        if not os.path.exists(image_file):
            print(f"\033[31mError: File {image_file} not found\033[0m")
            return
        
        with open(file= os.path.join(self.current_directory, self.metadata_file), mode='r') as f:
            metadata = json.load(f)
            
        original_id = f"ORIG_{patient_id}_{datetime.now().strftime('%Y%m%d%H%M')}"
            
        metadata['original_images'][original_id] = {
            'file': image_file,
            'patient_id': patient_id,
            'study_info': study_info, 
            'timestamp': datetime.now().isoformat(),
            'hash': subprocess.check_output(['git', 'hash-object', image_file]).decode().strip()
        }
        
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='w') as f:
            json.dump(metadata, f, indent=4)
        
        subprocess.run(['git', 'add', image_file, self.metadata_file], cwd= self.current_directory)
        
        print(f"\033[32mOriginal image registered as {original_id}\033[0m")
        
        return original_id
        
    def register_derivatives_images(self, original_id, segmentation_file, description, method= "") -> str | None:
        """
        Registers a derived segmentation image in the metadata file.
        Links it to the original image, stores its metadata, and stages the changes in Git.
        """
        if not os.path.exists(segmentation_file):
            print(f"\033[31mError: File {segmentation_file} not found\033[0m")
            return
        
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='r') as f:
            metadata= json.load(f)
            
        if original_id not in metadata['original_images']:
            print(f"\033[31mError: Original ID {original_id} not found\033[0m")
            return
        
        patient_id = metadata['original_images'][original_id]['patient_id']
        
        version_id = f"SEG_{original_id}_{len(metadata['versions']) + 1}"
        
        if original_id not in metadata['derivatives']:
            metadata['derivatives'][original_id] = []
            
        metadata['derivatives'][original_id].append(version_id)
        
        metadata['versions'][version_id] = {
            'original_id': original_id,
            'file': segmentation_file,
            'patient_id': patient_id,
            'description': description,
            'method': method,
            'timestamp': datetime.now().isoformat(),
            'hash': subprocess.check_output(['git', 'hash-object', segmentation_file]).decode().strip()
        }
        
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='w') as f:
            json.dump(metadata, f, indent=4)
            
        subprocess.run(['git', 'add', segmentation_file, self.metadata_file], cwd=self.current_directory)
        
        print(f"\033[32mSegmentation registered as {version_id} derives from {original_id}\033[0m")
        
        return version_id
        
    def show_derivatives_images(self, original_id):
        """
        Registers a derived segmentation image in the metadata file.
        Links it to the original image, stores its metadata, and stages the changes in Git.
        """
        with open(os.path.join(self.current_directory, self.metadata_file), 'r') as f:
            metadata = json.load(f)
            
        if original_id not in metadata['original_images']:
            print(f"\033[31mError: Original ID {original_id} not found\033[0m")
            return
        
        print(f"""
            Original image: {original_id}
            File: {metadata['original_images'][original_id]['file']}
            Patient: {metadata['original_images'][original_id]['patient_id']}
            Derivatives segmentations:
            {'-' * 50}    
            """)
        
        if original_id in metadata['derivatives']:
            for segmentation_id in metadata['derivatives'][original_id]:
                segmentation_data = metadata['versions'][segmentation_id]
                print(f"""
                    ID: {segmentation_id}
                    File: {segmentation_data['file']}
                    Method: {segmentation_data.get('method', 'N/A')}
                    Description: {segmentation_data['description']}
                    Date: {segmentation_data['timestamp']}
                    {'-' * 50}
                    """)
                
        else:
            print("There are no registered segmentations for this image")
            
    
    def show_patient_tree(self, patient_id):
        """
        Displays a version tree for a specific patient.
        Lists all original images and their derived segmentations, grouped by patient ID.
        """
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='r') as f:
            metadata = json.load(f)
            
        print(f"""
            Version tree for patient {patient_id}:
            {'=' * 60}
            """)
        
        originals = {
            key: value for key, value in metadata['original_images'].items() if value['patient_id'] == patient_id
        }
        
        if not originals:
            print('No original images were found for this patient')
            return
        
        for original_id, original_data in originals.items():
            print(f"""
                Original Image: {original_id}
                Study: {original_data['study_info']}
                File: {original_data['file']}
                Date: {original_data['timestamp']}
                """)
            
            if original_id in metadata['derivatives']:
                print("\n  Derived segmentations:")
                for segmentation_id in metadata['derivatives'][original_id]:
                    segmentation_data = metadata['versions'][segmentation_id]
                    print(f"""
                            - {segmentation_id}: {segmentation_data['description']}
                            Method: {segmentation_data.get('method', 'N/A')}
                            File: {segmentation_data['file']}
                        """)
                    
            else:
                print("\n There are no derived segmentations recorded")
                
            print('-' * 50)
            
    def compare_versions(self, version1, version2, output_file=None):
        """
        Compares two segmentation versions by analyzing their voxel data.
        Calculates the number of differing voxels and similarity percentage.
        Optionally writes the comparison report to a file.
        """
        with open(file=os.path.join(self.current_directory, self.metadata_file), mode='r') as f:
            metadata = json.load(f)
            
        if (version1 or version2) not in metadata['versions']:
            print("\033[31mError: One or both versions do not exist\033[0m")
            return
        
        file1 = metadata['versions'][version1]['file']
        file2 = metadata['versions'][version2]['file']
        
        try:
            image1 = nib.load(file1).get_fdata()
            image2 = nib.load(file2).get_fdata()
            
            diff = np.sum(image1 != image2)
            total_voxels = image1.size
            similarity = 1 - (diff / total_voxels)
            
            report = f"""
                Comparation between {version1} and {version2}
                {'-' * 30}
                Different voxels: {diff} of {total_voxels}
                Similarity: {similarity:.2%}
                
                Metadata {version1}:
                - Patient: {metadata['versions']}{[version1]}{['patient_id']}
                - Description: {metadata['versions'][version1]['description']}
                - Date: {metadata['versions'][version1]['timestamp']}
                
                Metadata {version2}:
                - Patient: {metadata['versions'][version2]['patient_id']}
                - Description: {metadata['versions'][version2]['description']}
                - Date: {metadata['versions'][version2]['timestamp']}
            """
            
            print(report)
            
            if output_file:
                with open(file=output_file, mode='w') as f:
                    f.write(report)
                print()
        except Exception as e:
            print(f"\033[31mError comparing versions: {str(e)}\033[0m")
            
    def show_history(self) -> None:
        """
        Displays the Git commit history and registered versions from the metadata file.
        """
        try:
            log = subprocess.check_output([
                                            'git',
                                            'log',
                                            '--pretty=format:%h - %an, %ar : %s'
                                        ], cwd=self.current_directory).decode('utf-8')
            
            print("\nCommit history:")
            print(log)
            
            with open(file=os.path.join(self.current_directory, self.metadata_file), mode='r') as f:
                metadata = json.load(f)
                
            print("\nRegistered versions:")
            for version, data in metadata['versions'].items():
                print(f"{version}: {data['patient_id']} - {data['description']}")
                
        except subprocess.CalledProcessError as e:
            print(f"\033[31mError getting history:\033[0m {e.stderr.decode().strip()}")
            
        except Exception as e:
            print(f"\033[31mError:\033[0m {str(e)}")
            
    def show_help(self) -> None:
        """
        Prints a help message listing all available commands and their usage.
        """
        help_text = """
            Medical Version Control Shell - Commands:
            
            IMAGE REGISTRATION:
            register-original <image_file> <patient_id> "<study_info>" - Register original medical image
            register-derivative <original_id> <seg_file> "<desc>" [method] - Register derived segmentation
            
            VERSION MANAGEMENT:
            compare <version1> <version2> [output_file] - Compare two segmentations
            show-derivatives <original_id> - Show all segmentations from an original image
            show-patient-tree <patient_id> - Show complete version tree for a patient
            
            INFORMATION:
            history - Show commit history with medical versions
            help - Show this help message
            
            STANDARD GIT COMMANDS:
            All standard Git commands are supported (status, commit, push, pull, etc.)
            """
        print(help_text)
            
    def execute_command(self, command: str) -> None:
        """
        Parses and executes user commands entered in the shell.
        Supports both custom commands and standard Git commands.
        """
        try:
            command_parts = command.split()
            if not command_parts:
                return
            
            cmd = command_parts[0].lower()
            
            if cmd == 'init' and len(command_parts) == 1:
                # git init without arguments
                self._execute_git_command(['init'])
                return
                
            elif cmd == 'git' and len(command_parts) > 1:
                # When 'git <command>' is written
                self._execute_git_command(command_parts[1:])
                return
                
            # Personalized commands
            elif cmd == 'register-original':
                if len(command_parts) < 4:
                    print("Usage: register-original <image_file> <patient_id> \"<study_info>\"")
                    return
                self.register_original_image(command_parts[1], command_parts[2], " ".join(command_parts[3:]))
                
            elif cmd == 'register-derivative':
                if len(command_parts) < 4:
                    print("Usage: register-derivative <original_id> <segmentation_file> \"<description>\" [method]")
                    return
                method = command_parts[4] if len(command_parts) > 4 else ""
                self.register_derivatives_images(command_parts[1], command_parts[2], " ".join(command_parts[3:4]), method)
                
            elif cmd == 'compare':
                if len(command_parts) < 3:
                    print("Usage: compare <version1> <version2> [output_file]")
                    return
                output_file = command_parts[3] if len(command_parts) > 3 else None
                self.compare_versions(command_parts[1], command_parts[2], output_file)
                
            elif cmd == 'show-derivatives':
                if len(command_parts) < 2:
                    print("Usage: show-derivatives <original_id>")
                    return
                self.show_derivatives_images(command_parts[1])
                
            elif cmd == 'show-patient-tree':
                if len(command_parts) < 2:
                    print("Usage: show-patient-tree <patient_id>")
                    return 
                self.show_patient_tree(command_parts[1])
                
            elif cmd == 'history':
                self.show_history()
                
            elif cmd == 'help':
                self.show_help()
                
            else:
                # Try to execute as a standard git command (without 'git' prefix)
                self._execute_git_command(command_parts)
                
        except SystemExit:
            raise
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode().strip() if e.stderr else str(e)
            print(f"\033[31mError: {error_msg}\033[0m")
        except FileNotFoundError as e:
            print(f"\033[31mError: File not found - {str(e)}\033[0m")
        except KeyError as e:
            print(f"\033[31mError: ID not found in metadata - {str(e)}\033[0m")
        except Exception as e:
            print(f"\033[31mUnexpected error: {str(e)}\033[0m")

    def _execute_git_command(self, git_args: list): 
        """
        Executes a Git command with the provided arguments.
        Handles errors and displays appropriate messages if the command fails.
        """
        try:
            # Special case for 'git commit' command
            if len(git_args) > 0 and git_args[0] == 'commit':
                # Check if the commit message is provided
                message = ' '.join(git_args[2:]) if '-m' in git_args else ''
                commit_cmd = ['git', 'commit', '-m', message]
                result = subprocess.run(
                    commit_cmd,
                    cwd=self.current_directory,
                    shell=True,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
            else:
                # Normal git commands
                result = subprocess.run(
                    ['git'] + git_args,
                    cwd=self.current_directory,
                    shell=True,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
            if result.stdout:
                print(result.stdout.strip())
                
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            print(f"\033[31mGit error: {error_msg}\033[0m")
        except FileNotFoundError:
            print("\033[31mError: Git is not installed or not in PATH\033[0m")
            
    def run(self) -> None:
        """
        Starts the interactive shell for the medical version control system.
        Continuously prompts the user for input and executes commands until the user exits.
        """
        print("Medical Version Control Interactive Shell")
        print("Type 'help' for available commands, 'exit' or 'quit' to exit\n")
        
        while True:
            try: 
                user_input = input(self.display_prompt()).strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['exit', 'quit']:
                    print("Exiting Medical Version Control Interactive Shell...")
                    break
                
                if user_input.lower() == 'cd':
                    print(f"Current directory: {os.getcwd()}")
                    continue
                elif user_input.lower().startswith('cd '):
                    new_directory = user_input[3:].strip()
                    try:
                        os.chdir(new_directory)
                        self.current_directory = os.getcwd()
                    except Exception as e:
                        print(f"\033[31mError changing directory:\033[0m {str(e)}")
                    continue
                
                self.execute_command(user_input)
                
            except KeyboardInterrupt:
                print("\nUse 'exit' or 'quit' to exit")
                continue
            
            except EOFError:
                print("\nExiting...")
                break
            
if __name__ == "__main__":
    shell = VersioningShell()
    shell.run()