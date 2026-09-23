from unittest.mock import patch
import run


def test_failed_pipeline_never_starts_ui():
    with patch('sys.argv', ['run.py']), patch.object(run, 'wait_for', return_value=7) as wait:
        assert run.main() == 7
        assert wait.call_count == 1


def test_launcher_uses_same_python_absolute_paths():
    with patch('sys.argv', ['run.py']), patch.object(run, 'wait_for', return_value=0) as wait:
        assert run.main() == 0
        pipeline, ui = [call.args[0] for call in wait.call_args_list]
        assert pipeline[0] == ui[0] == run.sys.executable
        assert run.Path(pipeline[3]).is_absolute()
        assert ui[1:4] == ['-m','streamlit','run']


def test_interrupt_reaps_child():
    with patch.object(run.subprocess, 'Popen') as popen:
        child = popen.return_value
        child.wait.side_effect = [KeyboardInterrupt, 0]
        assert run.wait_for(['example']) == 130
        child.terminate.assert_called_once()
        assert child.wait.call_count == 2
