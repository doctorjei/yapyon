"""Execute the guide's complete safe-file workflow as well as its doctests."""

import errno
from pathlib import Path
import re
import sys

import pytest


GUIDE = Path(__file__).resolve().parent.parent / "docs" / "DETAILS.md"


def test_complete_safe_file_guide_example(capsys):
    text = GUIDE.read_text(encoding="utf-8")
    blocks = [block for block in re.findall(r"```python\n(.*?)\n```", text, re.S)
              if "TemporaryDirectory" in block and "dump_safe(" in block]
    assert len(blocks) == 1
    code = compile(blocks[0], str(GUIDE), "exec")
    if sys.platform == "linux":
        exec(code, {})
        assert capsys.readouterr() == ("{'port': 8080}\n", "")
    else:
        with pytest.raises(OSError) as caught:
            exec(code, {})
        assert caught.value.errno == errno.ENOTSUP
