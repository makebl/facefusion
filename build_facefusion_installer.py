#!/usr/bin/env python3
"""Build a standalone FaceFusion desktop installer executable."""

import os
import sys
from pathlib import Path


def main() -> None:
        try:
                from PyInstaller.__main__ import run as pyinstaller_run
        except ImportError as error:  # pragma: no cover - executed in packaging envs
                sys.stderr.write('未安装 PyInstaller，请先运行 "pip install pyinstaller"。' + os.linesep)
                raise SystemExit(1) from error

        project_root = Path(__file__).resolve().parent
        data_separator = ';' if os.name == 'nt' else ':'

        add_data = [
                f'{project_root / "requirements.txt"}{data_separator}.',
                f'{project_root / "facefusion.py"}{data_separator}.',
                f'{project_root / "facefusion.ini"}{data_separator}.',
                f'{project_root / "facefusion"}{data_separator}facefusion'
        ]

        args = [
                '--noconfirm',
                '--clean',
                '--onefile',
                '--windowed',
                f'--name=FaceFusionInstaller',
                f'--icon={project_root / "facefusion.ico"}'
        ]

        for data in add_data:
                args.extend(['--add-data', data])

        args.append(str(project_root / 'desktop_installer.py'))

        pyinstaller_run(args)


if __name__ == '__main__':
        main()
