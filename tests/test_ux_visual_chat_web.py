"""Execute actual PAGE JS navigation/theme behavior and its existing regressions."""
from pathlib import Path
import shutil
import subprocess


def test_actual_web_navigation_and_theme_functions():
    node=shutil.which('node')
    assert node, 'Node is required for the embedded UI behavior checks'
    root=Path(__file__).resolve().parents[1]
    for name in ('ux_visual_chat_probe.cjs','web_navigation_probe.cjs'):
        result=subprocess.run([node,str(root/'tests'/name)],cwd=root,capture_output=True,text=True,timeout=25)
        assert result.returncode==0,result.stdout+'\n'+result.stderr
