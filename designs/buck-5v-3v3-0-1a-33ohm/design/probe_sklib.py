from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

probe = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'V', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'v', 'AMMETER', 'ammeter', 'VS', 'vs', 'V'}), 'ref_prefix':'V', 'fplist':None, 'footprint':None, 'keywords':'voltage source', 'description':'Voltage source', 'datasheet':None, 'pins':[
            Pin(num='1',name='p',func=pin_types.PASSIVE),
            Pin(num='2',name='n',func=pin_types.PASSIVE)] }),
        Part(**{ 'name':'R', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R'}), 'ref_prefix':'R', 'fplist':None, 'footprint':None, 'keywords':'res resistor', 'description':'Resistor', 'datasheet':None, 'pins':[
            Pin(num='1',name='p',func=pin_types.PASSIVE),
            Pin(num='2',name='n',func=pin_types.PASSIVE)] })])