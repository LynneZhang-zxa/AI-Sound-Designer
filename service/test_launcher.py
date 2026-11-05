import os
import signal
import subprocess
import unittest
from unittest.mock import patch
import launcher

class LauncherTests(unittest.TestCase):
    def test_restart_without_key_leaves_old_worker_running(self):
        with patch.dict(os.environ,{},clear=True),patch('launcher.os.kill') as kill:
            with self.assertRaises(RuntimeError):launcher.restart_ai({'service':'resonanca-prompt'})
            kill.assert_not_called()

    def test_restart_checks_identity_and_uses_normal_termination(self):
        result=subprocess.CompletedProcess([],0,stdout='12345\n',stderr='')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-not-a-key'}),patch('launcher.subprocess.run',return_value=result),patch('launcher.subprocess.check_output',return_value=f'python3 {launcher.ROOT}/service/server.py --provider openai'),patch('launcher.os.kill') as kill,patch('launcher.health',return_value=None):
            launcher.restart_ai({'service':'resonanca-prompt'});kill.assert_called_once_with(12345,signal.SIGTERM)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-not-a-key'}),patch('launcher.subprocess.run',return_value=result),patch('launcher.subprocess.check_output',return_value='other-service'),patch('launcher.os.kill') as kill:
            with self.assertRaises(RuntimeError):launcher.restart_ai({'service':'resonanca-prompt'})
            kill.assert_not_called()

    def test_old_analysis_worker_is_not_silently_reused_or_killed(self):
        with patch('launcher.sys.argv',['launcher']),patch('launcher.health',return_value={'service':'resonanca-analysis','matcher_version':2}),patch('launcher.subprocess.Popen') as spawn,patch('launcher.os.kill') as kill:
            self.assertEqual(launcher.main(),1)
            spawn.assert_not_called();kill.assert_not_called()
