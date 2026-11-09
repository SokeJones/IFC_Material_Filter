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
        self.material_scan_result = None
        self.material_scan_fingerprint = None
        self.material_scan_window = None
        self._layout()
        self.filevar.trace_add('write', self._input_changed)
        self.parentvar.trace_add('write', self._scan_settings_changed)
        self.after(120, self._poll)

    def _layout(self):
        menubar = tk.Menu(self)
        advanced = tk.Menu(menubar, tearoff=False)
        advanced.add_command(label='Export settings...', command=self._advanced_settings)
        material_tools = tk.Menu(advanced, tearoff=False)
        material_tools.add_command(label='Scan IFC materials...', command=self._start_material_scan)
        advanced.add_cascade(label='Material tools', menu=material_tools)
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
        ttk.Label(outer, text='Original IFC is never overwritten. Material names match exactly (case-sensitive).',
                  foreground='#666666').pack(anchor='w', pady=(17, 0))

    def _input_changed(self, *_):
        # Works for Browse and manual edits; leave active worker progress intact.
        self._invalidate_material_scan()
        if not self._busy():
            self._reset_status()

    def _scan_settings_changed(self, *_):
        # Counts can change when aggregate/nest inheritance mode changes.
        self._invalidate_material_scan()

    def _invalidate_material_scan(self):
        self.material_scan_result = None
        self.material_scan_fingerprint = None
        win = self.material_scan_window
        if win is not None and win.winfo_exists():
            win.destroy()
        self.material_scan_window = None

    def _source_fingerprint(self, src):
        path = Path(src).resolve()
        stat = path.stat()
        return (str(path), stat.st_size, stat.st_mtime_ns, self.parentvar.get())

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

    def _start_material_scan(self):
        """Scan explicitly; never reopen a multi-GB source automatically."""
        if self._busy():
            messagebox.showwarning('Processing', 'Finish the current operation first.')
            return
        src = self.filevar.get().strip()
        if not src or not Path(src).is_file():
            messagebox.showerror('Missing source', 'Select a valid input IFC before scanning materials.')
            return
        try:
            fingerprint = self._source_fingerprint(src)
        except OSError as error:
            messagebox.showerror('Input IFC', str(error))
            return
        if (self.material_scan_result is not None and
                self.material_scan_fingerprint == fingerprint):
            self._show_material_scan(self.material_scan_result)
            return
        self._begin('Scanning IFC materials...')
        self._log('Material scan parent mode: ' + self.parentvar.get())
        self._log('The input IFC is read-only; no output file will be created.')
        mode = self.parentvar.get()
        self.worker = threading.Thread(target=self._scan_work,
                                       args=(src, mode, fingerprint), daemon=True)
        self.worker.start()

    def _scan_work(self, src, mode, fingerprint):
        try:
            from material_inventory import scan_ifc_materials
            result = scan_ifc_materials(src, parent_mode=mode,
                                        notify=lambda msg: self.q.put(('log', str(msg))))
            self.q.put(('scan_done', (fingerprint, result)))
        except Exception:
            self.q.put(('error', traceback.format_exc()))

    def _show_material_scan(self, result):
        """Read-only inventory; selected exact names replace the main filter field."""
        if self.material_scan_window is not None and self.material_scan_window.winfo_exists():
            self.material_scan_window.lift()
            return
        win = tk.Toplevel(self)
        self.material_scan_window = win
        win.title('IFC material inventory — select exact names')
        win.geometry('900x530')
        win.minsize(680, 385)
        panel = ttk.Frame(win, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Available IFC materials',
                  font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(panel, text=(f'{len(result["materials"])} distinct material names, '
              f'{result["elements_scanned"]:,} physical elements scanned '
              f'({result["schema"]}; parent mode: {result["parent_mode"]})')).pack(anchor='w', pady=(4, 8))
        ttk.Label(panel, text='Counts show elements selected by each material individually. '
                  'Multiple material names can match the same element.').pack(anchor='w', pady=(0, 8))
        search_row = ttk.Frame(panel)
        search_row.pack(fill='x', pady=(0, 8))
        ttk.Label(search_row, text='Search (case-insensitive):').pack(side='left', padx=(0, 8))
        search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=search_var).pack(side='left', fill='x', expand=True)
        table_frame = ttk.Frame(panel)
        table_frame.pack(fill='both', expand=True)
        columns = ('name', 'total', 'direct', 'type', 'parent')
        table = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='extended')
        headings = [('name', 'Exact material name', 350),
                    ('total', 'Matching elements', 140),
                    ('direct', 'Direct', 75), ('type', 'Type', 75), ('parent', 'Parent', 75)]
        for key, heading, width in headings:
            table.heading(key, text=heading)
            table.column(key, width=width, minwidth=65, anchor='w' if key == 'name' else 'e')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        by_id = {}
        available_names = {entry['name'] for entry in result['materials']}
        chosen_names = set(parse_materials(self.materials.get('1.0', 'end'))) & available_names
        selected_count = tk.StringVar(value=f'{len(chosen_names)} selected')
        refreshing = False
        visible_names = set()

        def refresh(*_):
            nonlocal refreshing, visible_names
            refreshing = True
            table.delete(*table.get_children())
            by_id.clear()
            visible_names = set()
            phrase = search_var.get().casefold().strip()
            for idx, entry in enumerate(result['materials']):
                name = entry['name']
                if phrase and phrase not in name.casefold():
                    continue
                iid = f'mat{idx}'
                by_id[iid] = name
                visible_names.add(name)
                table.insert('', 'end', iid=iid, values=(name, entry['matching_elements'],
                            entry['direct'], entry['type'], entry['parent']))
            table.selection_set(*[iid for iid, name in by_id.items() if name in chosen_names])
            selected_count.set(f'{len(chosen_names)} selected')
            refreshing = False

        def selection_changed(*_):
            if refreshing:
                return
            chosen_names.difference_update(visible_names)
            chosen_names.update(by_id[iid] for iid in table.selection() if iid in by_id)
            selected_count.set(f'{len(chosen_names)} selected')

        def select_visible():
            chosen_names.update(visible_names)
            refresh()

        def clear_all():
            chosen_names.clear()
            refresh()

        def apply_selection():
            if not chosen_names:
                messagebox.showwarning('No materials selected', 'Select at least one material name.', parent=win)
                return
            try:
                current_fingerprint = self._source_fingerprint(self.filevar.get().strip())
            except OSError:
                current_fingerprint = None
            if current_fingerprint != self.material_scan_fingerprint:
                messagebox.showerror('Material scan outdated', 'The input IFC or parent mode changed. Scan again.', parent=win)
                return
            if self._busy():
                messagebox.showwarning('Processing', 'Finish the current operation first.', parent=win)
                return
            # Preserve inventory list ordering rather than arbitrary set order.
            names = [entry['name'] for entry in result['materials'] if entry['name'] in chosen_names]
            self.materials.delete('1.0', 'end')
            self.materials.insert('1.0', '\n'.join(names))
            self._log(f'Inserted {len(names)} exact material name(s) from the IFC inventory.')
            win.destroy()

        table.bind('<<TreeviewSelect>>', selection_changed)
        search_var.trace_add('write', refresh)
        refresh()
        controls = ttk.Frame(panel)
        controls.pack(fill='x', pady=(12, 0))
        ttk.Label(controls, textvariable=selected_count).pack(side='left')
        ttk.Button(controls, text='Select visible', command=select_visible).pack(side='left', padx=(12, 4))
        ttk.Button(controls, text='Clear', command=clear_all).pack(side='left')
        ttk.Button(controls, text='Close', command=win.destroy).pack(side='right')
        ttk.Button(controls, text='Use selected materials', command=apply_selection).pack(side='right', padx=(0, 10))
        ttk.Label(panel, text='Selecting materials only fills the main filter field. '
                  'It does not start filtering or save any reports.',
                  foreground='#666666').pack(anchor='w', pady=(12, 0))
        win.transient(self)

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
                elif kind == 'scan_done':
                    fingerprint, result = data
                    self._finish('Material scan completed.')
                    try:
                        is_current = self._source_fingerprint(self.filevar.get().strip()) == fingerprint
                    except OSError:
                        is_current = False
                    if not is_current:
                        self._log('Material scan results were discarded: source IFC or parent mode changed.')
                        messagebox.showwarning('Material scan outdated', 'The source IFC or parent mode changed. Please scan again.')
                    else:
                        self.material_scan_fingerprint = fingerprint
                        self.material_scan_result = result
                        self._show_material_scan(result)
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
