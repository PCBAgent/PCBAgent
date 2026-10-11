from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

skidl_kicad = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'C', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'C'}), 'ref_prefix':'C', 'fplist':[''], 'footprint':'Capacitor_SMD:C_0402_1005Metric', 'keywords':'cap capacitor', 'description':'Unpolarized capacitor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'R', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R'}), 'ref_prefix':'R', 'fplist':[''], 'footprint':'Resistor_SMD:R_0402_1005Metric', 'keywords':'R res resistor', 'description':'Resistor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'AMS1117-3.3', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'AMS1117-3.3'}), 'ref_prefix':'U', 'fplist':['Package_TO_SOT_SMD:SOT-223-3_TabPin2', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2'], 'footprint':'Package_TO_SOT_SMD:SOT-223-3_TabPin2', 'keywords':'linear regulator ldo fixed positive', 'description':'1A Low Dropout regulator, positive, 3.3V fixed output, SOT-223', 'datasheet':'http://www.advanced-monolithic.com/pdf/ds1117.pdf', 'pins':[
            Pin(num='1',name='GND',func=pin_types.PWRIN,unit=1),
            Pin(num='2',name='VO',func=pin_types.PWROUT,unit=1),
            Pin(num='3',name='VI',func=pin_types.PWRIN,unit=1)], 'unit_defs':[] })])