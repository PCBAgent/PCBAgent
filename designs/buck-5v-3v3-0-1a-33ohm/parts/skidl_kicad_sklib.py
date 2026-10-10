from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

skidl_kicad = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'XL1509-ADJ', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'XL1509-ADJ'}), 'ref_prefix':'U', 'fplist':['Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'], 'footprint':'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'keywords':'Buck DC/DC Converter', 'description':'Buck DC/DC Converter, 2A, 1.23-37V Adjustable Output Voltage, 4.5-40V Input Voltage', 'datasheet':'https://datasheet.lcsc.com/lcsc/1809050422_XLSEMI-XL1509-5-0E1_C61063.pdf', 'pins':[
            Pin(num='1',name='VIN',func=pin_types.PWRIN,unit=1),
            Pin(num='2',name='OUT',func=pin_types.PWROUT,unit=1),
            Pin(num='3',name='FB',func=pin_types.INPUT,unit=1),
            Pin(num='4',name='~{EN}',func=pin_types.INPUT,unit=1),
            Pin(num='5',name='GND',func=pin_types.PWRIN,unit=1),
            Pin(num='6',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='7',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='8',name='GND',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'R', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R'}), 'ref_prefix':'R', 'fplist':[''], 'footprint':'Resistor_SMD:R_0402_1005Metric', 'keywords':'R res resistor', 'description':'Resistor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] })])