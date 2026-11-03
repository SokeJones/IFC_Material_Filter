"""Portable IFC material-filter GUI; packaged on Windows with PyInstaller."""
import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from filter_engine import export_ifc, parse_materials


class FilterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('IFC Material Filter v1.2')
        self.geometry('820x660')
        self.minsize(690, 540)
        self.q = queue.Queue()
        self.worker = None
        self.filevar = tk.StringVar()
        self.outputvar = tk.StringVar()
        self.parentvar = tk.StringVar(value='aggregates')
        self.dryvar = tk.BooleanVar(value=False)
        self._layout()
        self.after(100, self._poll)

    def _layout(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Filter IFC by material', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Enter one material per line. Any matching material is enough to retain an element.').pack(anchor='w', pady=(3, 15))
        frm = ttk.Frame(outer)
        frm.pack(fill='x')
        ttk.Label(frm, text='Source IFC').pack(anchor='w')
        f1 = ttk.Frame(frm)
        f1.pack(fill='x', pady=(3, 9))
        ttk.Entry(f1, textvariable=self.filevar).pack(side='left', fill='x', expand=True, padx=(0, 8))
        ttk.Button(f1, text='Browse...', command=self._source).pack(side='left')
        ttk.Label(frm, text='Save filtered IFC as').pack(anchor='w')
        f2 = ttk.Frame(frm)
        f2.pack(fill='x', pady=(3, 12))
        ttk.Entry(f2, textvariable=self.outputvar).pack(side='left', fill='x', expand=True, padx=(0, 8))
        ttk.Button(f2, text='Browse...', command=self._destination).pack(side='left')
        ttk.Label(outer, text='Material names (one per line or separated by semicolons)').pack(anchor='w')
        self.materials = tk.Text(outer, height=6, wrap='word', undo=True)
        self.materials.pack(fill='x', pady=(4, 12))
        self.materials.insert('1.0', 'Stahlbeton Schweiz\n')
        r = ttk.Frame(outer)
        r.pack(fill='x', pady=(0, 10))
        ttk.Label(r, text='Include unassigned children of matching parents:').pack(side='left', padx=(0, 8))
        ttk.Combobox(r, textvariable=self.parentvar, state='readonly', width=22,
                     values=['none','aggregates','aggregates+nests']).pack(side='left')
        ttk.Checkbutton(outer, text='Audit only (CSV, no IFC export)', variable=self.dryvar).pack(anchor='w', pady=(0, 12))
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x')
        self.runbutton = ttk.Button(buttons, text='Start filter', command=self._start)
        self.runbutton.pack(side='left')
        ttk.Button(buttons, text='Clear log', command=lambda: self.log.delete('1.0', 'end')).pack(side='left', padx=8)
        ttk.Label(outer, text='Processing log').pack(anchor='w', pady=(13, 3))
        self.log = tk.Text(outer, height=12, wrap='word', state='normal')
        self.log.pack(fill='both', expand=True)
        ttk.Label(outer, text='Original IFC is never overwritten. Exact material names; case-insensitive.').pack(anchor='w', pady=(8, 0))

    def _source(self):
        path = filedialog.askopenfilename(filetypes=[('IFC models', '*.ifc'), ('All files', '*.*')])
        if path:
            self.filevar.set(path)
            self.outputvar.set(str(Path(path).with_name(Path(path).stem + '_filtered.ifc')))

    def _destination(self):
        path = filedialog.asksaveasfilename(defaultextension='.ifc', filetypes=[('IFC models','*.ifc')])
        if path:
            self.outputvar.set(path)

    def _start(self):
        infile = self.filevar.get().strip()
        outfile = self.outputvar.get().strip()
        materials = parse_materials(self.materials.get('1.0','end'))
        if not infile or not outfile or not materials:
            messagebox.showerror('Missing input', 'Select input IFC and output file, and enter at least one material.')
            return
        if Path(outfile).exists() and not self.dryvar.get():
            messagebox.showerror('Output exists', 'Choose a new output filename. Existing files are never overwritten.')
            return
        self.runbutton.configure(state='disabled')
        self.log.insert('end', f'Filtering for: {", ".join(materials)}\n')
        self.log.see('end')
        options = (infile, outfile, materials, self.parentvar.get(), self.dryvar.get())
        self.worker = threading.Thread(target=self._work, args=(options,), daemon=True)
        self.worker.start()

    def _work(self, options):
        try:
            source, dest, materials, mode, dry = options
            result = export_ifc(source, dest, materials, parent_mode=mode, dry_run=dry,
                                notify=lambda msg: self.q.put(('log', msg)))
            self.q.put(('done', result))
        except Exception:
            self.q.put(('error', traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == 'log':
                    self.log.insert('end', str(data) + '\n')
                    self.log.see('end')
                elif kind == 'done':
                    self.runbutton.configure(state='normal')
                    messagebox.showinfo('Completed', 'Processing finished. See the log and audit CSV for results.')
                elif kind == 'error':
                    self.runbutton.configure(state='normal')
                    self.log.insert('end', 'ERROR\n' + data + '\n')
                    self.log.see('end')
                    messagebox.showerror('Failed', 'Processing failed. See the log for details.')
        except queue.Empty:
            pass
        self.after(120, self._poll)


if __name__ == '__main__':
    FilterApp().mainloop()
