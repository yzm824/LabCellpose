"""Exercise the real Windows shell without a person: one window, two views, the trial server, a run, the review
bridge, an export, opening saved results and recent analyses. The Windows counterpart of the macOS native check.

    <bundled python> -I -B -X utf8 windows/shell_check.py --app APP_FOLDER --selftest-exe EXE --work NEW_DIR --result RESULT_FOLDER

APP_FOLDER is a built LabCellpose folder. EXE is the shell compiled with SELFTEST: it follows a script instead of a
person, keeps its settings and browser data under "LabCellpose-selftest" (never the user's), and saves exports
without asking. It is placed beside LabCellpose.exe for the check and removed afterwards. The images are generated
(windows/cross_check.py); RESULT_FOLDER is a completed run to open afterwards. Writes shell_report.json and page
captures into NEW_DIR; exits 0 when every check holds.
"""
from pathlib import Path
import argparse, json, os, shutil, subprocess, sys, time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DATA = Path(os.environ.get('LOCALAPPDATA', '')) / 'LabCellpose-selftest'

UNTIL = "const wait=ms=>new Promise(r=>setTimeout(r,ms)),$=id=>document.getElementById(id);const until=async(test,ms)=>{for(let t=0;t<ms&&!test();t+=200)await wait(200);return !!test();};"
Q = "const q=id=>document.querySelector('#'+id);"   # in the report's frame, where a script cannot wait


def engine_processes(root):
    """Processes of the bundled Python that are still running."""
    command = "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ForEach-Object { \"$($_.ProcessId) $($_.ExecutablePath)\" }"
    done = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True)
    rows = [line.strip().split(' ', 1) for line in done.stdout.splitlines() if ' ' in line.strip()]
    return [path for pid, path in rows if path.lower().startswith(str(root).lower()) and pid != str(os.getpid())]   # not this script itself


