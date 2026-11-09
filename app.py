"""IFC Material Filter GUI: simple routine filtering and opt-in diagnostics.

Keep engine logic in filter_engine unchanged. The GUI only dispatches to it.
"""
import queue
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from filter_engine import export_ifc, parse_materials
from version import __version__


class FilterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'IFC Material Filter v{__version__}')
        self.geometry('760x620')
        self.minsize(620, 570)
        self.q = queue.Queue()
        self.worker = None
        self.filevar = tk.StringVar()
        self.outputvar = tk.StringVar()
        self.parentvar = tk.StringVar(value='aggregates')
        self.dryvar = tk.BooleanVar(value=False)
        self.saveauditvar = tk.BooleanVar(value=False)
        self.savereportsvar = tk.BooleanVar(value=False)
        # Normal use: only the previously benchmarked Batch Cleanup engine.
        self.enginevar = tk.StringVar(value='batch')
        self.validationvar = tk.StringVar(value='basic')
        self.statusvar = tk.StringVar(value='Ready to filter an IFC model.')
        self.stagevar = tk.StringVar(value='')
        self.log_lines = []
        self.log_window = None
        self.log_text = None
        self.operation_start = None
        self._layout()
        self.filevar.trace_add('write', self._input_changed)
        self.after(120, self._poll)

    def _layout(self):
        menubar = tk.Menu(self)
        advanced = tk.Menu(menubar, tearoff=False)
        advanced.add_command(label='Export settings...', command=self._advanced_settings)
        advanced.add_separator()
        verification = tk.Menu(advanced, tearoff=False)
        verification.add_command(label='Verify geometry...', command=self._start_verify)
        verification.add_command(label='Verify materials...', command=self._start_material_verify)
        verification.add_separator()
        verification.add_command(label='View processing log...', command=self._open_log)
        advanced.add_cascade(label='Verification tools', menu=verification)
        menubar.add_cascade(label='Advanced options', menu=advanced)
        self.config(menu=menubar)

        outer = ttk.Frame(self, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='IFC Material Filter', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Create a smaller IFC containing elements with the selected materials.').pack(anchor='w', pady=(5, 19))

        ttk.Label(outer, text='Input IFC file').pack(anchor='w')
        r = ttk.Frame(outer)
        r.pack(fill='x', pady=(4, 14))
        self.source_entry = ttk.Entry(r, textvariable=self.filevar)
        self.source_entry.pack(side='left', fill='x', expand=True, padx=(0, 9))
        ttk.Button(r, text='Browse...', command=self._source).pack(side='left')

        ttk.Label(outer, text='Material names').pack(anchor='w')
        self.materials = tk.Text(outer, height=4, wrap='word', undo=True, font=('Segoe UI', 10))
        self.materials.pack(fill='x', pady=(4, 2))
        ttk.Label(outer, text='One per line or separated by semicolons.', foreground='#666666').pack(anchor='w', pady=(0, 14))

        ttk.Label(outer, text='Output IFC file').pack(anchor='w')
        r = ttk.Frame(outer)
        r.pack(fill='x', pady=(4, 16))
        ttk.Entry(r, textvariable=self.outputvar).pack(side='left', fill='x', expand=True, padx=(0, 9))
        ttk.Button(r, text='Browse...', command=self._destination).pack(side='left')

        # A centered primary action is easier to locate than a full-width button.
        primary_style = ttk.Style(self)
        primary_style.configure('Primary.TButton', font=('Segoe UI', 11, 'bold'), padding=(24, 10))
        action_row = ttk.Frame(outer)
        action_row.pack(fill='x', pady=(4, 0))
        self.runbutton = ttk.Button(action_row, text='Filter IFC', command=self._start,
                                    style='Primary.TButton', width=23)
        self.runbutton.pack(anchor='center')
        progress = ttk.Frame(outer)
        progress.pack(fill='x', pady=(17, 2))
        ttk.Label(progress, textvariable=self.statusvar).pack(side='left')
        self.progress = ttk.Progressbar(outer, orient='horizontal', mode='indeterminate')
        self.progress.pack(fill='x', pady=(6, 3))
        ttk.Label(outer, textvariable=self.stagevar, foreground='#666666').pack(anchor='w')
        ttk.Label(outer, text='Original IFC is never overwritten. Material names match exactly (case-insensitive).',
                  foreground='#666666').pack(anchor='w', pady=(17, 0))

    def _input_changed(self, *_):
        # Works for Browse and manual edits; leave active worker progress intact.
        if not self._busy():
            self._reset_status()

    def _reset_status(self):
        self.progress.stop()
        self.progress.configure(value=0)
        self.statusvar.set('Ready to filter an IFC model.')
        self.stagevar.set('')
        self.operation_start = None

    def _source(self):
        if self._busy():
            messagebox.showwarning('Processing', 'Finish the current operation before changing the input IFC.')
            return
        path = filedialog.askopenfilename(filetypes=[('IFC models', '*.ifc'), ('All files', '*.*')])
        if path:
            self.filevar.set(path)
            self.outputvar.set(str(Path(path).with_name(Path(path).stem + '_filtered.ifc')))

    def _destination(self):
        path = filedialog.asksaveasfilename(defaultextension='.ifc', filetypes=[('IFC models', '*.ifc')])
        if path:
            self.outputvar.set(path)

    def _advanced_settings(self):
        if getattr(self, 'settings_window', None) and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        win = tk.Toplevel(self)
        self.settings_window = win
        win.title('Advanced options — Export settings')
        win.resizable(False, False)
        panel = ttk.Frame(win, padding=20)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Export engine', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        for value, label in [('batch', 'Batch Cleanup (recommended)'),
                             ('ifcpatch', 'IfcPatch (reference)'),
                             ('both', 'Both (benchmark comparison)')]:
            ttk.Radiobutton(panel, text=label, value=value, variable=self.enginevar).pack(anchor='w', pady=3)
        ttk.Separator(panel).pack(fill='x', pady=10)
        ttk.Label(panel, text='Validation level', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        ttk.Radiobutton(panel, text='Standard (recommended)', value='basic', variable=self.validationvar).pack(anchor='w', pady=3)
        ttk.Radiobutton(panel, text='Full schema validation', value='full', variable=self.validationvar).pack(anchor='w', pady=3)
        ttk.Separator(panel).pack(fill='x', pady=10)
        ttk.Label(panel, text='Include unassigned children of matching parents').pack(anchor='w')
        ttk.Combobox(panel, textvariable=self.parentvar, state='readonly', width=26,
                     values=('none', 'aggregates', 'aggregates+nests')).pack(anchor='w', pady=(5, 8))
        ttk.Checkbutton(panel, text='Save audit CSV', variable=self.saveauditvar).pack(anchor='w', pady=(10, 3))
        ttk.Checkbutton(panel, text='Save detailed reports (timing, comparison, diagnostics)', variable=self.savereportsvar).pack(anchor='w', pady=3)
        ttk.Checkbutton(panel, text='Audit only (CSV; do not export IFC)', variable=self.dryvar).pack(anchor='w', pady=(10, 0))
        ttk.Label(panel, text='Audit-only always saves an audit CSV.', foreground='#666666').pack(anchor='w')
        ttk.Label(panel, text='Settings apply to the next filtering operation.', foreground='#666666').pack(anchor='w', pady=(14, 8))
        ttk.Button(panel, text='Close', command=win.destroy).pack(anchor='e')
        win.transient(self)

    def _open_log(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        win = tk.Toplevel(self)
        self.log_window = win
        win.title('Processing log — IFC Material Filter')
        win.geometry('850x500')
        win.minsize(540, 300)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Current session processing log').pack(anchor='w', pady=(0, 8))
        body = ttk.Frame(frame)
        body.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(body)
        scroll.pack(side='right', fill='y')
        self.log_text = tk.Text(body, wrap='none', state='disabled', font=('Consolas', 9), yscrollcommand=scroll.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        scroll.configure(command=self.log_text.yview)
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=(10, 0))
        ttk.Button(controls, text='Save log...', command=self._save_log).pack(side='left')
        ttk.Button(controls, text='Copy all', command=self._copy_log).pack(side='left', padx=8)
        ttk.Button(controls, text='Close', command=win.destroy).pack(side='right')
        self._append_text('\n'.join(self.log_lines) + ('\n' if self.log_lines else ''))
        win.protocol('WM_DELETE_WINDOW', win.destroy)

    def _append_text(self, value):
        if self.log_window is None or not self.log_window.winfo_exists():
            return
        self.log_text.configure(state='normal')
        self.log_text.insert('end', value)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _log(self, message):
        stamp = datetime.now().strftime('%H:%M:%S')
        line = f'[{stamp}] {message}'
        self.log_lines.append(line)
        self._append_text(line + '\n')

    def _save_log(self):
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text log', '*.txt')])
        if path:
            try:
                Path(path).write_text('\n'.join(self.log_lines) + '\n', encoding='utf-8')
            except OSError as error:
                messagebox.showerror('Save log failed', str(error))

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append('\n'.join(self.log_lines))

    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _begin(self, title):
        self.operation_start = time.monotonic()
        self.runbutton.configure(state='disabled')
        self.source_entry.configure(state='disabled')
        self.statusvar.set(title)
        self.stagevar.set('Initializing...')
        self.progress.start(14)
        self._log('--- ' + title + ' ---')

    def _finish(self, message):
        self.progress.stop()
        self.runbutton.configure(state='normal')
        self.source_entry.configure(state='normal')
        self.statusvar.set(message)
        if self.operation_start is not None:
            elapsed = time.monotonic() - self.operation_start
            self.stagevar.set(f'Elapsed: {elapsed:.1f} seconds')
        self._log(message)

    def _start(self):
        if self._busy():
            messagebox.showwarning('Processing', 'Finish the current operation first.')
            return
        infile, outfile = self.filevar.get().strip(), self.outputvar.get().strip()
        materials = parse_materials(self.materials.get('1.0', 'end'))
        if not infile or not materials or (not outfile and not self.dryvar.get()):
            messagebox.showerror('Missing input', 'Select input IFC, enter at least one material, '
                                 'and choose an output file for IFC export.')
            return
        if not outfile and self.dryvar.get():
            # Audit-only writes an audit CSV alongside the source. No output
            # IFC pathname needs to be entered or actually created.
            source_path = Path(infile)
            outfile = str(source_path.with_name(source_path.stem + '_filtered.ifc'))
        if not Path(infile).is_file():
            messagebox.showerror('Input missing', 'The selected source IFC does not exist.')
            return
        from filter_engine import output_paths
        if not self.dryvar.get() and any(p.exists() for p in output_paths(Path(outfile), self.enginevar.get()).values()):
            messagebox.showerror('Output exists', 'Choose another output filename. Existing IFC files are never overwritten.')
            return
        opts = (infile, outfile, materials, self.parentvar.get(), self.dryvar.get(),
                self.enginevar.get(), self.validationvar.get(),
                self.saveauditvar.get(), self.savereportsvar.get())
        self._begin('Auditing IFC...' if self.dryvar.get() else 'Filtering IFC...')
        self._log('Selected materials: ' + '; '.join(materials))
        self._log('Engine: ' + self.enginevar.get() + '; validation: ' + self.validationvar.get())
        self._log(f'Save audit: {self.saveauditvar.get()}; save reports: {self.savereportsvar.get()}')
        self.worker = threading.Thread(target=self._work, args=(opts,), daemon=True)
        self.worker.start()

    def _start_verify(self):
        self._begin_verification('geometry')

    def _start_material_verify(self):
        self._begin_verification('materials')

    def _begin_verification(self, kind):
        if self._busy():
            messagebox.showwarning('Processing', 'Finish the current operation first.')
            return
        source = self.filevar.get().strip()
        if not source or not Path(source).is_file():
            messagebox.showerror('Missing source', 'Select the original IFC in Input IFC file.')
            return
        filtered = filedialog.askopenfilename(title='Select filtered IFC for verification', filetypes=[('IFC models', '*.ifc')])
        if not filtered:
            return
        if Path(source).resolve() == Path(filtered).resolve():
            messagebox.showerror('Invalid comparison', 'Select two different IFC files.')
            return
        self._begin('Verifying ' + kind + '...')
        self.worker = threading.Thread(target=self._verify_work, args=(kind, source, filtered), daemon=True)
        self.worker.start()

    def _work(self, options):
        try:
            source, dest, materials, mode, dry, engine, validation, save_audit, save_reports = options
            result = export_ifc(source, dest, materials, parent_mode=mode, dry_run=dry,
                                engine=engine, validation=validation,
                                save_audit=save_audit, save_reports=save_reports,
                                notify=lambda msg: self.q.put(('log', str(msg))))
            self.q.put(('done', result))
        except Exception:
            self.q.put(('error', traceback.format_exc()))

    def _verify_work(self, kind, source, filtered):
        try:
            if kind == 'geometry':
                from geometry_verification import compare_geometry
                result = compare_geometry(source, filtered, notify=lambda msg: self.q.put(('log', str(msg))))
            else:
                from material_verification import compare_materials
                result = compare_materials(source, filtered, notify=lambda msg: self.q.put(('log', str(msg))))
            self.q.put((kind + '_done', result))
        except Exception:
            self.q.put(('error', traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == 'log':
                    self._log(str(data))
                    self.stagevar.set(str(data)[:115])
                elif kind == 'done':
                    audit_only = data.get('dry_run', False)
                    self._finish('Audit completed — no IFC exported.' if audit_only else
                                 'Filtering completed successfully.')
                    if audit_only:
                        messagebox.showinfo('Audit completed',
                                            'Audit CSV saved. No IFC file was exported.\n' +
                                            str(data.get('audit', '')))
                        continue
                    unmatched = data.get('unmatched_materials', [])
                    if unmatched:
                        messagebox.showwarning('Filtering completed with a material warning',
                            'The IFC was filtered, but these requested material names did not match '
                            'any selected elements:\n' + '; '.join(unmatched)
                            + '\n\nReview the input names and processing log before using this IFC.')
                    else:
                        messagebox.showinfo('Completed', 'IFC filtering completed. Details are available in Advanced options > Verification tools > View processing log.')
                elif kind == 'geometry_done':
                    self._finish('Geometry verification completed.')
                    messagebox.showinfo('Geometry verification',
                                        f"Verified: {data['geometry_verified']}\nDifferences: {data['mismatches']}\nUnverified: {data['geometry_unverified']}\nSee JSON report.")
                elif kind == 'materials_done':
                    self._finish('Material verification completed.')
                    messagebox.showinfo('Material verification',
                                        f"Equivalent: {data['material_equivalent']}\nDifferences: {data['material_mismatches']}\nUnverified: {data['material_unverified']}\nSee JSON report.")
                elif kind == 'error':
                    self._log('ERROR\n' + str(data))
                    self._finish('Processing failed. See processing log.')
                    # Last traceback line contains the actionable exception.
                    detail = str(data).strip().splitlines()[-1] if str(data).strip() else 'Unknown error'
                    messagebox.showerror('Processing failed',
                                         f'{detail}\n\nFull details: Advanced options > '
                                         'Verification tools > View processing log.')
        except queue.Empty:
            pass
        self.after(120, self._poll)


def main(argv=None):
    import sys
    import traceback
    argv = sys.argv[1:] if argv is None else argv
    if '--selftest' not in argv:
        FilterApp().mainloop()
        return 0

    # The Windows executable is built --windowed; stdout/stderr may be absent.
    # Write a result file that the CI runner can inspect, including failures.
    if '--selftest-report' not in argv:
        raise SystemExit('A --selftest-report PATH is required with --selftest.')
    pos = argv.index('--selftest-report')
    if pos + 1 >= len(argv):
        raise SystemExit('Missing path after --selftest-report.')
    report = Path(argv[pos + 1])
    try:
        from selftest import run_selftest
        run_selftest()
    except BaseException:
        report.write_text('FAIL\n' + traceback.format_exc(), encoding='utf-8')
        return 1
    report.write_text('PASS\nFrozen application completed real IFC filtering.\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
