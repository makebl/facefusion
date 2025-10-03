import os
import shutil
import signal
import subprocess
import sys
import tempfile
from argparse import ArgumentParser, HelpFormatter
from pathlib import Path
from typing import Dict, Iterable, Tuple

from facefusion import metadata, wording
from facefusion.common_helper import is_linux, is_macos, is_windows

ONNXRUNTIMES : Dict[str, Tuple[str, str]] = {}

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_resource(*parts : str) -> str:
        """Return an absolute path to a project resource.

        When the installer is packaged with PyInstaller the project files are
        extracted to a temporary directory exposed via ``sys._MEIPASS``. In a
        normal source checkout we simply resolve paths relative to the project
        root.
        """

        base_path = getattr(sys, '_MEIPASS', PROJECT_ROOT)  # type: ignore[attr-defined]
        return str(Path(base_path).joinpath(*parts))


def run_pip(args : Iterable[str]) -> None:
        """Execute ``pip`` with the provided arguments.

        The helper attempts to reuse the in-process pip module when available so
        that PyInstaller builds remain self-contained. When the module cannot be
        imported we fall back to invoking the user's Python interpreter.
        """

        try:
                from pip._internal.cli.main import main as pip_main  # type: ignore
        except Exception as error:  # pragma: no cover - best effort fallback
                python_candidates = []
                if is_windows():
                        python_candidates.extend(
                        [
                                os.path.join(os.getenv('CONDA_PREFIX', ''), 'python.exe'),
                                shutil.which('pythonw'),
                                shutil.which('python')
                        ])
                else:
                        python_candidates.extend(
                        [
                                os.path.join(os.getenv('CONDA_PREFIX', ''), 'bin', 'python3'),
                                shutil.which('python3'),
                                shutil.which('python')
                        ])
                python_candidates.append(sys.executable)
                python_executable = next(
                        (candidate for candidate in python_candidates if candidate and os.path.exists(candidate)),
                        None
                )
                if not python_executable:
                        raise InstallerError('无法找到可用的 Python 或 pip 来安装依赖。') from error
                exit_code = subprocess.call([ python_executable, '-m', 'pip', *list(args) ])
        else:
                exit_code = pip_main(list(args))

        if exit_code != 0:
                raise InstallerError('pip 执行失败 (退出代码 {code})。'.format(code = exit_code))


def locate_python_interpreter() -> str:
        """Return a Python interpreter path suitable for launching FaceFusion."""

        candidates = []
        if is_windows():
                candidates.extend(
                [
                        os.path.join(os.getenv('CONDA_PREFIX', ''), 'python.exe'),
                        shutil.which('pythonw'),
                        shutil.which('python')
                ])
        else:
                candidates.extend(
                [
                        os.path.join(os.getenv('CONDA_PREFIX', ''), 'bin', 'python3'),
                        shutil.which('python3'),
                        shutil.which('python')
                ])
        if not getattr(sys, 'frozen', False):  # pragma: no branch - simple check
                candidates.append(sys.executable)

        for candidate in candidates:
                if candidate and os.path.exists(candidate):
                        return str(candidate)

        raise InstallerError('未能定位可用于启动 FaceFusion 的 Python 解释器。')

# Importing ``pip`` as a top-level dependency ensures PyInstaller bundles it when
# we package the desktop installer. The module is only referenced indirectly via
# ``run_pip`` below.
try:  # pragma: no cover - defensive import for packaging environments
        import pip  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover - pip may be unavailable during linting
        pip = None


class InstallerError(RuntimeError):
        pass


if is_macos():
        ONNXRUNTIMES['default'] = ('onnxruntime', '1.19.2')
else:
        ONNXRUNTIMES['default'] = ('onnxruntime', '1.19.2')
        ONNXRUNTIMES['cuda'] = ('onnxruntime-gpu', '1.19.2')
        ONNXRUNTIMES['openvino'] = ('onnxruntime-openvino', '1.19.0')
if is_linux():
        ONNXRUNTIMES['rocm'] = ('onnxruntime-rocm', '1.18.0')
if is_windows():
        ONNXRUNTIMES['directml'] = ('onnxruntime-directml', '1.17.3')


