#!/usr/bin/env python3

import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from facefusion import installer

os.environ['SYSTEM_VERSION_COMPAT'] = '0'


class DesktopInstaller:
        def __init__(self, master : tk.Tk) -> None:
                self.master = master
                self.master.title('FaceFusion Environment Installer')
                self.master.resizable(False, False)

                self._set_window_icon()

                container = ttk.Frame(self.master, padding = 16)
                container.grid(row = 0, column = 0, sticky = 'nsew')

                self.master.columnconfigure(0, weight = 1)
                self.master.rowconfigure(0, weight = 1)

                ttk.Label(container, text = '选择需要安装的 ONNX Runtime 版本：').grid(row = 0, column = 0, sticky = 'w')

                self.runtime_var = tk.StringVar(value = self._default_runtime())
                runtime_values = list(installer.ONNXRUNTIMES.keys())
                self.runtime_combo = ttk.Combobox(container, textvariable = self.runtime_var, values = runtime_values, state = 'readonly', width = 18)
                self.runtime_combo.grid(row = 1, column = 0, sticky = 'ew', pady = (4, 12))

                self.skip_conda_var = tk.BooleanVar(value = False)
                ttk.Checkbutton(container, text = '跳过 Conda 环境检测', variable = self.skip_conda_var).grid(row = 2, column = 0, sticky = 'w')

                self.status_var = tk.StringVar(value = '点击“开始安装”以安装依赖环境。')
                self.status_label = ttk.Label(container, textvariable = self.status_var, wraplength = 320)
                self.status_label.grid(row = 3, column = 0, sticky = 'w', pady = (12, 8))

                self.install_button = ttk.Button(container, text = '开始安装', command = self.start_install)
                self.install_button.grid(row = 4, column = 0, sticky = 'ew')

                self.launch_button = ttk.Button(container, text = '启动 FaceFusion', command = self.launch_facefusion)
                self.launch_button.state(['disabled'])
                self.launch_button.grid(row = 5, column = 0, sticky = 'ew', pady = (8, 0))

                self.launch_process : Optional[subprocess.Popen[str]] = None

        def _set_window_icon(self) -> None:
                icon_path = installer.get_project_resource('facefusion.ico')
                if os.path.exists(icon_path):
                        try:
                                self.master.iconbitmap(icon_path)  # type: ignore[attr-defined]
                        except Exception:
                                pass

        def _default_runtime(self) -> str:
                runtimes = list(installer.ONNXRUNTIMES.keys())
                if 'default' in runtimes:
                        return 'default'
                if runtimes:
                        return runtimes[0]
                raise RuntimeError('No ONNX Runtime options available for this platform.')

        def start_install(self) -> None:
                onnxruntime_key = self.runtime_var.get()
                skip_conda = self.skip_conda_var.get()

                self.install_button.state(['disabled'])
                self.launch_button.state(['disabled'])
                self.status_var.set('正在安装依赖，请稍候……')

                threading.Thread(target = self._run_installation, args = (onnxruntime_key, skip_conda), daemon = True).start()

        def _run_installation(self, onnxruntime_key : str, skip_conda : bool) -> None:
                try:
                        installer.execute_install(onnxruntime_key, skip_conda)
                except installer.InstallerError as error:
                        self._report_failure(str(error) or '安装过程中出现错误。')
                except SystemExit as error:
                        message = '安装过程中出现错误。'
                        if isinstance(error.code, str):
                                message = error.code
                        elif isinstance(error.code, int) and error.code != 0:
                                message = '安装未完成 (退出代码 {code})。'.format(code = error.code)
                        self._report_failure(message)
                except Exception as error:
                        self._report_failure(str(error) or '安装过程中出现未知错误。')
                else:
                        self._report_success()

        def _report_success(self) -> None:
                def callback() -> None:
                        self.install_button.state(['!disabled'])
                        self.launch_button.state(['!disabled'])
                        self.status_var.set('安装完成，您可以立即启动 FaceFusion。')
                        if messagebox.askyesno('安装完成', '依赖环境安装完成。是否现在启动 FaceFusion？'):
                                self.launch_facefusion()
                self.master.after(0, callback)

        def _report_failure(self, message : str) -> None:
                def callback() -> None:
                        self.install_button.state(['!disabled'])
                        self.launch_button.state(['disabled'])
                        self.status_var.set(message)
                        messagebox.showerror('安装失败', message)
                self.master.after(0, callback)

        def launch_facefusion(self) -> None:
                if self.launch_process and self.launch_process.poll() is None:
                        messagebox.showinfo('FaceFusion 已在运行', 'FaceFusion 已经启动，无需再次运行。')
                        return

                try:
                        python_executable = installer.locate_python_interpreter()
                except installer.InstallerError as error:
                        messagebox.showerror('无法启动 FaceFusion', str(error))
                        return

                facefusion_entry = installer.get_project_resource('facefusion.py')
                if not os.path.exists(facefusion_entry):
                        messagebox.showerror('无法启动 FaceFusion', '未找到 facefusion.py 入口脚本。')
                        return

                command = [ python_executable, facefusion_entry, 'run' ]
                try:
                        self.launch_process = subprocess.Popen(command)
                except OSError as error:
                        messagebox.showerror('无法启动 FaceFusion', str(error))
                else:
                        messagebox.showinfo('FaceFusion 已启动', 'FaceFusion 正在启动，您可以最小化此窗口。')


def main() -> None:
        root = tk.Tk()
        DesktopInstaller(root)
        root.mainloop()


if __name__ == '__main__':
        main()
