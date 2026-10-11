from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

skidl_kicad = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'C', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'C'}), 'ref_prefix':'C', 'fplist':[''], 'footprint':'Capacitor_SMD:C_0402_1005Metric', 'keywords':'cap capacitor', 'description':'Unpolarized capacitor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'R', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R'}), 'ref_prefix':'R', 'fplist':[''], 'footprint':'Resistor_SMD:R_0603_1608Metric', 'keywords':'R res resistor', 'description':'Resistor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'AMS1117-3.3', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'AMS1117-3.3'}), 'ref_prefix':'U', 'fplist':['Package_TO_SOT_SMD:SOT-223-3_TabPin2', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2'], 'footprint':'Package_TO_SOT_SMD:SOT-223-3_TabPin2', 'keywords':'linear regulator ldo fixed positive', 'description':'1A Low Dropout regulator, positive, 3.3V fixed output, SOT-223', 'datasheet':'http://www.advanced-monolithic.com/pdf/ds1117.pdf', 'pins':[
            Pin(num='1',name='GND',func=pin_types.PWRIN,unit=1),
            Pin(num='2',name='VO',func=pin_types.PWROUT,unit=1),
            Pin(num='3',name='VI',func=pin_types.PWRIN,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'LM358', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'LM358'}), 'ref_prefix':'U', 'fplist':['', ''], 'footprint':'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'keywords':'dual opamp', 'description':'Low-Power, Dual Operational Amplifiers, DIP-8/SOIC-8/TO-99-8', 'datasheet':'http://www.ti.com/lit/ds/symlink/lm2904-n.pdf', 'pins':[
            Pin(num='1',func=pin_types.OUTPUT,unit=1),
            Pin(num='2',name='-',func=pin_types.INPUT,unit=1),
            Pin(num='3',name='+',func=pin_types.INPUT,unit=1),
            Pin(num='5',name='+',func=pin_types.INPUT,unit=2),
            Pin(num='6',name='-',func=pin_types.INPUT,unit=2),
            Pin(num='7',func=pin_types.OUTPUT,unit=2),
            Pin(num='4',name='V-',func=pin_types.PWRIN,unit=3),
            Pin(num='8',name='V+',func=pin_types.PWRIN,unit=3)], 'unit_defs':[{'label': 'uA', 'num': 1, 'pin_nums': ['1', '2', '3']},{'label': 'uB', 'num': 2, 'pin_nums': ['6', '5', '7']},{'label': 'uC', 'num': 3, 'pin_nums': ['4', '8']}] }),
        Part(**{ 'name':'TestPoint', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'TestPoint'}), 'ref_prefix':'TP', 'fplist':[''], 'footprint':'TestPoint:TestPoint_Pad_D1.5mm', 'keywords':'test point tp', 'description':'test point', 'datasheet':'', 'pins':[
            Pin(num='1',name='1',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] })])