import subprocess
import sys
from unittest.mock import Mock

import pytest
import run


def test_pipeline_failure_prevents_server(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['run.py'])
    popen = Mock(return_value=Mock(wait=Mock(return_value=1), poll=Mock(return_value=1)))
    monkeypatch.setattr(run.subprocess, 'Popen', popen)
    with pytest.raises(SystemExit):
        run.main()
    assert popen.call_count == 1


def test_success_uses_absolute_paths_and_same_python(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['run.py'])
    popen = Mock(return_value=Mock(wait=Mock(return_value=0), poll=Mock(return_value=0)))
    monkeypatch.setattr(run.subprocess, 'Popen', popen)
    run.main()
    first, second = [call.args[0] for call in popen.call_args_list]
    assert first[0] == second[0] == sys.executable
    assert second[1:4] == ['-m', 'streamlit', 'run']
    assert all(run.Path(first[first.index(arg) + 1]).is_absolute() for arg in ['--data', '--out', '--edges-export'])


def test_interrupt_terminates_and_waits_for_child(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['run.py'])
    child = Mock(wait=Mock(side_effect=[KeyboardInterrupt(), 0]), poll=Mock(return_value=None))
    monkeypatch.setattr(run.subprocess, 'Popen', Mock(return_value=child))
    run.main()
    if run.os.name == 'nt':
        child.send_signal.assert_called_once_with(run.signal.CTRL_BREAK_EVENT)
    else:
        child.terminate.assert_called_once()
    assert child.wait.call_count == 2
