import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
from argparse import ArgumentParser, HelpFormatter
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

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
        """Execute ``pip`` with the provided arguments."""

        pip_arguments = list(args)

        if getattr(sys, 'frozen', False):
                python_executable = locate_python_interpreter(require_console = True)
                exit_code = subprocess.call([ python_executable, '-m', 'pip', *pip_arguments ])
        else:
                try:
                        from pip._internal.cli.main import main as pip_main  # type: ignore
                except Exception:  # pragma: no cover - best effort fallback
                        python_executable = locate_python_interpreter(require_console = True)
                        exit_code = subprocess.call([ python_executable, '-m', 'pip', *pip_arguments ])
                else:
                        exit_code = pip_main(pip_arguments)

        if exit_code != 0:
                raise InstallerError('pip 执行失败 (退出代码 {code})。'.format(code = exit_code))


def locate_python_interpreter(require_console : bool = False) -> str:
        """Return a Python interpreter path suitable for launching FaceFusion."""

        candidates = []
        if is_windows():
                conda_python = os.path.join(os.getenv('CONDA_PREFIX', ''), 'python.exe')
                python_console = shutil.which('python')
                python_windowless = shutil.which('pythonw')

                if require_console:
                        candidates.extend([ conda_python, python_console, python_windowless ])
                else:
                        candidates.extend([ conda_python, python_windowless, python_console ])
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


def _augment_path_for_conda(conda_prefix : str) -> None:
        path_entries = []

        if is_windows():
                path_entries.extend(
                [
                        os.path.join(conda_prefix, 'condabin'),
                        os.path.join(conda_prefix, 'Scripts'),
                        os.path.join(conda_prefix, 'Library', 'bin'),
                        conda_prefix
                ])
        else:
                path_entries.extend(
                [
                        os.path.join(conda_prefix, 'bin'),
                        conda_prefix
                ])

        current_path = os.environ.get('PATH', '')
        path_parts = current_path.split(os.pathsep) if current_path else []

        for entry in path_entries:
                if entry and os.path.exists(entry) and entry not in path_parts:
                        path_parts.insert(0, entry)

        os.environ['PATH'] = os.pathsep.join(path_parts)


def _resolve_conda_executable(conda_prefix : Path) -> str:
        if is_windows():
                candidates = [ conda_prefix / 'condabin' / 'conda.bat', conda_prefix / 'Scripts' / 'conda.exe' ]
        else:
                candidates = [ conda_prefix / 'bin' / 'conda' ]

        for candidate in candidates:
                if candidate.exists():
                        return str(candidate)

        raise InstallerError('未能找到 Conda 可执行文件。')


def _determine_miniconda_spec() -> Tuple[str, str]:
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == 'windows':
                return ('Miniconda3-latest-Windows-x86_64.exe', '.exe')
        if system == 'darwin':
                if machine in ('arm64', 'aarch64'):
                        return ('Miniconda3-latest-MacOSX-arm64.sh', '.sh')
                return ('Miniconda3-latest-MacOSX-x86_64.sh', '.sh')
        if system == 'linux':
                if machine in ('aarch64', 'arm64'):
                        return ('Miniconda3-latest-Linux-aarch64.sh', '.sh')
                return ('Miniconda3-latest-Linux-x86_64.sh', '.sh')

        raise InstallerError('当前平台暂不支持自动安装 Conda。')


def _download_miniconda_installer(filename : str, suffix : str) -> Path:
        url = 'https://repo.anaconda.com/miniconda/' + filename
        fd, temp_path = tempfile.mkstemp(suffix = suffix)
        os.close(fd)
        installer_path = Path(temp_path)

        try:
                with urllib.request.urlopen(url) as response, installer_path.open('wb') as output:
                        shutil.copyfileobj(response, output)
        except Exception as error:
                installer_path.unlink(missing_ok = True)
                raise InstallerError('下载 Conda 安装程序失败。') from error

        return installer_path


def _install_miniconda() -> Tuple[str, str]:
        filename, suffix = _determine_miniconda_spec()
        installer_path = _download_miniconda_installer(filename, suffix)
        target_prefix = Path.home() / 'facefusion-conda'
        target_prefix.parent.mkdir(parents = True, exist_ok = True)

        try:
                if target_prefix.exists():
                        shutil.rmtree(target_prefix)

                if is_windows():
                        exit_code = subprocess.call(
                                [
                                        str(installer_path),
                                        '/InstallationType=JustMe',
                                        '/RegisterPython=0',
                                        '/AddToPath=0',
                                        '/S',
                                        '/D={target}'.format(target = str(target_prefix))
                                ]
                        )
                else:
                        installer_path.chmod(0o755)
                        exit_code = subprocess.call(
                                [
                                        'bash',
                                        str(installer_path),
                                        '-b',
                                        '-u',
                                        '-p',
                                        str(target_prefix)
                                ]
                        )
        finally:
                installer_path.unlink(missing_ok = True)

        if exit_code != 0:
                raise InstallerError('自动安装 Conda 失败 (退出代码 {code})。'.format(code = exit_code))

        return str(target_prefix), _resolve_conda_executable(target_prefix)


def _ensure_conda_command() -> Tuple[Optional[str], Optional[str]]:
        conda_prefix = os.environ.get('CONDA_PREFIX')
        if conda_prefix and os.path.exists(conda_prefix):
                try:
                        conda_executable = _resolve_conda_executable(Path(conda_prefix))
                except InstallerError:
                        conda_executable = shutil.which('conda')
                else:
                        return conda_prefix, conda_executable

        conda_executable = shutil.which('conda')
        if conda_executable:
                try:
                        base_output = subprocess.check_output([ conda_executable, 'info', '--base' ], text = True)
                except Exception as error:
                        raise InstallerError('无法确定 Conda 安装路径。') from error
                conda_prefix = base_output.strip().splitlines()[-1].strip()
                if not conda_prefix or not os.path.exists(conda_prefix):
                        raise InstallerError('无法确定 Conda 安装路径。')
                return conda_prefix, conda_executable

        return None, None


def ensure_conda_environment(skip_conda : bool) -> Optional[str]:
        existing_prefix, _ = _ensure_conda_command()

        if existing_prefix and os.path.exists(existing_prefix):
                os.environ['CONDA_PREFIX'] = existing_prefix
                _augment_path_for_conda(existing_prefix)
                return existing_prefix

        if skip_conda:
                return None

        installation_prefix, conda_executable = _install_miniconda()
        os.environ['CONDA_PREFIX'] = installation_prefix
        _augment_path_for_conda(installation_prefix)

        try:
                base_output = subprocess.check_output([ conda_executable, 'info', '--base' ], text = True)
        except Exception as error:
                raise InstallerError('Conda 安装完成，但无法确定安装路径。') from error

        conda_prefix = base_output.strip().splitlines()[-1].strip() or installation_prefix
        if not os.path.exists(conda_prefix):
                raise InstallerError('Conda 安装完成，但安装路径无效。')

        os.environ['CONDA_PREFIX'] = conda_prefix
        _augment_path_for_conda(conda_prefix)
        os.environ.setdefault('CONDA_DEFAULT_ENV', 'base')

        return conda_prefix


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

        conda_prefix = ensure_conda_environment(skip_conda)
        has_conda = bool(conda_prefix)
        onnxruntime_name, onnxruntime_version = ONNXRUNTIMES.get(onnxruntime_key)
        requirements_path = get_project_resource('requirements.txt')

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
