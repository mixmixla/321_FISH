"""R3-LOCAL-01 reproducible, bounded build/preflight adapter; no GUI acceptance."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import local_trial
from friend_trial_process import launch_owned


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class RecordedJob:
    def __init__(self, proc, record):
        self.proc, self.record = proc, record

    def __getattr__(self, name):
        return getattr(self.proc, name)

    def terminate_tree(self):
        self.record['active_before_cleanup'] = self.proc.active_count()
        ok = self.proc.terminate_tree()
        self.record['active_after_cleanup'] = self.proc.active_count()
        self.record['cleanup_ok'] = bool(ok and self.record['active_after_cleanup'] == 0)
        return self.record['cleanup_ok']

    def close(self):
        try:
            self.proc.close()
        except Exception as exc:
            self.record['close_ok'] = False
            self.record['close_error_type'] = type(exc).__name__
            raise
        else:
            self.record['close_ok'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['entry-build', 'preflight', 'entry-cli'])
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args(argv)
    source = args.source.resolve()
    allowed = (ROOT / '_tmp_gui/r3-local-20261021').resolve()
    if not source.is_relative_to(allowed) or not (source/'friend_trial_start.py').is_file():
        raise ValueError('source must be the R3 owned build copy')
    runroot = allowed / 'preflight'
    if args.mode == 'entry-build':
        command = [sys.executable, '-m', 'PyInstaller', '--onefile', '--console',
                   '--clean', '--noconfirm', '--name', 'StartTrial',
                   '--distpath', str(source/'dist'),
                   '--workpath', str(source/'_tmp_gui/entry-work'),
                   '--specpath', str(source/'_tmp_gui/entry-spec'),
                   str(source/'friend_trial_start.py')]
        log = source.parent/'entry-build.log'
        with log.open('xb') as output:
            result = subprocess.run(command, cwd=source,
                env=local_trial._build_env(source/'_tmp_gui/entry-build-profile'),
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        exe = source/'dist/StartTrial.exe'
        summary = {'command':command, 'exit_code':result.returncode, 'log':str(log),
                   'path':str(exe), 'size':exe.stat().st_size if exe.exists() else 0,
                   'sha256':local_trial._sha256(exe) if exe.exists() else None}
        write_json(source.parent/'entry-build-summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False))
        return result.returncode or (0 if summary['size'] else 5)
    records = []
    def recorded_launch(command, **kwargs):
        proc = launch_owned(command, **kwargs)
        record = {'role':Path(kwargs['log_path']).stem, 'pid':proc.pid,
                  'ownership':'suspended -> unnamed Job -> resume; kill-on-close',
                  'close_ok':False}
        records.append(record)
        try:
            record['active_after_launch'] = proc.active_count()
        except BaseException as exc:
            record['registration_error_type'] = type(exc).__name__
            try:
                record['registration_cleanup_ok'] = bool(proc.terminate_tree())
            finally:
                try:
                    proc.close()
                except BaseException as close_exc:
                    record['close_error_type'] = type(close_exc).__name__
                    raise
                else:
                    record['close_ok'] = True
            raise
        return RecordedJob(proc, record)
    if args.mode == 'preflight':
        original = local_trial.launch_process
        local_trial.launch_process = recorded_launch
        try:
            code, summary = local_trial.run_candidate(source, runroot)
        finally:
            local_trial.launch_process = original
            write_json(source.parent/'job-ownership.json', records)
        jobs_ok = len(records) == 4 and all(r.get('cleanup_ok') and r.get('close_ok') and
                       r.get('active_after_cleanup') == 0 for r in records)
        code = code if code else (0 if jobs_ok else 4)
        write_json(source.parent/'preflight-result.json', {
            'exit_code':code, 'business_probe_exit_code':summary['exit_code'],
            'jobs_ok':jobs_ok, 'summary':str(runroot/summary['run_id']/'summary.json'),
            'native_gui_acceptance':False, 'natural_exit_verified':False})
        print(json.dumps({'exit_code':code, 'jobs_ok':jobs_ok, 'run_id':summary['run_id']}))
        return code
    # Actual compiled console entry probes. No demo children are started by --dry-run.
    exe = source/'dist/StartTrial.exe'
    cli = local_trial._new_run_dir(runroot, 'entry-cli')
    results = []
    summary = {'exit_code':1, 'results':results, 'jobs':records, 'actual_demo_run':False,
               'native_gui_acceptance':False, 'natural_exit_verified':False}
    ok = False
    try:
        for label, flags in [('help',['--help']), ('demo-dry-run',['--mode','demo','--dry-run','--bundle-dir',str(source)])]:
            env = local_trial._clean_env(profile=cli/('profile-'+label), flags=local_trial.TRIAL_FLAGS)
            proc = recorded_launch([str(exe),*flags], cwd=str(source), env=env,
                                   log_path=cli/(label+'.txt'), desktop_name='MoyuR3-CLI-'+cli.name)
            probe = {'probe':label, 'exit_code':None, 'log':str(cli/(label+'.txt'))}
            results.append(probe)
            try:
                probe['exit_code'] = proc.wait(timeout=45)
            finally:
                try:
                    proc.terminate_tree()
                finally:
                    proc.close()
        plan = json.loads((cli/'demo-dry-run.txt').read_text(encoding='utf-8').strip())
        summary['plan'] = plan
        assert plan['mode']=='demo' and plan['address']=='127.0.0.1' and plan['fresh_only']
        assert not plan['network_settings_changed'] and not plan['firewall_changes']
        assert not plan['real_data_import'] and not plan['external_windows_and_real_lan_verified']
        ok = all(r['exit_code']==0 for r in results) and all(r.get('cleanup_ok') and r.get('close_ok') for r in records)
        summary['exit_code'] = 0 if ok else 1
    except BaseException as exc:
        summary['error_type'] = type(exc).__name__
        raise
    finally:
        write_json(source.parent/'entry-cli-summary.json', summary)
    print(json.dumps({'entry_cli_ok':ok, 'log_dir':str(cli)}))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
