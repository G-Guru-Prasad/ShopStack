import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools import audit


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git(args, cwd):
    subprocess.run(
        ['git', *args], cwd=cwd, check=True,
        capture_output=True, text=True,
        env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
             'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'},
    )


class CliTests(unittest.TestCase):
    def _run(self, argv, cwd=None):
        original = os.getcwd()
        original_root = audit.REPO_ROOT
        try:
            if cwd:
                os.chdir(cwd)
                audit.REPO_ROOT = Path(cwd).resolve()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = audit.main(argv)
            return rc, buf.getvalue()
        finally:
            os.chdir(original)
            audit.REPO_ROOT = original_root

    def test_no_block_returns_zero_even_with_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _git(['init', '-q', '-b', 'main'], cwd=tmp_path)
            shopstack = tmp_path / 'shopstack'
            shopstack.mkdir()
            (shopstack / 'broken.py').write_text(
                'def f(ids):\n'
                '    for pid in ids:\n'
                '        Product.objects.get(id=pid)\n'
            )
            _git(['add', '.'], cwd=tmp_path)
            _git(['commit', '-m', 'seed', '-q'], cwd=tmp_path)
            (shopstack / 'broken.py').write_text(
                'def f(ids):\n'
                '    for pid in ids:\n'
                '        Product.objects.get(id=pid)\n'
                '        Product.objects.filter(id=pid)\n'
            )
            rc, out = self._run(
                ['--diff', '--skip-coverage', '--no-block', '--format', 'terminal'],
                cwd=tmp_path,
            )
            self.assertEqual(rc, 0)
            self.assertIn('orm.n_plus_one', out)

    def test_blocking_returns_one_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _git(['init', '-q', '-b', 'main'], cwd=tmp_path)
            shopstack = tmp_path / 'shopstack'
            shopstack.mkdir()
            (shopstack / 'broken.py').write_text('# empty\n')
            _git(['add', '.'], cwd=tmp_path)
            _git(['commit', '-m', 'seed', '-q'], cwd=tmp_path)
            (shopstack / 'broken.py').write_text(
                'def f(ids):\n'
                '    for pid in ids:\n'
                '        Product.objects.get(id=pid)\n'
            )
            rc, _ = self._run(
                ['--diff', '--skip-coverage', '--format', 'terminal'],
                cwd=tmp_path,
            )
            self.assertEqual(rc, 1)

    def test_migration_files_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _git(['init', '-q', '-b', 'main'], cwd=tmp_path)
            mig_dir = tmp_path / 'shopstack' / 'stackapp' / 'migrations'
            mig_dir.mkdir(parents=True)
            (mig_dir / '0001_initial.py').write_text(
                'def f(ids):\n'
                '    for pid in ids:\n'
                '        Product.objects.get(id=pid)\n'
            )
            (tmp_path / 'shopstack' / 'stackapp' / '__init__.py').write_text('')
            rc, out = self._run(
                ['--all', '--skip-coverage', '--format', 'terminal'],
                cwd=tmp_path,
            )
            self.assertEqual(rc, 0)
            self.assertNotIn('orm.n_plus_one', out)


if __name__ == '__main__':
    unittest.main()
