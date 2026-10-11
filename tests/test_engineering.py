"""Regression tests for under-rated parts and false-success manufacturing output."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/parts'))
from lookup import requests_from_sim, select, lookup
from catalog import power_rating, search_passive
from netlist_checks import validate
from validation import digest, simulation_evidence
from netlist import run as generate


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_extraction_does_not_confuse_equal_loads_comments_or_scientific_values():
    text = '''
# R(ref="FAKE", value=100 @ u_Ohm)
x = 33
R(ref='SENSE', value=x @ u_Ohm)
R(ref='RL', value=33 @ u_Ohm)
C(ref='C1', value=1e-6 @ u_F)
'''
    items = requests_from_sim(text, {'load': '33 ohm', 'external_components': ['RL']})
    assert [p['ref'] for p in items] == ['SENSE', 'RL', 'C1']
    assert items[0]['on_board'] and not items[1]['on_board']
    assert items[2]['value_si'] == 1e-6
    with pytest.raises(ValueError, match='Unresolved'):
        requests_from_sim("R(ref='R1', value=calculate())", {})


def libraries(tmp_path):
    fp, sym = tmp_path / 'fp', tmp_path / 'sym'
    sym.mkdir()
    for lib, name, pads in [('Resistor_SMD','R_0805_2012Metric', ['1','2']),
                            ('Connector_PinHeader_2.54mm','PinHeader_1x03_P2.54mm_Vertical', ['1','2','3'])]:
        folder = fp / f'{lib}.pretty'; folder.mkdir(parents=True)
        (folder / f'{name}.kicad_mod').write_text('(footprint ' + ' '.join(f'(pad "{p}" smd rect)' for p in pads) + ')')
    (sym / 'Device.kicad_sym').write_text('(kicad_symbol_lib (symbol "R" (symbol "R_1_1" (pin passive line (name "~") (number "1")) (pin passive line (name "~") (number "2")))))')
    (sym / 'Connector_Generic.kicad_sym').write_text('(kicad_symbol_lib (symbol "Conn_01x03" (symbol "Conn_01x03_1_1" ' + ' '.join(f'(pin passive line (name "Pin_{p}") (number "{p}"))' for p in ['1','2','3']) + ')))')
    return fp, sym


def row(value, watt, stock=100, price='0.01'):
    return {'category':'Resistors','describe':f'{value}Ω 50V {watt}W ±1%', 'model':f'R-{value}-{watt}', 'package':'0805',
            'code':f'C{value}-{watt}', 'stock':str(stock),'price':price,'library':'base'}


def test_power_stock_and_unknown_voltage_are_not_accepted(tmp_path):
    fp,sym = libraries(tmp_path)
    rows = [row(10, .0625), row(10, 1, stock=0), row(10, .5, price='.02')]
    chosen = search_passive(rows, 'resistor', 10, 5, fp, sym, {'power_w': .289, 'voltage_v':1.7})
    assert chosen['power_rating_w'] == .5
    assert search_passive(rows[:2], 'resistor',10,5,fp,sym, {'power_w': .289}) is None
    assert power_rating('1/4W') == .25
    cap = dict(rows[0], category='Capacitors', describe='10uF unknown voltage')
    assert search_passive([cap], 'capacitor', 10e-6,48,fp,sym) is None


def measured_design(tmp_path):
    root = tmp_path / 'project'; design = root / 'design'; design.mkdir(parents=True)
    spec = {'prompt':'5V divider', 'supply_voltage_v':5, 'output_voltage_v':3.3,
            'output_current_a':.1, 'load':'33 ohm', 'external_components':['RL'],
            'tolerances':{'output_voltage_v':.05,'output_current_a':.01}}
    (design/'circuit-spec.json').write_text(json.dumps(spec))
    (design/'skidl_sim.py').write_text('''from skidl.pyspice import *
def measure():
    reset()
    vin, vout = Net("VIN"), Net("VOUT")
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    R(ref="R1", value=10 @ u_Ohm)["p", "n"] += vin, vout
    R(ref="R2", value=47 @ u_Ohm)["p", "n"] += vout, gnd
    R(ref="RL", value=33 @ u_Ohm)["p", "n"] += vout, gnd
    op = Simulator.factory().simulation(generate_netlist()).operating_point()
    v = float(op.nodes["vout"][0])
    return {"output_voltage_v": v, "output_current_a": v/33}
''')
    proc = subprocess.run([sys.executable, str(ROOT/'skills/circuit/verify.py'), str(root)], capture_output=True,text=True)
    assert proc.returncode == 0, proc.stderr
    return root, spec


def test_real_ngspice_dissipation_and_stale_evidence(tmp_path):
    root,spec = measured_design(tmp_path)
    evidence,error = simulation_evidence(root/'design')
    assert error is None
    parts = {p['ref']:p for p in evidence['components']}
    assert parts['R1']['stress']['power_w'] == pytest.approx(.289477, rel=.001)
    assert parts['R2']['stress']['power_w'] == pytest.approx(.231512, rel=.001)
    fp,sym = libraries(tmp_path)
    requests = [dict(p,on_board=p['ref']!='RL', requested_value=str(p['value_si'])) for p in parts.values()]
    chosen = select(spec,'', [row(10,.0625),row(10,.5),row(47,.1),row(47,.5)],fp,sym,requests=requests)
    assert [p['power_rating_w'] for p in chosen if p['on_board']] == [.5,.5]
    (root/'design/skidl_sim.py').write_text('# changed')
    assert 'stale' in simulation_evidence(root/'design')[1]


def board():
    return '''(export (components
      (comp (ref R1) (value 10) (footprint Resistor_SMD:R_0805_2012Metric) (libsource (lib Device) (part R)))
      (comp (ref R2) (value 47) (footprint Resistor_SMD:R_0805_2012Metric) (libsource (lib Device) (part R)))
      (comp (ref J1) (value Conn_01x03) (footprint Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical) (libsource (lib Connector_Generic) (part Conn_01x03))))
      (nets (net (name VIN) (node (ref R1) (pin 1)) (node (ref J1) (pin 1)))
            (net (name VOUT) (node (ref R1) (pin 2)) (node (ref R2) (pin 1)) (node (ref J1) (pin 2)))
            (net (name GND) (node (ref R2) (pin 2)) (node (ref J1) (pin 3)))))'''


def test_netlist_requires_matching_values_connectivity_and_interfaces(tmp_path):
    fp,sym = libraries(tmp_path)
    parts = [{'ref':ref,'on_board':True,'symbol':'Device:R','footprint':'Resistor_SMD:R_0805_2012Metric'} for ref in ['R1','R2']]
    evidence = {'components':[{'ref':'R1','kind':'resistor','value_si':10,'nets':['VIN','VOUT']},
                              {'ref':'R2','kind':'resistor','value_si':47,'nets':['VOUT','0']}]}
    spec = {'supply_voltage_v':5,'output_voltage_v':3.3}
    assert validate(board(),parts,evidence,spec,fp,sym) == []
    assert any('value differs' in e for e in validate(board().replace('(value 10)','(value R)'),parts,evidence,spec,fp,sym))
    assert any('pin does not exist' in e for e in validate(board().replace('(ref R1) (pin 1)','(ref R1) (pin p)'),parts,evidence,spec,fp,sym))
    with pytest.raises(ValueError):
        validate('(netlist)',parts,evidence,spec,fp,sym)


def test_generator_does_not_accept_a_stale_or_malformed_board(tmp_path, monkeypatch):
    root,spec = measured_design(tmp_path)
    fp,sym = libraries(tmp_path)
    folder = root/'parts'; folder.mkdir()
    evidence,_ = simulation_evidence(root/'design')
    parts = [{'ref':r,'kind':'resistor','on_board':True,'matched':True,'symbol':'Device:R', 'power_rating_w':.5, 'voltage_rating_v':50,
              'footprint':'Resistor_SMD:R_0805_2012Metric'} for r in ['R1','R2']]
    (folder/'parts.json').write_text(json.dumps({'parts':parts,'status':'pass','simulation_inputs':evidence['inputs'], 'simulation_evidence_sha256':digest(root/'design/simulation-evidence.json')}))
    (folder/'skidl_kicad.py').write_text('pass')
    (folder/'board.net').write_text(board())
    monkeypatch.setenv('KICAD_FOOTPRINT_DIR',str(fp)); monkeypatch.setenv('KICAD10_SYMBOL_DIR',str(sym))
    assert generate(root)['status'] == 'fail'
    assert not (folder/'board.net').exists()
    (folder/'skidl_kicad.py').write_text("from pathlib import Path\nPath('board.net').write_text('(netlist)')")
    assert generate(root)['status'] == 'fail'
    (folder/'skidl_kicad.py').write_text(f"from pathlib import Path\nPath('board.net').write_text({board()!r})")
    assert generate(root)['status'] == 'pass'
    sys.path.insert(0, str(ROOT/'skills/layout'))
    import layout
    layout.check_netlist_provenance(root)
    evidence['status'] = 'fail'
    (root/'design/simulation-evidence.json').write_text(json.dumps(evidence))
    with pytest.raises(layout.NoBoard, match='does not pass'):
        layout.check_netlist_provenance(root)


def test_stage_allows_repeated_failures_and_ignores_previous_lockouts(tmp_path, monkeypatch):
    module = load_tool('pcb_stage')
    root = tmp_path/'design'; root.mkdir(); (root/'design').mkdir()
    (root/'design/skidl_sim.py').write_text('bad')
    monkeypatch.setattr(module,'run_command',lambda *a,**k: subprocess.CompletedProcess(a, 2, '', 'failure'))
    for attempt in range(1, 21):
        result = module.execute(root,'verify')
        assert result['status'] == 'execution_error'
        assert result['failed_attempts'] == attempt
    monkeypatch.setattr(module,'run_command',lambda *a,**k: subprocess.CompletedProcess(a, 0, 'fixed', ''))
    assert module.execute(root,'verify')['status'] == 'pass'


def test_stage_waits_without_deadline_and_cleans_up_on_user_interrupt(monkeypatch):
    from unittest.mock import Mock
    module = load_tool('pcb_stage')
    proc = Mock(pid=12345, returncode=0)
    proc.communicate.return_value = ('complete','')
    proc.poll.return_value = 0
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k: proc)
    result = module.run_command(['test'])
    assert result.stdout == 'complete'
    proc.communicate.assert_called_once_with()
    proc.communicate.reset_mock()
    proc.communicate.side_effect = [KeyboardInterrupt(), ('','')]
    proc.poll.return_value = None
    killed = Mock()
    monkeypatch.setattr(module.os, 'killpg', killed)
    with pytest.raises(KeyboardInterrupt):
        module.run_command(['test'])
    killed.assert_called_once_with(proc.pid, module.signal.SIGKILL)