def main():
    parser = argparse.ArgumentParser()
    for name in ('--app', '--selftest-exe', '--work', '--result'): parser.add_argument(name, required=True)
    args = parser.parse_args()
    app, work, result = Path(args.app).resolve(), Path(args.work).resolve(), Path(args.result).resolve()
    if work.exists(): raise SystemExit('Choose a new work folder.')
    images = work / 'images'; output = work / 'runs'; saved = work / 'exports'
    for folder in (images / 'Control', images / 'Treated', output, saved): folder.mkdir(parents=True)
    import tifffile
    from cross_check import field
    for index, name in enumerate(('Control/field 1.tif', 'Control/field 2.tif', 'Treated/field 3.tif')):
        tifffile.imwrite(images / name, field(2000 + index), photometric='minisblack')

    assert DATA.name == 'LabCellpose-selftest'
    shutil.rmtree(DATA, ignore_errors=True); DATA.mkdir(parents=True)
    (DATA / 'settings.json').write_text(json.dumps(dict(outputFolder=str(output))), encoding='utf-8')
    temp = Path(os.environ['TEMP'])
    sessions_before = set(temp.glob('LabCellpose-*')); reports_before = set(temp.glob('labcellpose-view-*'))

    shots = {name: str(work / f'shell_{name}.png') for name in ('home', 'setup', 'review', 'export', 'sheet', 'reopened', 'window')}
    steps = [
        dict(wait=3.0), dict(state=1),                                                                                                  # 0, 1
        dict(js=UNTIL + "await until(()=>$('versionBadge').textContent,15000);return {badge:$('versionBadge').textContent,home:!$('home').hidden,recents:!$('recentSection').hidden,"
                        "agent:navigator.userAgent,windows:LabUI.windows,appleGpu:!!document.querySelector('#device option[value=mps]'),output:$('outputPath')?.title||''};"),   # 2
        dict(snapshot=shots['home']),                                                                                                   # 3
        dict(open=str(images)),                                                                                                         # 4  (as if dropped on the window)
        dict(js=UNTIL + "const ok=await until(()=>!$('work').hidden,120000);await wait(800);return {loaded:ok,count:$('fieldCount').textContent,title:$('title').value,hint:$('runHint').textContent,"
                        "run:$('run').textContent,names:[...document.querySelectorAll('#fields .image-row .name')].map(n=>n.title.split(' · ')[0]),path:$('inputPath').textContent};"),   # 5
        dict(js=UNTIL + "if($('work').hidden)return {trial:false,skipped:true};const t0=Date.now();$('test').click();const ok=await until(()=>!$('trialBadge').hidden,400000);return {trial:ok,seconds:(Date.now()-t0)/1000,badge:$('trialBadge').textContent,"
                        "status:$('testStatus').textContent,outlines:document.querySelectorAll('#stage path.trial').length};"),   # 6
        dict(state=1),                                                                                                                  # 7  tester running
        dict(js=UNTIL + "if($('work').hidden)return {skipped:true};const t0=Date.now();$('test').click();await wait(500);await until(()=>$('testLabel').textContent==='Test on this image',400000);return {seconds:(Date.now()-t0)/1000,status:$('testStatus').textContent};"),   # 8  second trial: model already loaded
        dict(snapshot=shots['setup']),                                                                                                  # 9
        dict(js=UNTIL + "if($('work').hidden)return {skipped:true};$('run').click();const started=await until(()=>!$('runBusy').hidden,20000);await wait(4000);$('cancel').click();const t0=Date.now();"
                        "const stopped=await until(()=>!$('runIdle').hidden&&$('runBusy').hidden,180000);return {started,stopped,seconds:(Date.now()-t0)/1000,status:$('status').textContent};"),   # 9a  Stop ends a run
        dict(state=1), dict(probe='folder dialog'),                                                                                     # 9b, 9c
        dict(js=UNTIL + "if($('work').hidden)return {skipped:true};$('noFields').click();for(const at of [0,2]){document.querySelectorAll('#fields .image-row input')[at].click();await wait(100);}const label=$('run').textContent;$('run').click();return {label,selected:$('fieldCount').textContent};"),   # 10
        dict(js=UNTIL + "await wait(1500);if($('runBusy').hidden&&$('runDone').hidden)return {finished:false,skipped:true};const ok=await until(()=>!$('runDone').hidden,900000);return {finished:ok,status:$('status').textContent,review:!$('stepReview').disabled};"),   # 11
        dict(wait=8.0), dict(state=1),                                                                                                  # 12, 13  the review view is showing
        dict(view='review', js=UNTIL + "await until(()=>$('qc-storage').dataset.state==='ok',60000);return {title:$('bar-title').textContent,setupStep:!$('step-setup').hidden,folderButton:!$('show-folder').hidden,"
                                       "folderTitle:$('show-folder').title,progress:$('qc-progress').textContent,saved:$('qc-storage').textContent,bridge:!!window.webkit?.messageHandlers?.labReview};"),   # 14
        dict(wait=1.5),                                                                                                                 # 15
        dict(view='review', frame=True, js=Q + "return {ready:!q('qc-toggle').disabled,before:q('count').textContent,wording:[...document.querySelectorAll('[data-win]')].map(n=>n.textContent)};"),   # 16
        dict(view='review', frame=True, js=Q + "q('qc-toggle').click();return true;"), dict(wait=0.8),                                 # 17, 18
        dict(view='review', frame=True, js=Q + "const excluded=q('count').textContent;q('qc-reviewed').click();return {excluded};"), dict(wait=0.8),   # 19, 20
        dict(view='review', frame=True, js=Q + "return {progress:q('review-progress').textContent,image:q('image-label').textContent,thumbs:document.querySelectorAll('.thumb').length};"),   # 21
        dict(view='review', js=UNTIL + "await wait(1000);return {progress:$('qc-progress').textContent,saved:$('qc-storage').textContent};"),   # 22
        dict(view='review', snapshot=shots['review']), dict(screen=shots['window']),                                                    # 23, 23a
        dict(view='review', js=UNTIL + "$('step-export').click();await until(()=>document.querySelectorAll('#export-preview td').length>0,30000);return {shape:$('export-shape').textContent,file:$('export-file').textContent,"
                                       "count:$('qc-export-count').textContent,save:!document.querySelector('[data-qc-download=included]').disabled};"),   # 24
        dict(view='review', snapshot=shots['export']),                                                                                  # 25
        dict(view='review', js="document.querySelector('[data-qc-download=included]').click();return true;"), dict(wait=4.0), dict(state=1),   # 26, 27, 28  the table is saved as a download
        dict(view='review', js="document.getElementById('step-review').click();window.webkit.messageHandlers.labReview.postMessage({action:'showSetup'});return {exportShown:!document.getElementById('export-view').hidden};"),   # 29
        dict(wait=0.8), dict(state=1),                                                                                                  # 30, 31  back in setup
        dict(js="document.getElementById('stepExport').click();return true;"),                                                          # 32
        dict(wait=1.5), dict(state=1),                                                                                                  # 33, 34  review view again, on Export
        dict(view='review', js="return {exportShown:!document.getElementById('export-view').hidden};"),                                 # 35
        dict(open=str(result)), dict(wait=12.0), dict(state=1),                                                                         # 36, 37, 38  a saved result opens in the same window
        dict(view='review', js=UNTIL + "await until(()=>$('qc-storage').dataset.state==='ok',60000);return {title:$('bar-title').textContent,progress:$('qc-progress').textContent};"),   # 39
        dict(view='review', snapshot=shots['reopened']),                                                                                # 40
        dict(view='review', js="window.webkit.messageHandlers.labReview.postMessage({action:'showSetup'});return true;"),               # 41
        dict(wait=0.8),                                                                                                                 # 42
        dict(js=UNTIL + "return {status:$('status').textContent,recentRows:document.querySelectorAll('#recents > *').length};"),         # 43
        dict(js="document.getElementById('stepReview').click();return true;"),                                                          # 44  back to the review
        dict(wait=1.5),                                                                                                                 # 45
        dict(view='review', frame=True, js="document.querySelector('#open-summary').click();return true;"),                             # 46  a sheet of the report
        dict(wait=0.8),                                                                                                                 # 47
        dict(view='review', snapshot=shots['sheet']),                                                                                   # 48
        dict(view='review', js="const dim=document.body.classList.contains('sheet-open');window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,600));return {dim,after:document.body.classList.contains('sheet-open')};"),   # 49
        dict(state=1), dict(quit=1),                                                                                                    # 50, 51
    ]
    script = work / 'shell_script.json'; out = work / 'shell_check.json'
    script.write_text(json.dumps(dict(out=str(out), downloads=str(saved), steps=steps)), encoding='utf-8')
    exe = app / 'LabCellpose.selftest.exe'
    shutil.copyfile(args.selftest_exe, exe)
    # Like the other program files on the build machine, it carries the mark Windows puts on downloaded files.
    with open(str(exe) + ':Zone.Identifier', 'w') as mark: mark.write('[ZoneTransfer]\nZoneId=3\n')
    started = time.time(); timed_out = False
    try:
        environment = dict(os.environ, LABCELLPOSE_SELFTEST=str(script), LABCELLPOSE_SELFTEST_LOG=str(work / 'shell_trace.log'), LABCELLPOSE_STACKS=str(work / 'stacks'))
        try: subprocess.run([str(exe)], env=environment, timeout=1500)
        except subprocess.TimeoutExpired: timed_out = True
    finally:
        time.sleep(3)
        left = engine_processes(app)
        try: exe.unlink()
        except OSError: time.sleep(3); exe.unlink()
    results = {r['step']: r['result'] for r in json.loads(out.read_text(encoding='utf-8'))} if out.exists() else {}
    try: settings = json.loads((DATA / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError): settings = {}
    exported = sorted(saved.glob('*'))
    table = exported[0].read_text(encoding='utf-8-sig').splitlines() if exported else []
    sessions_left = set(temp.glob('LabCellpose-*')) - sessions_before; reports_left = set(temp.glob('labcellpose-view-*')) - reports_before
    shutil.rmtree(DATA, ignore_errors=True)

    def get(i, k=None):
        value = results.get(i)
        return value.get(k) if k and isinstance(value, dict) else (None if k else value)
    recents = [str(r.get('path', '')) for r in settings.get('recentResults', [])]
    checks = {
        'starts on the setup view with the start page': bool(get(1, 'setupVisible')) and not get(1, 'reviewVisible') and get(2, 'home') is True,
        'version shown, pages know they are on Windows, no Apple GPU choice': str(get(2, 'badge')) == 'Version 3.0' and get(2, 'windows') is True and get(2, 'appleGpu') is False,
        'the remembered output folder is offered': str(get(2, 'output')) == str(output),
        'a dropped folder is imported with folder/name image names': get(5, 'loaded') is True and '3 of 3' in str(get(5, 'count')) and get(5, 'names') == ['Control/field 1.tif', 'Control/field 2.tif', 'Treated/field 3.tif'],
        'trial segmentation draws outlines': get(6, 'trial') is True and (get(6, 'outlines') or 0) > 0,
        'the trial process stays loaded': bool(get(7, 'tester')) and (get(8, 'seconds') or 1e9) < (get(6, 'seconds') or 0),
        'Stop ends a run and the app is ready again': get(10, 'started') is True and get(10, 'stopped') is True and 'Stopped' in str(get(10, 'status')) and not get(11, 'busy'),
        'the folder dialog of Windows can be made': get(12) == 'ok',
        'run of two selected images finishes': get(13, 'label') == 'Analyze 2 images' and get(14, 'finished') is True,
        'the review view replaces the setup view in the same window': bool(get(16, 'reviewVisible')) and not get(16, 'setupVisible') and not get(16, 'tester') and str(get(16, 'title')).startswith('LabCellpose — LabCellpose_'),
        'review page has the app bridge and loads the run': get(17, 'bridge') is True and get(17, 'setupStep') is True and get(17, 'title') == get(5, 'title'),
        'Windows wording in the review': 'File Explorer' in str(get(17, 'folderTitle')) and sorted(get(19, 'wording') or []) == ['Alt', 'Ctrl-scroll to zoom · Shift-drag to select several cells', 'Shift-click, Ctrl-click'],
        'exclusion and reviewed mark are saved with the results': get(19, 'ready') is True and str(get(19, 'before')) != str(get(22, 'excluded')) and '1 of 2' in str(get(25, 'progress')) and 'saved with the results' in str(get(25, 'saved')),
        'export preview and file name': get(28, 'save') is True and str(get(28, 'file')).endswith('.csv'),
        'the table is saved as a CSV file': len(exported) == 1 and exported[0].suffix == '.csv' and len(table) > 1 and 'field' in table[0] and not get(32, 'downloads'),
        'Set up in the review page returns to the setup view': bool(get(35, 'setupVisible')) and not get(35, 'reviewVisible'),
        'Export in the setup page opens the export step': bool(get(38, 'reviewVisible')) and get(39, 'exportShown') is True,
        'a saved result opens in the same window': bool(get(42, 'reviewVisible')) and str(get(42, 'lastResult')).lower().startswith(str(result).lower()) and get(42, 'recents') == 2,
        'recent analyses and settings are remembered': any(p.lower().startswith(str(output).lower()) for p in recents) and 'appPresetVersion' in json.dumps(settings.get('setupMemory', '')),
        'a sheet of the report dims the bar of the window and Escape closes it': get(53, 'dim') is True and get(53, 'after') is False and bool(get(54, 'reviewVisible')),
        'the app quits by itself and leaves no engine process, session folder or temporary report': not timed_out and not left and not sessions_left and not reports_left,
    }
    report = dict(checks=checks, seconds=round(time.time() - started, 1), timed_out=timed_out, engine_processes_left=left,
                  session_folders_left=sorted(str(p) for p in sessions_left), reports_left=sorted(str(p) for p in reports_left),
                  exported=[p.name for p in exported], table_head=table[:2], results={str(k): v for k, v in sorted(results.items())}, snapshots=shots)
    (work / 'shell_report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    for name, ok in checks.items(): print('PASS' if ok else 'FAIL', name)
    print(json.dumps(report['results'], indent=1, ensure_ascii=False, default=str)[:6000])
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == '__main__':
    main()
