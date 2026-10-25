"""Desktop entry point; all validation is shared with the AI CLI."""
from pathlib import Path
import queue
import threading

try:
    from .mod_preflight import check_profile, load_profile, write_json
except ImportError:
    from mod_preflight import check_profile, load_profile, write_json


def format_result(report):
    status = {'passed': '通過', 'failed': '問題あり', 'incomplete': '検査が不完全'}
    lines = [f"事前検査：{status.get(report.get('auditStatus'), '未完了')}",
             'ゲーム実行検証：未実施',
             '範囲：MOD情報・選択したDefs/PatchesのXML構文。翻訳注入・Harmony・プレイは未検証。',
             f"経過時間：{report.get('elapsedSeconds', 0)} 秒",
             f"有効MOD：{len(report.get('activeMods', []))} 個"]
    for diagnostic in report.get('diagnostics', []):
        lines.append(f"[{diagnostic['code']}] {diagnostic['message']} {diagnostic.get('path', '')}")
    lines.extend('注意：' + warning for warning in report.get('warnings', []))
    if report.get('omittedDiagnostics'):
        lines.append(f"省略した診断：{report['omittedDiagnostics']} 件。詳細は入力を分けて確認してください。")
    return '\n'.join(lines)


def create_window(profile_path=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    window = tk.Tk()
    window.title('RimWorld MOD 事前検査')
    window.geometry('980x720')
    window.minsize(780, 580)

    class Desktop:
        def __init__(self):
            self.report = None
            self.profile_path = None
            self.messages = queue.Queue()
            panel = ttk.Frame(window, padding=16)
            panel.pack(fill='both', expand=True)
            ttk.Label(panel, text='MOD事前検査（静的検査）', font=('', 17, 'bold')).pack(anchor='w')
            ttk.Label(panel, text='同じ検査をLinux上のAIからも実行できます。ゲーム実行時の動作は別の検証です。').pack(anchor='w', pady=(4, 14))
            self.game = tk.StringVar()
            self.save = tk.StringVar()
            self.version = tk.StringVar(value='1.7')
            for label, variable in [('ゲームのフォルダ', self.game), ('保存先（Configフォルダの親）', self.save)]:
                row = ttk.Frame(panel)
                row.pack(fill='x', pady=4)
                ttk.Label(row, text=label, width=31).pack(side='left')
                ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
                ttk.Button(row, text='選択', command=lambda v=variable: self.choose(v)).pack(side='left', padx=(8, 0))
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text='ゲームのバージョン', width=31).pack(side='left')
            ttk.Entry(row, textvariable=self.version, width=10).pack(side='left')
            ttk.Label(row, text='例：1.7。実行ファイルの版を自動判定する値ではありません。').pack(side='left', padx=10)
            ttk.Label(panel, text='追加のMOD検索先（Workshopの content/294100 など。Data/ と Mods/ は自動検索）').pack(anchor='w', pady=(12, 3))
            self.roots = tk.Listbox(panel, height=4)
            self.roots.pack(fill='x')
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=4)
            ttk.Button(row, text='検索先を追加', command=self.add_root).pack(side='left')
            ttk.Button(row, text='選択行を削除', command=self.remove_root).pack(side='left', padx=6)
            ttk.Button(row, text='プロフィールを開く', command=self.open_profile).pack(side='right')
            ttk.Button(row, text='プロフィールを保存', command=self.save_profile).pack(side='right', padx=6)
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=(12, 8))
            self.check_button = ttk.Button(row, text='事前検査を実行', command=self.check)
            self.check_button.pack(side='left')
            ttk.Button(row, text='結果JSONを保存', command=self.save_report).pack(side='right')
            ttk.Label(panel, text='このツールは検証専用で、ゲームを起動しません。遊ぶときは通常どおりゲームを起動してください。').pack(anchor='w')
            self.status = tk.StringVar(value='ゲームと保存先を指定してください。設定やセーブは変更しません。')
            ttk.Label(panel, textvariable=self.status).pack(anchor='w', pady=6)
            self.output = ScrolledText(panel, wrap='word', height=16, state='disabled')
            self.output.pack(fill='both', expand=True)
            if profile_path is not None:
                self.apply_profile(profile_path)
            window.after(100, self.poll)

        def choose(self, variable):
            path = filedialog.askdirectory()
            if path:
                variable.set(path)

        def add_root(self):
            path = filedialog.askdirectory()
            if path and path not in self.roots.get(0, 'end'):
                self.roots.insert('end', path)

        def remove_root(self):
            for index in reversed(self.roots.curselection()):
                self.roots.delete(index)

        def profile(self):
            if not self.game.get().strip() or not self.save.get().strip():
                raise ValueError('ゲームのフォルダと保存先を選択してください。')
            return {'schemaVersion': 1, 'gameDir': str(Path(self.game.get()).resolve()),
                    'saveDataDir': str(Path(self.save.get()).resolve()),
                    'modRoots': list(self.roots.get(0, 'end')), 'gameVersion': self.version.get().strip()}

        def apply_profile(self, path):
            profile = load_profile(path)
            self.game.set(profile['gameDir'])
            self.save.set(profile['saveDataDir'])
            self.version.set(profile.get('gameVersion', '1.7'))
            self.roots.delete(0, 'end')
            for root in profile.get('modRoots', []):
                self.roots.insert('end', root)
            self.profile_path = Path(path)
            self.report = None

        def open_profile(self):
            path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
            if path:
                try:
                    self.apply_profile(path)
                except (OSError, ValueError, KeyError) as error:
                    messagebox.showerror('プロフィールを開けません', str(error))

        def save_profile(self):
            try:
                profile = self.profile()
                path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='desktop.local.json')
                if path:
                    write_json(path, profile, profile)
                    self.profile_path = Path(path)
            except (OSError, ValueError, KeyError) as error:
                messagebox.showerror('保存できません', str(error))

        def save_report(self):
            if self.report is None:
                return
            path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='preflight-result.json')
            if path:
                try:
                    write_json(path, self.report, self.report['profile'], self.profile_path)
                except (OSError, ValueError, KeyError) as error:
                    messagebox.showerror('保存できません', str(error))

        def begin(self, operation):
            self.check_button.configure(state='disabled')
            self.status.set('検査中です。画像・音声のデコードやゲームコードの実行は行いません。')
            def worker():
                try:
                    self.messages.put(('result', operation()))
                except Exception as error:
                    self.messages.put(('error', str(error)))
            threading.Thread(target=worker, daemon=True).start()

        def check(self):
            try:
                profile = self.profile()
                self.begin(lambda: ('check', profile, check_profile(profile)))
            except ValueError as error:
                messagebox.showerror('入力を確認してください', str(error))

        def poll(self):
            try:
                kind, value = self.messages.get_nowait()
                self.check_button.configure(state='normal')
                if kind == 'error':
                    self.status.set('処理できませんでした。入力を確認して再検査してください。')
                    messagebox.showerror('事前検査', value)
                else:
                    _, _, result = value
                    self.report = result
                    self.output.configure(state='normal')
                    self.output.delete('1.0', 'end')
                    self.output.insert('end', format_result(result))
                    self.output.configure(state='disabled')
                    self.status.set('事前検査が終わりました。ゲーム実行検証は未実施です。')
            except queue.Empty:
                pass
            window.after(100, self.poll)

    Desktop()
    return window


def run_gui(profile_path=None):
    create_window(profile_path).mainloop()
