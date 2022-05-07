# built-in libs
import json
import os
import copy
import shutil
import pickle
import hashlib
from EthereumClient import EthereumClient
from utils import bcolors, get_files, clear_text_color, unique


class DEGIT:

    def __init__(self):
        # defaults
        self.default_cache_file = os.path.normpath('./.degit')
        self.default_snapshot_dir = os.path.normpath('./.snapshot')
        self.default_init_branch = 'master'

        # use debug chain by default unless set in environment variable 'BLOCKCHAIN_URL'
        self.block_chain_url = os.environ.get('BLOCKCHAIN_URL', 'https://rpc.debugchain.net')
        self.block_chain_id = os.environ.get('BLOCKCHAIN_ID', 8348)
        self.db_url = os.environ.get('DB_URL', 'http://39.98.50.209:5145/')

        # init etherdata client
        self.client = EthereumClient()

        # get current repo state
        self.state = {}
        if os.path.exists(self.default_cache_file):
            with open(self.default_cache_file, 'rb') as f:
                self.state = pickle.load(f)

        # create snapshot directory
        if not os.path.exists(self.default_snapshot_dir):
            os.mkdir(self.default_snapshot_dir)

    def _init_check(self):
        if not self.state:
            raise Exception('The repository has not yet been initalized.')

    def _save_state(self):
        with open(self.default_cache_file, 'wb') as f:
            pickle.dump(self.state, f)

    def validate_and_persist(func):
        """To check if repo has been initalized before calling a function. Also persists state after the function call."""

        def inner1(self, *args, **kwargs):
            self._init_check()
            returned_values = func(self, *args, **kwargs)
            self._save_state()
            return returned_values

        return inner1

    def init(self, args):
        """Initialize repository with branch master if not already initialized."""
        if os.path.exists(self.default_cache_file):
            raise Exception('The current directory contains a repository that has already been initialized.')
        else:
            self.state = {
                "branch": {
                    self.default_init_branch: {'commit_history': []},
                },
                'name': args.repository_name[0],
                'head': self.default_init_branch,
                'remote_address': None,
                'remote_abi': None,
                'file_list': []}

            self._save_state()
            print('Initialized Repository. State file created in current directory.')

    def checkout(self):
        """Checkout a branch or commit base on user input."""
        pass

    def get_current_state(self):
        print(self.state)

    @validate_and_persist
    def branch(self, args):
        # switch branch should pull latest snapshot and overwrite any uncommitted changes
        """Create branch if not yet exists"""
        branch_name = args.branch_name[0]
        if branch_name in self.state:
            raise Exception(f'Branch {branch_name} already exists.')
        else:
            current_branch = self.state['head']
            self.state['branch'][branch_name] = self.state['branch'][current_branch]
            self.state['head'] = branch_name
    
    @validate_and_persist
    def list_branch(self):
        """List out existing branches if no branch name is given."""
        current_branch = self.state['head']
        for branch in self.state['branch']:
            if branch == current_branch:
                print('*' + branch)
            else:
                print(branch)

    @validate_and_persist
    def add(self, args):
        """
        python3 main.py add 2.txt -v

        stage_lists:           list - files going to stage
        staged_file_list:      list - staged files
        unstaged_file_list:    list - files not staged
        last_commit_file_list: list - files in latest commit
        snapshot_file_list:    list - file list in latest commit
        """
        stage_lists = args.file_list
        head = self.state['head']
        current_branch = self.state["branch"][head]
        if current_branch["commit_history"]:
            last_commit_file_list = current_branch["commit_history"][-1]["file_list"]
        else:
            last_commit_file_list = []

        # list the snapshot files.
        snapshot_file_list = self.state["file_list"]
        # list all files in all dir and sub_dir, and ommit ignored file
        unstaged_file_list = get_files(ommit=snapshot_file_list)
        # list the uncommitted, but staged files.
        staged_file_list = [file_path for file_path in snapshot_file_list if file_path not in last_commit_file_list]

        # find stage and unstage file.
        for file_path in stage_lists:
            if file_path in last_commit_file_list:
                unstaged_file_list.remove(file_path)
                continue
            elif file_path in unstaged_file_list:
                staged_file_list.append(file_path)
                unstaged_file_list.remove(file_path)
            else:
                if not os.path.exists(file_path):
                    raise Exception(f"{file_path} not found.")

        # remove duplicate and sort
        staged_file_list = sorted(unique(staged_file_list))
        unstaged_file_list = sorted(unique(unstaged_file_list))

        # print the staged and unstaged file list
        def stage_msg(start: str, file_list: list, color):

            msg = start
            for i in file_list:
                msg += f"\t{color}{i}\n"
            print(msg)
            clear_text_color()

        if args.v:
            stage_msg(f"Committed files:\n\n", last_commit_file_list, bcolors.ENDC)
        stage_msg(f"Staged files:\n\n", staged_file_list, bcolors.GREEN)
        # stage_msg(f"Unstaged files:\n\n", unstaged_file_list ,bcolors.RED)

        snapshot_file_list = unique(staged_file_list + last_commit_file_list)
        self.state["file_list"] = staged_file_list

    @validate_and_persist
    def commit(self):
        # generate local commit hash
        if len(self.state.get("file_list", [])) == 0:
            print("No files added")
            return

        self.state["file_list"] = sorted(self.state["file_list"])
        data = ""
        for file in self.state["file_list"]:
            f = open(file, 'r')
            data += f.read()
        hashfunc = hashlib.sha1()
        hashfunc.update(data.encode())
        commit_hash = hashfunc.hexdigest()
        snapshot_dir = os.path.join(self.default_snapshot_dir, commit_hash)
        if os.path.exists(snapshot_dir):
            print("commit hash already exists")
            return

        # Save snapshot locally
        os.makedirs(snapshot_dir)
        for file in self.state["file_list"]:
            dirname = os.path.dirname(file)
            if not os.path.exists(os.path.join(snapshot_dir, dirname)):
                os.makedirs(os.path.join(snapshot_dir, dirname))
            shutil.copyfile(file, os.path.join(snapshot_dir, file))

        snapshot_format = 'zip'
        package_path = self._save_archive(snapshot_dir, snapshot_format)
        head = self.state['head']
        self.state['branch'][head]['commit_history'].append({
            'file_id': None,
            'commit_hash': commit_hash,
            'snapshot_path': snapshot_dir + "." + snapshot_format,
            'is_push': False
        })

        print(f'Commit {commit_hash} was successful.')

    @validate_and_persist
    def push(self, args):
        '''
        create ether transaction
        upload [code files] to ETD ( return file id)
        writes [file id, previous, current commit hash] to transaction
        new transaction hash = hash(previous commit hash)
        previous and current commit acts like a linked list
        '''
        branch_name = args.branch_name[0]

        is_changes = False
        success_push = True
        tmp_state = copy.deepcopy(self.state)

        pushed_commit = []

        for i, commit in enumerate(tmp_state['branch'][branch_name]['commit_history']):
            if not commit["is_push"]:
                is_changes = True
                file_id = self.client.upload_file(file_path=commit["snapshot_path"])
                if file_id is not None:
                    commit['file_id'] = file_id
                    commit['is_push'] = True
                    pushed_commit.append(commit['commit_hash'])
                else:
                    success_push = False

        local_commit_hashes = [commit['commit_hash'] for commit in self.state['branch'][branch_name]['commit_history']]

        if not is_changes:
            print('No new commits to push')
            return

        # if push succeed
        if success_push:
            if not self.state['remote_address'] and not self.state['remote_abi']:
                tmp_state['remote_address'], tmp_state['remote_abi'] = self.client.create_repository(
                    self.state['name'])

            # download origin state
            remote_state = self.client.contract_getter('git_pull', name=self.state['name'])

            # if remote has just been created, the state will be empty string
            if remote_state is not None and remote_state != '':
                remote_state = json.loads(remote_state)

                if branch_name in remote_state['branch']:
                    # check if there is commit in origin BUT NOT IN local
                    remote_commit_hashes = [commit['commit_hash'] for commit in
                                            remote_state['branch'][branch_name]['commit_history']]

                    commit_exists_on_remote_but_not_local = list(set(remote_commit_hashes) - set(local_commit_hashes))

                    # if yes DENY push and ask for resolve conflicts
                    if len(commit_exists_on_remote_but_not_local) > 0:
                        raise Exception(
                            f'Branch {branch_name} on the origin has commits not in local. Please resolve conflicts.')

            # replace real state with temp state
            self.state = tmp_state

            # if no accept push to blockchain
            self.client.contract_setter('git_push', json.dumps(self.state), name=self.state['name'])
            print(f'Pushed commits "{",".join(pushed_commit)}" to repository "{self.state["name"]}".')

        else:
            print('Failed upload to blockchain')

    @validate_and_persist
    def pull(self):
        # update current snapshot file list by last commit plz
        remote_state = self.client.contract_getter('git_pull', name=self.state['name'])
        if remote_state is not None and remote_state != '':
            remote_state = json.loads(remote_state)
            # Download all commits
            download_hash = []
            for branch_name in remote_state['branch'].keys():
                for i, commit in enumerate(remote_state['branch'][branch_name]['commit_history']):
                    commit_hash = commit['commit_hash']
                    if not os.path.exists(os.path.join(self.default_snapshot_dir, commit_hash)): # Download new commit
                        file_id = commit['file_id']
                        download_path = os.path.join(self.default_snapshot_dir, commit_hash + '.zip')
                        self.client.download_file(file_id, download_path)
                        self._unarchive(download_path)
                        download_hash.append(commit_hash)
            
            if len(download_hash) == 0:
                print("Your repository is already up to date")
                return
            
            if self.state['head'] in remote_state['branch']:
                if len(remote_state['branch'][self.state['head']]['commit_history']) > 0:
                    # Replace your code by latest commit so you should stash your work first
                    latest_commit = remote_state['branch'][self.state['head']]['commit_history'][-1]
                    commit_hash = latest_commit['commit_hash']
                    print(f'Replace your repository by commit {commit_hash}')
                    for file in remote_state['file_list']:
                        src_file = os.path.join(self.default_snapshot_dir, commit_hash, file)
                        if os.path.exists(src_file):
                            shutil.copyfile(src_file, file)
                            
            remote_state['head'] = self.state['head']
            self.state = remote_state
            
        else:
            print("No history found")

    def stash(self):
        '''Temporary save your changes'''
        snapshot_dir = os.path.join(self.default_snapshot_dir, 'stash')
        if os.path.exists(snapshot_dir):
            print("Remove old stash")
            shutil.rmtree(snapshot_dir)

        os.makedirs(snapshot_dir)
        for file in self.state["file_list"]:
            dirname = os.path.dirname(file)
            if not os.path.exists(os.path.join(snapshot_dir, dirname)):
                os.makedirs(os.path.join(snapshot_dir, dirname))
            shutil.copyfile(file, os.path.join(snapshot_dir, file))

    def pop_stash(self):
        '''Restore your save'''
        snapshot_dir = os.path.join(self.default_snapshot_dir, 'stash')
        if not os.path.exists(snapshot_dir):
            print("No stash history found")
            return

        for file in self.state["file_list"]:
            if os.path.exists(os.path.join(snapshot_dir, file)):
                if not os.path.exists(os.path.dirname(file)) and os.path.dirname(file) != '':
                    os.makedirs(os.path.dirname(file))
                shutil.copyfile(os.path.join(snapshot_dir, file), file)
        
        shutil.rmtree(snapshot_dir)

    def logs(self):
        pass

    def _save_archive(self, path, format='zip'):
        package_path = shutil.make_archive(
            path,
            format,
            path
        )
        return package_path
    
    def _unarchive(self, zip_path):
        commit_hash = os.path.splitext(os.path.basename(zip_path))[0]
        extract_dir = os.path.join(self.default_snapshot_dir, commit_hash)
        if not os.path.exists(extract_dir):
            shutil.unpack_archive(
                zip_path,
                extract_dir,
                'zip'
            )

    # def _zip(self, files: list):
    #     # pack-up the files
    #     pass


if __name__ == '__main__':
    class ArgparseMimic:
        pass

    degit = DEGIT()

    mimic = ArgparseMimic()

    if os.path.exists('.degit'):
        os.remove('.degit')
    if os.path.exists('.ethclient'):
        os.remove('.ethclient')
    if os.path.exists('.snapshot'):
        import shutil
        shutil.rmtree('.snapshot', ignore_errors=True)

    setattr(mimic, 'repository_name', ['test'])
    degit.init(mimic)

    setattr(mimic, 'file_list', ['utils.py'])
    setattr(mimic, 'v', True)
    degit.add(mimic)

    degit.commit()

    setattr(mimic, 'branch_name', ['master'])
    degit.push(mimic)