def cli() -> None:
        signal.signal(signal.SIGINT, lambda signal_number, frame: sys.exit(0))
        program = ArgumentParser(formatter_class = lambda prog: HelpFormatter(prog, max_help_position = 50))
        program.add_argument('--onnxruntime', help = wording.get('help.install_dependency').format(dependency = 'onnxruntime'), choices = ONNXRUNTIMES.keys(), required = True)
        program.add_argument('--skip-conda', help = wording.get('help.skip_conda'), action = 'store_true')
        program.add_argument('-v', '--version', version = metadata.get('name') + ' ' + metadata.get('version'), action = 'version')
        run(program)


def run(program : ArgumentParser) -> None:
        args = program.parse_args()
        try:
                execute_install(args.onnxruntime, args.skip_conda)
        except InstallerError as error:
                message = str(error)
                if message:
                        sys.stdout.write(message + os.linesep)
                sys.exit(1)


def execute_install(onnxruntime_key : str, skip_conda : bool = False) -> None:
        if onnxruntime_key not in ONNXRUNTIMES:
                raise InstallerError('Unknown ONNX Runtime selection: ' + onnxruntime_key)

        has_conda = 'CONDA_PREFIX' in os.environ
        onnxruntime_name, onnxruntime_version = ONNXRUNTIMES.get(onnxruntime_key)
        requirements_path = get_project_resource('requirements.txt')

        if not skip_conda and not has_conda:
                raise InstallerError(wording.get('conda_not_activated') or 'Conda is not activated')

        run_pip([ 'install', '-r', requirements_path, '--force-reinstall' ])

        if onnxruntime_key == 'rocm':
                python_id = 'cp' + str(sys.version_info.major) + str(sys.version_info.minor)

                if python_id == 'cp310':
                        wheel_name = 'onnxruntime_rocm-' + onnxruntime_version + '-' + python_id + '-' + python_id + '-linux_x86_64.whl'
                        wheel_path = os.path.join(tempfile.gettempdir(), wheel_name)
                        wheel_url = 'https://repo.radeon.com/rocm/manylinux/rocm-rel-6.2/' + wheel_name
                        subprocess.call([ shutil.which('curl'), '--silent', '--location', '--continue-at', '-', '--output', wheel_path, wheel_url ])
                        run_pip([ 'uninstall', 'onnxruntime', wheel_path, '-y', '-q' ])
                        run_pip([ 'install', wheel_path, '--force-reinstall' ])
                        os.remove(wheel_path)
        else:
                run_pip([ 'uninstall', 'onnxruntime', onnxruntime_name, '-y', '-q' ])
                run_pip([ 'install', onnxruntime_name + '==' + onnxruntime_version, '--force-reinstall' ])

        if onnxruntime_key == 'cuda' and has_conda:
                library_paths = []

                if is_linux():
                        if os.getenv('LD_LIBRARY_PATH'):
                                library_paths = os.getenv('LD_LIBRARY_PATH').split(os.pathsep)

                        python_id = 'python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor)
                        library_paths.extend(
                        [
                                os.path.join(os.getenv('CONDA_PREFIX'), 'lib'),
                                os.path.join(os.getenv('CONDA_PREFIX'), 'lib', python_id, 'site-packages', 'tensorrt_libs')
                        ])
                        library_paths = [ library_path for library_path in library_paths if os.path.exists(library_path) ]

                        subprocess.call([ shutil.which('conda'), 'env', 'config', 'vars', 'set', 'LD_LIBRARY_PATH=' + os.pathsep.join(library_paths) ])

                if is_windows():
                        if os.getenv('PATH'):
                                library_paths = os.getenv('PATH').split(os.pathsep)

                        library_paths.extend(
                        [
                                os.path.join(os.getenv('CONDA_PREFIX'), 'Lib'),
                                os.path.join(os.getenv('CONDA_PREFIX'), 'Lib', 'site-packages', 'tensorrt_libs')
                        ])
                        library_paths = [ library_path for library_path in library_paths if os.path.exists(library_path) ]

                        subprocess.call([ shutil.which('conda'), 'env', 'config', 'vars', 'set', 'PATH=' + os.pathsep.join(library_paths) ])

        if onnxruntime_version < '1.19.0':
                run_pip([ 'install', 'numpy==1.26.4', '--force-reinstall' ])
        run_pip([ 'install', 'python-multipart==0.0.12', '--force-reinstall' ])
