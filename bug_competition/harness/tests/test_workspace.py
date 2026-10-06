"""Host export boundaries for untrusted action workspaces."""
import builtins
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bug_competition.harness import core, workspace as w


class WorkspaceExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mosslight-export-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'candidate.tar'
        self.destination = self.root / 'extracted'

    def make_archive(self, entries):
        with tarfile.open(self.archive, 'w', format=tarfile.GNU_FORMAT) as archive:
            for name, data, kind, mode in entries:
                member = tarfile.TarInfo(name)
                member.type, member.mode = kind, mode
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    member.linkname = data
                    stream = None
                elif kind == tarfile.REGTYPE:
                    member.size = len(data)
                    stream = io.BytesIO(data)
                else:
                    stream = None
                archive.addfile(member, stream)

    def unpack(self):
        return w.unpack(self.archive, self.destination, time.monotonic() + 5)

    def rejects(self, message):
        with self.assertRaisesRegex(w.ExportRejected, message):
            self.unpack()
        self.assertFalse(self.destination.exists(), 'validation must finish before extraction')

    def test_regular_files_and_hardlinks_are_copied_without_metadata_or_host_links(self):
        self.make_archive([('.', '', tarfile.DIRTYPE, 0o700),
                           ('./src', '', tarfile.DIRTYPE, 0o700),
                           ('./src/main.py', b'print(1)\n', tarfile.REGTYPE, 0o4755),
                           ('copy.py', './src/main.py', tarfile.LNKTYPE, 0o644)])
        self.assertEqual(self.unpack(), {})
        original, duplicate = self.destination/'src/main.py', self.destination/'copy.py'
        self.assertEqual(original.read_bytes(), duplicate.read_bytes())
        self.assertEqual(original.stat().st_mode & 0o7777, 0o755)
        self.assertEqual(duplicate.stat().st_mode & 0o7777, 0o644)
        self.assertNotEqual(original.stat().st_ino, duplicate.stat().st_ino)
        self.assertFalse(any(path.is_symlink() for path in self.destination.rglob('*')))

    def test_symlink_names_are_reported_without_extracting_anything(self):
        self.make_archive([('good.py', b'x', tarfile.REGTYPE, 0o644),
                           ('linked-dir', '/outside', tarfile.SYMTYPE, 0o777),
                           ('linked-dir/escape', b'x', tarfile.REGTYPE, 0o644),
                           ('dangling', '../../private', tarfile.SYMTYPE, 0o777)])
        self.assertEqual(self.unpack(), {'symlinks':['dangling','linked-dir']})
        self.assertFalse(self.destination.exists())

    def test_unsafe_paths_duplicates_and_file_ancestors_are_rejected(self):
        for names, message in [(['../outside'], 'unsafe path'), (['/outside'], 'unsafe path'),
                               (['x','./x'], 'duplicate'), (['x','x/nested'], 'directory'),
                               (['x' * 513], 'overlong')]:
            with self.subTest(names=names):
                self.make_archive([(name, b'x', tarfile.REGTYPE, 0o644) for name in names])
                self.rejects(message)

    def test_unsupported_and_unreadable_entries_are_rejected(self):
        for kind, mode, message in [(tarfile.FIFOTYPE,0o644,'regular files'),
                                     (tarfile.REGTYPE,0o000,'Unreadable')]:
            with self.subTest(kind=kind):
                self.make_archive([('item', b'x', kind, mode)])
                self.rejects(message)

    def test_hardlink_targets_and_expanded_size_are_validated(self):
        for target, kind in [('../outside',tarfile.REGTYPE), ('missing',tarfile.REGTYPE),
                              ('directory',tarfile.DIRTYPE)]:
            with self.subTest(target=target):
                self.make_archive([('directory','',tarfile.DIRTYPE,0o755),
                                   ('link',target,tarfile.LNKTYPE,0o644)])
                with self.assertRaises((w.ExportRejected,KeyError)):
                    self.unpack()
                self.assertFalse(self.destination.exists())
        self.make_archive([('original',b'123456',tarfile.REGTYPE,0o644),
                           ('copy','original',tarfile.LNKTYPE,0o644)])
        with patch.object(w,'WORKSPACE_BYTES',8):
            self.rejects('Expanded workspace')

    def test_sparse_and_huge_declared_files_are_rejected_before_reading_contents(self):
        member=tarfile.TarInfo('huge'); member.size=2**50; member.mode=0o644
        self.archive.write_bytes(member.tobuf(format=tarfile.GNU_FORMAT)+b'\0'*1024)
        self.rejects('64 MiB')
        member=tarfile.TarInfo('sparse'); member.type=tarfile.GNUTYPE_SPARSE; member.mode=0o644
        self.archive.write_bytes(member.tobuf(format=tarfile.GNU_FORMAT)+b'\0'*1024)
        self.rejects('Sparse')

    def test_archive_byte_limit_and_implicit_directories_count_towards_entry_limit(self):
        self.make_archive([('file',b'x',tarfile.REGTYPE,0o644)])
        with patch.object(w,'ARCHIVE_BYTES',100):
            self.rejects('archive exceeds')
        self.make_archive([('a/b/c/file',b'x',tarfile.REGTYPE,0o644)])
        with patch.object(w,'WORKSPACE_ENTRIES',3):
            self.rejects('4096 entries')
        self.make_archive([(str(index),b'x',tarfile.REGTYPE,0o644) for index in range(4)])
        with patch.object(w,'WORKSPACE_ENTRIES',3):
            self.rejects('4096 entries')

    def test_deadline_is_checked_before_validation_and_during_large_file_copy(self):
        self.make_archive([('large',b'x'*(2*1024*1024),tarfile.REGTYPE,0o644)])
        with self.assertRaisesRegex(TimeoutError,'validation deadline'):
            w.unpack(self.archive,self.destination,time.monotonic()-1)
        self.assertFalse(self.destination.exists())
        now=[0.0]
        extract=tarfile.TarFile.extractfile
        class AdvancingReader:
            def __init__(self, stream): self.stream=stream
            def __enter__(self): return self
            def __exit__(self,*args): self.stream.close()
            def read(self,size):
                now[0]=2.0
                return self.stream.read(size)
        with patch.object(w.time,'monotonic',side_effect=lambda:now[0]), \
             patch.object(tarfile.TarFile,'extractfile',lambda source,member:AdvancingReader(extract(source,member))):
            with self.assertRaisesRegex(TimeoutError,'extraction deadline'):
                w.unpack(self.archive,self.destination,1.0)
        self.assertEqual((self.destination/'large').stat().st_size,1024*1024)

    def test_capture_replaces_only_successful_complete_exports(self):
        tree=self.root/'action'; tree.mkdir(); (tree/'old').write_text('keep me')
        def download(name,target,seconds): shutil.copyfile(self.archive,target)
        self.make_archive([('new',b'saved',tarfile.REGTYPE,0o644)])
        with patch.object(w,'_download',side_effect=download):
            self.assertEqual(w.capture('container',tree,5),{})
        self.assertEqual([p.name for p in tree.iterdir()],['new'])
        for data in (b'not a tar file',b''):
            self.archive.write_bytes(data)
            with patch.object(w,'_download',side_effect=download):
                result=w.capture('container',tree,5)
            self.assertIn('workspace_rejected',result)
            self.assertEqual((tree/'new').read_text(),'saved')
        self.make_archive([('link','/elsewhere',tarfile.SYMTYPE,0o777)])
        with patch.object(w,'_download',side_effect=download):
            self.assertEqual(w.capture('container',tree,5),{'symlinks':['link']})
        self.assertEqual((tree/'new').read_text(),'saved')

    def test_download_limits_stop_and_reap_export_process(self):
        popen=subprocess.Popen
        processes=[]
        def run_script(script):
            def start(*args,**kwargs):
                child=popen([sys.executable,'-c',script],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                processes.append(child)
                return child
            return start
        for script,seconds,error in [('import time; time.sleep(30)',.05,TimeoutError),
                                      ('import sys,time; sys.stdout.buffer.write(b"x"*100000);sys.stdout.flush();time.sleep(30)',2,w.ExportRejected)]:
            with self.subTest(error=error), patch.object(w.subprocess,'Popen',side_effect=run_script(script)), \
                 patch.object(w,'ARCHIVE_BYTES',1024):
                start=time.monotonic()
                with self.assertRaises(error):
                    w._download('container',self.archive,seconds)
                self.assertLess(time.monotonic()-start,2)
                self.assertIsNotNone(processes[-1].poll())
        with patch.object(w.subprocess,'Popen') as start:
            with self.assertRaises(TimeoutError): w._download('container',self.archive,0)
            start.assert_not_called()

class ActionProcessCleanupTests(unittest.TestCase):
    def run_cleanup(self, snapshots, *, missing=False, unreadable=False):
        state={'scan':-1,'kills':0,'time':0.0}
        def processes(_):
            state['scan']+=1
            return ['1','900',*snapshots[min(state['scan'],len(snapshots)-1)]]
        def stop(*args):
            state['kills']+=1
            if missing: raise ProcessLookupError()
        def sleep(seconds): state['time']+=seconds
        class ProcPath:
            def __init__(self,path): self.path=path
            def __truediv__(self,part): return ProcPath(self.path+'/'+part)
            def read_text(self):
                pid=self.path.split('/')[-2]
                if pid=='1': return 'Uid: 0 0 0 0'
                if unreadable: raise PermissionError('metadata inaccessible')
                if self.path.endswith('/status'): return 'Name: fixture\nUid: 65534 65534 65534 65534'
                process_state=snapshots[min(state['scan'],len(snapshots)-1)][pid]
                return pid+' (name ) with parentheses) '+process_state+' 1 2 3'
        modules={'os':SimpleNamespace(getuid=lambda:65534,getpid=lambda:900,listdir=processes,kill=stop),
                 'time':SimpleNamespace(monotonic=lambda:state['time'],sleep=sleep),
                 'pathlib':SimpleNamespace(Path=ProcPath)}
        actual_import=builtins.__import__
        def import_module(name,*args,**kwargs):
            return modules[name] if name in modules else actual_import(name,*args,**kwargs)
        namespace={'__builtins__':dict(vars(builtins),__import__=import_module)}
        exec(w.FINISH_ACTION_PROGRAM,namespace)
        return state

    def test_new_child_requires_another_kill_and_two_stable_scans(self):
        result=self.run_cleanup([{'2':'S'}, {'2':'Z','3':'R'}, {'2':'Z','3':'Z'}, {'2':'Z','3':'Z'}])
        self.assertEqual(result['kills'],4)

    def test_no_survivors_is_safe_and_nondumpable_uid_does_not_use_proc_directory_owner(self):
        self.assertEqual(self.run_cleanup([{}],missing=True)['kills'],2)
        # UIDs are read from status; this fixture deliberately offers no stat API.
        self.assertEqual(self.run_cleanup([{'2':'Z'}])['kills'],2)

    def test_uninterruptible_or_unreadable_processes_fail_closed(self):
        with self.assertRaisesRegex(TimeoutError,'did not terminate'):
            self.run_cleanup([{'2':'D'}])
        with self.assertRaises(PermissionError):
            self.run_cleanup([{'2':'Z'}],unreadable=True)


# Explicit opt-in keeps ordinary unit runs independent of Docker availability.
@unittest.skipUnless(os.environ.get('MOSSLIGHT_DOCKER_TESTS') == '1', 'set MOSSLIGHT_DOCKER_TESTS=1 for real Docker export checks')
class DockerWorkspaceExportTests(unittest.TestCase):
    def test_accepted_entry_limit_can_be_loaded_into_the_next_action(self):
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='mosslight-docker-entry-boundary-') as folder:
            tree=Path(folder)/'tree'; tree.mkdir()
            executor=core.DockerShell(os.environ.get('MOSSLIGHT_TEST_IMAGE','docker.io/library/mosslight-tools:local'))
            try:
                create="python3 -c \"from pathlib import Path; [Path('item-'+str(i)).write_bytes(b'x') for i in range(4096)]\""
                first=executor.shell(tree,create,30)
                self.assertEqual(first['exit_code'],0,first)
                self.assertNotIn('workspace_rejected',first)
                self.assertEqual(len(list(tree.iterdir())),w.WORKSPACE_ENTRIES)
                inspect="python3 -c \"from pathlib import Path; print(len(list(Path('.').iterdir())))\""
                second=executor.shell(tree,inspect,30)
                self.assertEqual(second['exit_code'],0,second)
                self.assertNotIn('workspace_rejected',second)
                self.assertEqual(int(second['output'].strip()),w.WORKSPACE_ENTRIES)
            finally:
                executor.close()

    def test_tmpfs_edits_private_files_symlinks_and_background_writer(self):
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='mosslight-docker-export-') as folder:
            tree=Path(folder)/'tree'; tree.mkdir(); (tree/'input').write_text('seed')
            executor=core.DockerShell(os.environ.get('MOSSLIGHT_TEST_IMAGE','docker.io/library/mosslight-tools:local'))
            try:
                result=executor.shell(tree,"cat input; printf edited > result; chmod 600 result; mkdir nested; printf safe > nested/file",30)
                self.assertEqual(result['exit_code'],0)
                self.assertNotIn('workspace_rejected',result)
                self.assertEqual((tree/'result').read_text(),'edited')
                self.assertEqual((tree/'nested/file').read_text(),'safe')
                result=executor.shell(tree,'ln -s /etc/passwd escape; printf discarded > result',30)
                self.assertEqual(result.get('symlinks'),['escape'])
                self.assertEqual((tree/'result').read_text(),'edited')
                self.assertFalse((tree/'escape').is_symlink())
                captured=core.capture
                def capture_finished(name,tree,seconds):
                    inspect=['docker','exec','--user','65534:65534',name,'/usr/bin/stat','-c','%s','/workspace/growing']
                    before=subprocess.check_output(inspect,text=True,timeout=5).strip()
                    time.sleep(.12)
                    after=subprocess.check_output(inspect,text=True,timeout=5).strip()
                    self.assertEqual(before,after,'participant child kept writing during export')
                    self.assertGreater(int(before),0)
                    return captured(name,tree,seconds)
                commands=["(while true; do printf x >> growing; sleep .01; done) >/dev/null 2>&1 & sleep .1",
                          "(while true; do (printf x >> growing) & sleep .002; done) >/dev/null 2>&1 & sleep .1"]
                for command in commands:
                    with patch.object(core,'capture',side_effect=capture_finished):
                        result=executor.shell(tree,command,30)
                    self.assertEqual(result['exit_code'],0)
                    self.assertNotIn('workspace_rejected',result)
                    self.assertGreater((tree/'growing').stat().st_size,0)
            finally:
                executor.close()
            self.assertFalse(executor.active)


if __name__=='__main__':
    unittest.main()
